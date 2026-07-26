"""Held-out metrics: score patches the fit never saw against its winding family.

Every metric is computed at patch quad centers (matching the granularity of
villa's satisfaction metrics, for comparability), against the union of the
run's winding surfaces:

- surface distance percentiles and fraction within ``tau``;
- single-winding consistency: one physical patch must land on one winding;
- winding-number agreement, when the patch carries a ``winding.tif`` grid;
- normal agreement (sign-agnostic angle between patch and matched face).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import TriangleSoup, surface_distance
from .io_tifxyz import QuadSurface

DEFAULT_TAU = 6.0  # scan voxels; matches satisfaction_distance_tolerance for comparability


@dataclass
class WindingFamilySoup:
    """All winding surfaces of a run merged into one queryable soup."""

    soup: TriangleSoup
    face_winding: np.ndarray  # (M,) winding id per face
    winding_ids: list[int]

    @classmethod
    def from_family(cls, family: dict[int, QuadSurface]) -> "WindingFamilySoup":
        if not family:
            raise ValueError("empty winding family")
        vertices, faces, face_wids = [], [], []
        offset = 0
        for wid in sorted(family):
            v, f = family[wid].triangles()
            vertices.append(v.astype(np.float64))
            faces.append(f + offset)
            face_wids.append(np.full(len(f), wid, dtype=np.int64))
            offset += len(v)
        soup = TriangleSoup(np.concatenate(vertices), np.concatenate(faces))
        return cls(soup=soup, face_winding=np.concatenate(face_wids), winding_ids=sorted(family))


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
    normal_angle_p50_deg: float
    normal_angle_p90_deg: float
    winding_agreement: float | None  # None when the patch has no winding grid
    # per-point payload for overlays (not serialized)
    point_dist: np.ndarray = field(repr=False)
    point_winding: np.ndarray = field(repr=False)
    point_zyx: np.ndarray = field(repr=False)

    def to_dict(self) -> dict:
        return {
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
            "normal_angle_p50_deg": self.normal_angle_p50_deg,
            "normal_angle_p90_deg": self.normal_angle_p90_deg,
            "winding_agreement": self.winding_agreement,
        }


def score_patch(
    patch: QuadSurface,
    family_soup: WindingFamilySoup,
    tau: float = DEFAULT_TAU,
    patch_id: str = "",
) -> PatchScore:
    centers, quad_idx = patch.quad_centers()
    if len(centers) == 0:
        raise ValueError(f"patch {patch_id or patch.path}: no valid quad")
    pts = centers.astype(np.float64)

    result = surface_distance(pts, family_soup.soup)
    assigned = family_soup.face_winding[result.face_idx]

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
        normal_angle_p50_deg=float(np.percentile(angles, 50)),
        normal_angle_p90_deg=float(np.percentile(angles, 90)),
        winding_agreement=agreement,
        point_dist=dist,
        point_winding=assigned,
        point_zyx=pts,
    )


def score_patches(
    patches: dict[str, QuadSurface],
    family: dict[int, QuadSurface],
    tau: float = DEFAULT_TAU,
) -> tuple[list[PatchScore], dict]:
    """Score every held-out patch; return per-patch scores and aggregates.

    Aggregates are point-weighted so large patches count proportionally.
    """
    family_soup = WindingFamilySoup.from_family(family)
    scores = [score_patch(p, family_soup, tau=tau, patch_id=pid) for pid, p in patches.items()]

    all_dist = np.concatenate([s.point_dist for s in scores])
    weights = np.array([s.n_points for s in scores], dtype=np.float64)
    agreements = [s.winding_agreement for s in scores if s.winding_agreement is not None]
    aggregate = {
        "n_patches": len(scores),
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
        "normal_angle_p90_deg": float(
            np.average([s.normal_angle_p90_deg for s in scores], weights=weights)
        ),
        "mean_winding_agreement": (float(np.mean(agreements)) if agreements else None),
    }
    return scores, aggregate
