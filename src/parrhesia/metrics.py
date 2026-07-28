"""Held-out metrics: score patches the fit never saw against its winding family.

Every metric is computed at patch quad centers (matching the granularity of
villa's satisfaction metrics, for comparability), against the union of the
run's winding surfaces:

- surface distance percentiles and fraction within ``tau``;
- sheet consistency: one physical patch must land on one continuous sheet.
  Winding ids alone cannot express this at the theta seam (a patch legitimately
  spans windings w and w+1 there), and no fixed-width window over a winding
  coordinate can either (real bands follow the spiral for many turns). Each
  face carries a continuous winding coordinate ``u = winding_id + column /
  columns``; grid-adjacent quads agreeing within half a turn are connected,
  same-turn islands are merged, and consistency is the fraction of points on
  the largest resulting sheet (see ``sheet_components``). The raw
  modal-winding fraction (``single_winding_consistency``) is kept alongside;
- winding-number agreement, when the patch carries a ``winding.tif`` grid;
- normal agreement (sign-agnostic angle between patch and matched face);
- evidence leakage, when the fit's input patches are provided: the distance
  from every scored point to the union of input surfaces. Points closer than
  ``unseen_min_dist`` were physically available to the fit through overlapping
  inputs, whatever the split says; the ``unseen`` aggregate re-scores only the
  points beyond that distance. This is the guarantee a name-level split cannot
  give (overlapping selections of one parent patch are distinct directories).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import TriangleSoup, surface_distance
from .io_tifxyz import QuadSurface

DEFAULT_TAU = 6.0  # scan voxels; matches satisfaction_distance_tolerance for comparability
DEFAULT_UNSEEN_MIN_DIST = 2.0  # vox; overlapping inputs agree sub-voxel, sheets sit ~1 pitch apart
SHEET_MAX_JUMP_TURNS = 0.5  # adjacent quads farther apart in u than this belong to different sheets
_MIN_UNSEEN_POINTS = 8  # patches with fewer unseen points are excluded from the unseen aggregate

LEAKAGE_THRESHOLDS = (0.5, 1.0, 2.0, 6.0)


class PatchSkip(ValueError):
    """A patch has nothing scorable (no valid quad, or nothing in the z window).

    Distinct from engine errors on purpose: ``score_patches`` skips these and
    counts them, while any other failure propagates loudly instead of being
    silently folded into a skip count.
    """


@dataclass
class WindingFamilySoup:
    """All winding surfaces of a run merged into one queryable soup."""

    soup: TriangleSoup
    face_winding: np.ndarray  # (M,) winding id per face
    face_u: np.ndarray  # (M,) continuous winding coordinate per face
    winding_ids: list[int]

    @classmethod
    def from_family(cls, family: dict[int, QuadSurface]) -> WindingFamilySoup:
        if not family:
            raise ValueError("empty winding family")
        vertices, faces, face_wids, face_us = [], [], [], []
        offset = 0
        for wid in sorted(family):
            surface = family[wid]
            v, f = surface.triangles()
            vertices.append(v.astype(np.float64))
            faces.append(f + offset)
            face_wids.append(np.full(len(f), wid, dtype=np.int64))
            # Continuous winding coordinate per face. Grid columns follow the
            # spiral, so u = wid + column fraction is continuous across the
            # theta seam (column 0 of winding w+1 continues the last column of
            # winding w). triangles() emits two blocks of faces in valid-quad
            # C order, so the per-quad values are tiled twice.
            qmask = surface.valid_quad_mask
            cols = np.nonzero(qmask)[1].astype(np.float64)
            n_qcols = max(qmask.shape[1], 1)
            u_quad = wid + (cols + 0.5) / n_qcols
            face_us.append(np.concatenate([u_quad, u_quad]))
            offset += len(v)
        soup = TriangleSoup(np.concatenate(vertices), np.concatenate(faces))
        return cls(
            soup=soup,
            face_winding=np.concatenate(face_wids),
            face_u=np.concatenate(face_us),
            winding_ids=sorted(family),
        )


def _grid_adjacency(
    u: np.ndarray, quad_idx: np.ndarray, max_jump: float
) -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Connected components of "grid-adjacent and u agrees within max_jump",
    plus the surviving edges per grid direction (used to estimate drift)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(u)
    rows, cols = quad_idx[:, 0], quad_idx[:, 1]
    grid = np.full((rows.max() + 2, cols.max() + 2), -1, dtype=np.int64)
    grid[rows, cols] = np.arange(n)
    edges: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for key, (da, db) in (("row", (1, 0)), ("col", (0, 1))):
        a = grid[: grid.shape[0] - da, : grid.shape[1] - db]
        b = grid[da:, db:]
        ok = (a >= 0) & (b >= 0)
        ia, ib = a[ok], b[ok]
        smooth = np.abs(u[ia] - u[ib]) <= max_jump
        edges[key] = (ia[smooth], ib[smooth])
    ea = np.concatenate([edges["row"][0], edges["col"][0]])
    eb = np.concatenate([edges["row"][1], edges["col"][1]])
    adj = coo_matrix((np.ones(len(ea)), (ea, eb)), shape=(n, n))
    _, labels = connected_components(adj, directed=False)
    return labels, edges


def sheet_components(
    u: np.ndarray, quad_idx: np.ndarray, max_jump: float = SHEET_MAX_JUMP_TURNS
) -> np.ndarray:
    """Label each scored quad with the continuous sheet it lies on.

    Two grid-adjacent quads share a sheet when their continuous winding
    coordinates agree to within ``max_jump`` turns; connected components of
    that relation are sheets as the fit experienced them. A sheet switch cuts
    the patch at a ~1-turn jump; the theta seam does not, since u is
    continuous there.

    Holes split one physical sheet into several components, so components are
    then merged, but only when the evidence says they belong together: a
    patch lying on one sheet has a roughly constant u-drift per grid step
    (each column advances a fixed fraction of a turn), so two components are
    merged when the u difference at their closest grid-space pair matches
    what that drift predicts across the gap, to within ``max_jump``. A hole
    is bridged whatever its size; a switch shows a full-turn residual at zero
    grid distance and is never bridged.

    Comparing component *medians* instead (parrhesia v0.3) is wrong in both
    directions and was withdrawn: it splits a long band that merely has a
    hole, and it chains fragments across many turns. On PHerc. Paris 4 that
    rated one heavily switched patch 0.986 while 18% of its own grid
    adjacencies were cut; the drift rule rates it 0.447, and its winning
    group spans 0.93 turns instead of 4.59.
    """
    u = np.asarray(u, dtype=np.float64)
    n = len(u)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    labels, edges = _grid_adjacency(u, quad_idx, max_jump)
    n_comp = int(labels.max()) + 1
    if n_comp == 1:
        return labels

    from scipy.spatial import cKDTree

    def drift(key: str) -> float:
        ia, ib = edges[key]
        return float(np.median(u[ib] - u[ia])) if len(ia) else 0.0

    g_row, g_col = drift("row"), drift("col")
    rows = quad_idx[:, 0].astype(np.float64)
    cols = quad_idx[:, 1].astype(np.float64)
    members = [np.nonzero(labels == c)[0] for c in range(n_comp)]
    coords = [np.stack([rows[m], cols[m]], axis=-1) for m in members]
    trees = [cKDTree(c) for c in coords]

    parent = list(range(n_comp))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(n_comp):
        for b in range(a + 1, n_comp):
            if find(a) == find(b):
                continue
            dist, idx = trees[b].query(coords[a], k=1)
            k = int(np.argmin(dist))
            ia = int(members[a][k])
            ib = int(members[b][int(np.atleast_1d(idx)[k])])
            predicted = g_row * (rows[ib] - rows[ia]) + g_col * (cols[ib] - cols[ia])
            if abs((u[ib] - u[ia]) - predicted) <= max_jump:
                parent[find(a)] = find(b)
    groups = np.array([find(c) for c in range(n_comp)])
    _, compact = np.unique(groups, return_inverse=True)
    return compact[labels]


def largest_sheet_fraction(labels: np.ndarray) -> float:
    """Fraction of points on the largest sheet; 1.0 when there is nothing to
    split (a single point cannot be inconsistent with itself)."""
    if len(labels) == 0:
        return 1.0
    return float(np.bincount(labels).max() / len(labels))


def _grid_quad_normals(zyxs: np.ndarray) -> np.ndarray:
    """Unit normals per quad from the cross product of the two diagonals."""
    d1 = zyxs[1:, 1:] - zyxs[:-1, :-1]
    d2 = zyxs[:-1, 1:] - zyxs[1:, :-1]
    n = np.cross(d1.astype(np.float64), d2.astype(np.float64))
    norm = np.linalg.norm(n, axis=-1, keepdims=True)
    return n / np.maximum(norm, 1e-12)


def _quad_center_windings(winding_grid: np.ndarray) -> np.ndarray:
    """Per-quad winding value: mean of the four vertex values."""
    w = winding_grid.astype(np.float64)
    return (w[:-1, :-1] + w[1:, :-1] + w[:-1, 1:] + w[1:, 1:]) / 4.0


@dataclass
class PatchScore:
    patch_id: str
    n_points: int
    dist_p50: float
    dist_p90: float
    dist_p99: float
    dist_max: float
    frac_within_tau: float
    tau: float
    modal_winding: int
    single_winding_consistency: float
    sheet_consistency: float
    normal_angle_p50_deg: float
    normal_angle_p90_deg: float
    winding_agreement: float | None  # None when the patch has no winding grid
    n_points_unseen: int | None = None  # None when no fit inputs were provided
    _unseen_min_dist: float = DEFAULT_UNSEEN_MIN_DIST
    # per-point payload for overlays and subset aggregation (not serialized)
    point_dist: np.ndarray = field(default=None, repr=False)
    point_winding: np.ndarray = field(default=None, repr=False)
    point_zyx: np.ndarray = field(default=None, repr=False)
    point_u: np.ndarray = field(default=None, repr=False)
    point_sheet: np.ndarray = field(default=None, repr=False)
    point_normal_angle: np.ndarray = field(default=None, repr=False)
    point_input_dist: np.ndarray | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        out = {
            "patch_id": self.patch_id,
            "n_points": self.n_points,
            "dist_p50": self.dist_p50,
            "dist_p90": self.dist_p90,
            "dist_p99": self.dist_p99,
            "dist_max": self.dist_max,
            "frac_within_tau": self.frac_within_tau,
            "tau": self.tau,
            "modal_winding": self.modal_winding,
            "single_winding_consistency": self.single_winding_consistency,
            "sheet_consistency": self.sheet_consistency,
            "normal_angle_p50_deg": self.normal_angle_p50_deg,
            "normal_angle_p90_deg": self.normal_angle_p90_deg,
            "winding_agreement": self.winding_agreement,
        }
        if self.n_points_unseen is not None:
            out["n_points_unseen"] = self.n_points_unseen
            out["unseen"] = self.unseen_metrics()
        return out

    def unseen_metrics(self) -> dict | None:
        """The same per-patch numbers, restricted to the points beyond the
        leakage threshold. Published per patch so a reader can resample the
        unseen column, not only the pooled one."""
        if self.point_input_dist is None:
            return None
        mask = self.point_input_dist > self._unseen_min_dist
        n = int(mask.sum())
        if n == 0:
            return {"n_points": 0}
        d, ang = self.point_dist[mask], self.point_normal_angle[mask]
        return {
            "n_points": n,
            "dist_p50": float(np.percentile(d, 50)),
            "dist_p90": float(np.percentile(d, 90)),
            "dist_p99": float(np.percentile(d, 99)),
            "dist_max": float(d.max()),
            "frac_within_tau": float((d <= self.tau).mean()),
            "sheet_consistency": largest_sheet_fraction(self.point_sheet[mask]),
            "normal_angle_p90_deg": float(np.percentile(ang, 90)),
        }


def score_patch(
    patch: QuadSurface,
    family_soup: WindingFamilySoup,
    tau: float = DEFAULT_TAU,
    patch_id: str = "",
    z_range: tuple[float, float] | None = None,
    input_soup: TriangleSoup | None = None,
    unseen_min_dist: float = DEFAULT_UNSEEN_MIN_DIST,
) -> PatchScore:
    """Score one held-out patch against a run's winding family.

    ``z_range`` restricts scoring to quad centers inside the fitted z window:
    a run only claims to model its own window, so points outside it must not
    count against it. Patches with no point left inside are skipped upstream.

    ``input_soup`` is the union of the fit's input patch surfaces; when given,
    every point also gets its distance to that union (evidence leakage).
    """
    centers, quad_idx = patch.quad_centers()
    if len(centers) == 0:
        raise PatchSkip(f"patch {patch_id or patch.path}: no valid quad")
    if z_range is not None:
        inside = (centers[:, 0] >= z_range[0]) & (centers[:, 0] <= z_range[1])
        if not inside.any():
            raise PatchSkip(
                f"patch {patch_id or patch.path}: no quad center inside z {z_range}"
            )
        centers, quad_idx = centers[inside], quad_idx[inside]
    pts = centers.astype(np.float64)

    result = surface_distance(pts, family_soup.soup)
    assigned = family_soup.face_winding[result.face_idx]
    u = family_soup.face_u[result.face_idx]
    sheets = sheet_components(u, quad_idx)
    sheet_cons = largest_sheet_fraction(sheets)

    windings, counts = np.unique(assigned, return_counts=True)
    modal = int(windings[counts.argmax()])
    consistency = float(counts.max() / len(assigned))

    patch_normals = _grid_quad_normals(patch.zyxs)[quad_idx[:, 0], quad_idx[:, 1]]
    face_normals = family_soup.soup.face_normals()[result.face_idx]
    cosine = np.abs(np.einsum("ij,ij->i", patch_normals, face_normals)).clip(0.0, 1.0)
    angles = np.degrees(np.arccos(cosine))

    agreement = None
    if isinstance(patch.winding, np.ndarray):
        quad_w = _quad_center_windings(patch.winding)[quad_idx[:, 0], quad_idx[:, 1]]
        ok = np.isfinite(quad_w)
        if ok.sum() >= 2:
            patch_delta = np.round(quad_w[ok] - np.median(quad_w[ok]))
            assigned_delta = assigned[ok] - modal
            # Both deltas are relative; align their references via their modes.
            def mode(x):
                vals, cnts = np.unique(x, return_counts=True)
                return vals[cnts.argmax()]

            patch_delta = patch_delta - mode(patch_delta)
            assigned_delta = assigned_delta - mode(assigned_delta)
            agreement = float((patch_delta == assigned_delta).mean())

    input_dist = None
    n_unseen = None
    if input_soup is not None:
        input_dist = surface_distance(pts, input_soup).dist
        n_unseen = int((input_dist > unseen_min_dist).sum())

    dist = result.dist
    return PatchScore(
        patch_id=patch_id or (patch.path.name if patch.path else ""),
        n_points=len(pts),
        dist_p50=float(np.percentile(dist, 50)),
        dist_p90=float(np.percentile(dist, 90)),
        dist_p99=float(np.percentile(dist, 99)),
        dist_max=float(dist.max()),
        frac_within_tau=float((dist <= tau).mean()),
        tau=tau,
        modal_winding=modal,
        single_winding_consistency=consistency,
        sheet_consistency=sheet_cons,
        normal_angle_p50_deg=float(np.percentile(angles, 50)),
        normal_angle_p90_deg=float(np.percentile(angles, 90)),
        winding_agreement=agreement,
        n_points_unseen=n_unseen,
        _unseen_min_dist=unseen_min_dist,
        point_dist=dist,
        point_winding=assigned,
        point_zyx=pts,
        point_u=u,
        point_sheet=sheets,
        point_normal_angle=angles,
        point_input_dist=input_dist,
    )


def _subset_aggregate(scores: list[PatchScore], tau: float, unseen_min_dist: float) -> dict:
    """Aggregate over the points farther than ``unseen_min_dist`` from any fit
    input surface: the evidence the fit could not have seen."""
    dists, angles, patch_sheet, patch_weights = [], [], [], []
    n_excluded = 0
    for s in scores:
        mask = s.point_input_dist > unseen_min_dist
        k = int(mask.sum())
        if k < _MIN_UNSEEN_POINTS:
            n_excluded += 1
            continue
        dists.append(s.point_dist[mask])
        angles.append(s.point_normal_angle[mask])
        # Reuse the full-patch sheet labels on the subset: unseen lobes of one
        # continuous sheet stay one sheet, however far apart the subsampling
        # left them.
        patch_sheet.append(largest_sheet_fraction(s.point_sheet[mask]))
        patch_weights.append(k)  # weight by unseen points, not by patch size
    if not dists:
        return {
            "unseen_min_dist": unseen_min_dist,
            "n_patches": 0,
            "n_patches_excluded": n_excluded,
            "n_points": 0,
        }
    all_dist = np.concatenate(dists)
    all_angles = np.concatenate(angles)
    weights = np.asarray(patch_weights, dtype=np.float64)
    return {
        "unseen_min_dist": unseen_min_dist,
        "n_patches": len(dists),
        "n_patches_excluded": n_excluded,
        "n_points": int(all_dist.size),
        "dist_p50": float(np.percentile(all_dist, 50)),
        "dist_p90": float(np.percentile(all_dist, 90)),
        "dist_p99": float(np.percentile(all_dist, 99)),
        "dist_max": float(all_dist.max()),
        "frac_within_tau": float((all_dist <= tau).mean()),
        "mean_sheet_consistency": float(np.average(patch_sheet, weights=weights)),
        "min_sheet_consistency": float(min(patch_sheet)),
        "normal_angle_p90_deg": float(np.percentile(all_angles, 90)),
    }


def score_patches(
    patches: dict[str, QuadSurface],
    family: dict[int, QuadSurface],
    tau: float = DEFAULT_TAU,
    z_range: tuple[float, float] | None = None,
    input_family: dict[str, QuadSurface] | None = None,
    unseen_min_dist: float = DEFAULT_UNSEEN_MIN_DIST,
) -> tuple[list[PatchScore], dict]:
    """Score every held-out patch; return per-patch scores and aggregates.

    Aggregates are point-weighted so large patches count proportionally.
    Patches left with no point inside ``z_range`` are skipped (reported in the
    aggregate as ``n_patches_skipped``); any other failure propagates.

    ``input_family`` is the fit's input patch set. When given, the aggregate
    carries an ``evidence_leakage`` profile (how much scored evidence lies
    within touching distance of an input surface) and an ``unseen`` aggregate
    computed only on points beyond ``unseen_min_dist`` of every input.
    """
    family_soup = WindingFamilySoup.from_family(family)
    input_soup = None
    if input_family:
        vertices, faces = [], []
        offset = 0
        for surface in input_family.values():
            v, f = surface.triangles()
            vertices.append(v.astype(np.float64))
            faces.append(f + offset)
            offset += len(v)
        input_soup = TriangleSoup(np.concatenate(vertices), np.concatenate(faces))

    scores, skipped = [], []
    for pid, patch in patches.items():
        try:
            scores.append(
                score_patch(
                    patch, family_soup, tau=tau, patch_id=pid, z_range=z_range,
                    input_soup=input_soup, unseen_min_dist=unseen_min_dist,
                )
            )
        except PatchSkip:
            skipped.append(pid)
    if not scores:
        raise ValueError("no patch had a scorable point (check --z-range)")

    all_dist = np.concatenate([s.point_dist for s in scores])
    all_angles = np.concatenate([s.point_normal_angle for s in scores])
    weights = np.array([s.n_points for s in scores], dtype=np.float64)
    with_agreement = [s for s in scores if s.winding_agreement is not None]
    aggregate = {
        "n_patches": len(scores),
        "n_patches_skipped": len(skipped),
        "z_range": list(z_range) if z_range else None,
        "n_points": int(weights.sum()),
        "tau": tau,
        "dist_p50": float(np.percentile(all_dist, 50)),
        "dist_p90": float(np.percentile(all_dist, 90)),
        "dist_p99": float(np.percentile(all_dist, 99)),
        "dist_max": float(all_dist.max()),
        "frac_within_tau": float((all_dist <= tau).mean()),
        "mean_single_winding_consistency": float(
            np.average([s.single_winding_consistency for s in scores], weights=weights)
        ),
        "min_single_winding_consistency": float(
            min(s.single_winding_consistency for s in scores)
        ),
        "mean_sheet_consistency": float(
            np.average([s.sheet_consistency for s in scores], weights=weights)
        ),
        "min_sheet_consistency": float(min(s.sheet_consistency for s in scores)),
        # Pooled over points, like the distance percentiles above and like the
        # unseen block: a weighted mean of per-patch p90 is a different
        # estimator, and mixing the two across a comparison table produced a
        # spurious "inversion" in parrhesia v0.3.
        "normal_angle_p90_deg": float(np.percentile(all_angles, 90)),
        "mean_winding_agreement": (
            float(
                np.average(
                    [s.winding_agreement for s in with_agreement],
                    weights=[s.n_points for s in with_agreement],
                )
            )
            if with_agreement
            else None
        ),
    }
    if input_soup is not None:
        all_input_dist = np.concatenate([s.point_input_dist for s in scores])
        aggregate["evidence_leakage"] = {
            "n_input_patches": len(input_family),
            **{
                f"frac_within_{t:g}_vox": float((all_input_dist <= t).mean())
                for t in LEAKAGE_THRESHOLDS
            },
        }
        aggregate["unseen"] = _subset_aggregate(scores, tau, unseen_min_dist)
    return scores, aggregate
