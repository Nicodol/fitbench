"""Planted defects in a *real* fit's output surfaces, with known answers.

The planted-defect matrix of VALIDATION.md section 2 runs on a synthetic
scroll, where the ground truth is analytic and the geometry is ideal. The
objection is obvious: nothing there proves the metrics behave on the
irregular surfaces a real ``fit_spiral`` run emits. This script answers it by
damaging a real run's meshes in known ways and rescoring the same sealed
patches, so every alarm has an answer fixed in advance.

Two things separate it from ``scripts/pitch_blindness.py``. That script moves
the *evidence* around the umbilicus; this one moves the *fit's surfaces*,
which is the defect a real fit actually presents. And it manufactures the one
piece of ground truth PHerc. Paris 4 does not ship: no verified patch carries
a ``winding.tif``, so winding agreement has never run against labelled truth
on real data. Here each sealed patch is labelled with the winding the *intact*
run assigns it, on quads where that assignment is locally unambiguous; the
planted defect then makes the fit disagree with those labels in a place known
in advance. The labels come from the reference fit, not from a human, so the
null row is 1.0 by construction: what is being tested is detection and
localization of the planted change, not whether the reference fit is right.

Each scenario below states what it is *for*. What it actually did on PHerc.
Paris 4 is VALIDATION.md section 9, and not every prediction survived: a real
fit is not an ideal spiral, and the differences are the point.

- ``null``: the intact run. Not silence — a real fit scores what it scores —
  but the reference every other row is a difference from, and a second
  scoring of the same inputs identical bit for bit.
- ``pitch_band``: every winding pushed one measured pitch outward inside a z
  band, which is what "the fit is off by one turn from here up" looks like.
  A winding family tiles space at its pitch, so the matched winding should
  drop by exactly one inside the band and hold outside it, while the distance
  percentiles move by far less than the pitch that was planted.
- ``one_winding``: the same displacement, the same z band, one winding
  instead of the family. The control that separates the two readings of "off
  by one pitch": here the sheet leaves a gap behind and doubles up on its
  neighbour, so distance is *supposed* to fire, and only on that winding's
  evidence.
- ``sheet_swap``: two adjacent windings exchange radial position inside a
  theta band, each displaced by the median pitch. Their radial order inverts,
  so the intrinsic check must fire in the planted (winding, theta) bins, and
  sheet consistency should fall on the patches crossing the band edge. The
  exchange is only as clean as the run's gap is regular: where the local gap
  is not the median, the two sheets land off each other's place and the
  distance channel sees the difference.
- ``radial_drift``: every winding displaced by ``amplitude * sin(theta)``.
  The displacement depends on theta alone, so two windings meeting at one
  (z, theta) move together and the inter-winding gaps survive: distance must
  rise while the topology counters hold (up to the bins whose theta spread
  makes the averaging inexact).
- ``hole``: one winding's vertices invalidated inside a (z, theta) box. Its
  per-winding validity must drop, nobody else's, and no crossing may be
  invented.

Every number the run prints also lands in ``--out``/planted_defects_real.json,
scenario by scenario, with the per-patch rows behind the aggregates.

    uv run python scripts/planted_defects_real.py <meshes_dir> <heldout_dir> \
        --umbilicus <umbilicus.json> --z-range 10600,10900 \
        --fit-inputs <fit_inputs_dir> --out <report_dir>

Scenarios are independent given the reference, so ``--only`` runs a subset
(after ``--only null``, which writes the reference cache the others read) and
the merged JSON is rebuilt from whatever scenario files exist. Run them one at
a time unless there is real memory to spare: a pass peaks around 5 GB on this
corpus, and five at once exhausted a 12 GB machine. Nothing is written outside
``--out``: the sealed patch directories are read-only here, and the winding
labels live in memory.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from spiralcheck.geometry import TriangleSoup
from spiralcheck.intrinsic import intrinsic_report, resolve_umbilicus
from spiralcheck.io_tifxyz import INVALID, QuadSurface, load_run_windings, load_tifxyz
from spiralcheck.metrics import WindingFamilySoup, score_patches

SCENARIOS = ("null", "pitch_band", "one_winding", "sheet_swap", "radial_drift", "hole")


# --------------------------------------------------------------------------
# Geometry: the defect injectors, all deterministic and all radial around the
# dataset umbilicus (the axis a real scroll is measured against).
# --------------------------------------------------------------------------


def _cylindrical(zyxs: np.ndarray, sel: np.ndarray, umbilicus) -> tuple[np.ndarray, ...]:
    """(radius, theta, centre, yx) of the selected vertices of a (H, W, 3) grid.

    The umbilicus is resolved at each vertex's own z, so a tilted axis is
    followed rather than averaged away.
    """
    block = zyxs[sel]
    centre = resolve_umbilicus(umbilicus, block[:, 0])
    yx = block[:, 1:] - centre
    r = np.linalg.norm(yx, axis=-1)
    theta = np.arctan2(yx[:, 0], yx[:, 1])
    return r, theta, centre, yx


def displace(
    surface: QuadSurface, umbilicus, delta: float, where: np.ndarray | None = None
) -> QuadSurface:
    """Move vertices radially away from the umbilicus by ``delta``.

    ``where`` is an optional (H, W) vertex mask; without it every valid vertex
    moves, which is exactly ``scripts/pitch_blindness.py``'s ``displace`` —
    that one applied to the held-out evidence, this one to the fit.
    """
    zyxs = surface.zyxs.astype(np.float64).copy()
    sel = surface.valid_vertex_mask
    if where is not None:
        sel = sel & where
    if sel.any():
        r, _, centre, yx = _cylindrical(zyxs, sel, umbilicus)
        block = zyxs[sel]
        block[:, 1:] = centre + yx / np.maximum(r, 1e-9)[:, None] * (r + delta)[:, None]
        zyxs[sel] = block
    return QuadSurface(zyxs.astype(np.float32), surface.scale)


def grid_row_spacing(family: dict[int, QuadSurface]) -> float:
    """Median z step between adjacent grid rows of the winding surfaces.

    Displacing a contiguous block of rows necessarily leaves one quad row at
    each band edge with two moved corners and two unmoved ones: a radial wall
    the plant does not define a winding label for. That row is one grid step
    thick, so this is the margin the exactness claim has to stand clear of.
    """
    steps = []
    for s in family.values():
        z = np.where(s.valid_vertex_mask, s.zyxs[..., 0].astype(np.float64), np.nan)
        with np.errstate(invalid="ignore"):
            rows = np.array([np.nanmean(r) if np.isfinite(r).any() else np.nan for r in z])
        rows = rows[np.isfinite(rows)]
        if len(rows) >= 2:
            steps.append(float(np.median(np.diff(rows))))
    if not steps:
        raise ValueError("no winding surface has two populated grid rows")
    return float(np.median(steps))


def _vertex_z_mask(surface: QuadSurface, z_band: tuple[float, float]) -> np.ndarray:
    z = surface.zyxs[..., 0]
    return surface.valid_vertex_mask & (z >= z_band[0]) & (z < z_band[1])


def _vertex_theta_mask(
    surface: QuadSurface, umbilicus, theta_band: tuple[float, float]
) -> np.ndarray:
    """Vertices whose angle around the umbilicus falls in a [lo, hi) band, in
    radians on ``arctan2``'s [-pi, pi) branch (no wraparound: give a band with
    lo < hi)."""
    valid = surface.valid_vertex_mask
    out = np.zeros(valid.shape, dtype=bool)
    if valid.any():
        _, theta, _, _ = _cylindrical(surface.zyxs.astype(np.float64), valid, umbilicus)
        out[valid] = (theta >= theta_band[0]) & (theta < theta_band[1])
    return out


def plant_pitch_band(family, umbilicus, pitch: float, z_band) -> dict[int, QuadSurface]:
    """Push the whole family one pitch outward inside a z band.

    Surface k lands roughly where k+1 used to be, so the winding label inside
    the band is off by one while the union of surfaces moves much less than
    the pitch. Only roughly, on a real fit: the local gap is not the median
    everywhere, the innermost and outermost surfaces move in and out of the
    modelled volume, and the band edges leave a one-grid-row radial wall. The
    step is what an accumulated-turn error looks like at its sharpest, not
    what one looks like in the wild.
    """
    return {
        wid: displace(s, umbilicus, pitch, where=_vertex_z_mask(s, z_band))
        for wid, s in family.items()
    }


def plant_sheet_swap(family, umbilicus, pitch: float, inner: int, theta_band):
    """Exchange the radial positions of windings ``inner`` and ``inner + 1``
    inside a theta band: the inner one moves out by one pitch, the outer one
    in by the same, so their radial order is inverted where the band bites."""
    outer = inner + 1
    if inner not in family or outer not in family:
        raise ValueError(f"sheet_swap needs windings {inner} and {outer} in the family")
    out = dict(family)
    out[inner] = displace(
        family[inner], umbilicus, +pitch,
        where=_vertex_theta_mask(family[inner], umbilicus, theta_band),
    )
    out[outer] = displace(
        family[outer], umbilicus, -pitch,
        where=_vertex_theta_mask(family[outer], umbilicus, theta_band),
    )
    return out


def plant_radial_drift(family, umbilicus, amplitude: float) -> dict[int, QuadSurface]:
    """r += amplitude * sin(theta) on every winding.

    The displacement depends on theta alone, so two windings meeting at the
    same (z, theta) move by the same amount and the inter-winding gaps
    survive: the intrinsic counters should barely budge. Barely, not exactly —
    a bin averages over a range of theta, and two windings do not populate
    that range identically.
    """
    out = {}
    for wid, s in family.items():
        zyxs = s.zyxs.astype(np.float64).copy()
        sel = s.valid_vertex_mask
        if sel.any():
            r, theta, centre, yx = _cylindrical(zyxs, sel, umbilicus)
            r_new = r + amplitude * np.sin(theta)
            block = zyxs[sel]
            block[:, 1:] = centre + yx / np.maximum(r, 1e-9)[:, None] * r_new[:, None]
            zyxs[sel] = block
        out[wid] = QuadSurface(zyxs.astype(np.float32), s.scale)
    return out


def plant_hole(family, umbilicus, winding: int, z_band, theta_band):
    """Invalidate one winding's vertices inside a (z, theta) box."""
    if winding not in family:
        raise ValueError(f"hole needs winding {winding} in the family")
    s = family[winding]
    sel = _vertex_z_mask(s, z_band) & _vertex_theta_mask(s, umbilicus, theta_band)
    zyxs = s.zyxs.copy()
    zyxs[sel] = INVALID
    out = dict(family)
    out[winding] = QuadSurface(zyxs, s.scale)
    return out


# --------------------------------------------------------------------------
# Bookkeeping the mutations need: degenerate faces, and the grid index behind
# each scored point.
# --------------------------------------------------------------------------


def degenerate_face_counts(soup: TriangleSoup) -> dict[str, int]:
    """Faces the distance primitive is known to over-estimate on.

    VALIDATION.md section 1: a face whose *first two* vertices coincide
    over-estimates on 47.9% of queries, and exactly collinear faces on 1.9%.
    A quad mesh produces neither unless a grid cell is pinched, and the intact
    corpus has zero of both. Moving vertices can pinch one, so every mutated
    family is recounted rather than assumed clean.
    """
    a, b, c = soup.a, soup.b, soup.c
    ab = np.all(a == b, axis=-1)
    ac = np.all(a == c, axis=-1)
    bc = np.all(b == c, axis=-1)
    collinear = np.all(np.cross(b - a, c - a) == 0.0, axis=-1) & ~(ab | ac | bc)
    return {
        "n_faces": len(soup.faces),
        "first_two_vertices_equal": int(ab.sum()),
        "other_duplicate_pair": int((ac | bc).sum()),
        "exactly_collinear": int(collinear.sum()),
    }


def violated_bins(family, umbilicus) -> set[tuple[int, float, float]]:
    """Every (inner winding, z bin, theta bin) the radial-order check flags.

    ``intrinsic_report`` publishes only its top offenders (and ``report.md``
    renders only the top ten of those), and on a real fit the pre-existing
    crossings outrank a freshly planted one, so neither table can localize a
    plant. Asking for a ``top_n`` larger than the offender count lists them
    all instead: same public function, same bins, no threshold moved.
    """
    rep = intrinsic_report(family, umbilicus=umbilicus)
    total = rep.n_violations + rep.n_collapsed + rep.n_inflated
    full = intrinsic_report(family, umbilicus=umbilicus, top_n=total + 1)
    listed = {
        (int(w["inner_winding"]), float(w["z_range"][0]), float(w["theta_range"][0]))
        for w in full.worst if w["kind"] == "violation"
    }
    if len(listed) != rep.n_violations:
        raise RuntimeError(
            f"listed {len(listed)} violated bins for {rep.n_violations} violations"
        )
    return listed


def scored_quad_index(patch: QuadSurface, z_range) -> np.ndarray:
    """The (row, col) grid index of each scored quad, in the order
    ``metrics.score_patch`` produces its per-point arrays. Recomputed rather
    than returned by the scorer, and asserted against the scorer's own point
    coordinates at the call site."""
    centers, quad_idx = patch.quad_centers()
    if z_range is not None:
        inside = (centers[:, 0] >= z_range[0]) & (centers[:, 0] <= z_range[1])
        quad_idx = quad_idx[inside]
    return quad_idx


def winding_label_grid(patch: QuadSurface, quad_idx: np.ndarray, assigned: np.ndarray):
    """The ``winding.tif`` grid PHerc. Paris 4 does not ship, built from the
    reference fit's own assignment.

    ``winding.tif`` is per vertex while the metric reads the mean of a quad's
    four corners, so a vertex is labelled only when every quad touching it was
    scored and they all agree. A quad then has four finite corners exactly
    when it sits strictly inside a constant-assignment region, and its mean is
    that constant. Everything else stays NaN, which the agreement metric skips
    — the same convention villa uses to leave the first column past a seam
    unlabelled. Returns (grid, n_labelled_quads).
    """
    h, w, _ = patch.zyxs.shape
    quads = np.full((h - 1, w - 1), np.nan)
    quads[quad_idx[:, 0], quad_idx[:, 1]] = assigned
    padded = np.pad(quads, 1, constant_values=np.nan)
    corners = np.stack(
        [padded[:h, :w], padded[:h, 1:], padded[1:, :w], padded[1:, 1:]], axis=-1
    )
    labelled = np.isfinite(corners)
    # +/-inf sentinels rather than nanmin/nanmax: an all-unlabelled vertex is
    # ordinary here, and must not raise an all-NaN-slice warning per patch.
    lo = np.where(labelled, corners, np.inf).min(axis=-1)
    hi = np.where(labelled, corners, -np.inf).max(axis=-1)
    # A padded slot is "no quad here", which is fine; an unlabelled real quad
    # is not, so a vertex is clean only when every touching quad is labelled.
    exists = np.pad(np.ones((h - 1, w - 1), dtype=bool), 1, constant_values=False)
    exists4 = np.stack(
        [exists[:h, :w], exists[:h, 1:], exists[1:, :w], exists[1:, 1:]], axis=-1
    )
    clean = np.all(labelled == exists4, axis=-1) & labelled.any(axis=-1) & (lo == hi)
    grid = np.where(clean, lo, np.nan).astype(np.float32)
    quad_mean = (grid[:-1, :-1] + grid[1:, :-1] + grid[:-1, 1:] + grid[1:, 1:]) / 4.0
    scored = np.zeros((h - 1, w - 1), dtype=bool)
    scored[quad_idx[:, 0], quad_idx[:, 1]] = True
    return grid, int((np.isfinite(quad_mean) & scored).sum())


# --------------------------------------------------------------------------
# Scoring and response extraction
# --------------------------------------------------------------------------


def _agg_row(aggregate: dict) -> dict:
    """The published aggregate fields, plus the unseen block when present."""
    keys = (
        "n_patches", "n_points", "dist_p50", "dist_p90", "dist_p99", "dist_max",
        "frac_within_tau", "mean_single_winding_consistency",
        "mean_sheet_consistency", "min_sheet_consistency",
        "normal_angle_p90_deg", "mean_winding_agreement",
    )
    out = {k: aggregate[k] for k in keys}
    for block in ("evidence_leakage", "unseen"):
        if block in aggregate:
            out[block] = aggregate[block]
    return out


def _intrinsic_row(rep) -> dict:
    d = rep.to_dict()
    return {
        k: d[k]
        for k in (
            "median_pitch", "n_bins_checked", "n_violations", "violated_bin_fraction",
            "n_collapsed", "n_inflated",
        )
    } | {"worst": d["worst"], "validity_per_winding": d["validity_per_winding"]}


def _per_patch_rows(scores) -> list[dict]:
    return [
        {
            "patch_id": s.patch_id,
            "n_points": s.n_points,
            "dist_p50": s.dist_p50,
            "dist_p90": s.dist_p90,
            "frac_within_tau": s.frac_within_tau,
            "modal_winding": s.modal_winding,
            "sheet_consistency": s.sheet_consistency,
            "single_winding_consistency": s.single_winding_consistency,
            "winding_agreement": s.winding_agreement,
        }
        for s in scores
    ]


def _payload(scores) -> dict[str, dict]:
    """Per-point arrays, keyed by patch, for the localization arithmetic."""
    return {
        s.patch_id: {
            "winding": s.point_winding,
            "dist": s.point_dist,
            "zyx": s.point_zyx,
            "sheet": s.point_sheet,
            "angle": s.point_normal_angle,
        }
        for s in scores
    }


def _identical(a: dict, b: dict) -> bool:
    """Bit-for-bit equality of two per-point payloads."""
    if set(a) != set(b):
        return False
    return all(
        np.array_equal(a[pid][k], b[pid][k]) for pid in a for k in a[pid]
    )


def _quantiles(x: np.ndarray) -> dict:
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": len(x),
        "p50": float(np.percentile(x, 50)),
        "p90": float(np.percentile(x, 90)),
        "p99": float(np.percentile(x, 99)),
        "max": float(x.max()),
    }


def _print_summary(merged: dict) -> None:
    """The whole matrix in one table, plus the line that matters per row: what
    the defect was supposed to move, and by how much it moved."""
    scen = merged["scenarios"]
    if not scen:
        return
    head = (f"\n{'scenario':>13s} {'p50':>7s} {'p99':>7s} {'<tau':>7s} {'sheet':>7s} "
            f"{'agree':>7s} {'viol':>6s} {'coll':>6s} {'infl':>6s}")
    print(head)
    print("-" * len(head.strip()))
    for name, s in scen.items():
        a, i = s["aggregate"], s["intrinsic"]
        agree = a["mean_winding_agreement"]
        print(f"{name:>13s} {a['dist_p50']:7.2f} {a['dist_p99']:7.2f} "
              f"{a['frac_within_tau'] * 100:6.1f}% {a['mean_sheet_consistency']:7.3f} "
              f"{'-' if agree is None else format(agree, '7.3f')} "
              f"{i['n_violations']:6d} {i['n_collapsed']:6d} {i['n_inflated']:6d}")

    def q(block, key="p50"):
        return "-" if not block or block.get("n", 0) == 0 else f"{block[key]:.2f}"

    def viol(r):
        """The crossing-localization counts, or dashes for a scenario file
        written before they existed: a partial --out must still print."""
        v = r.get("violated_bins") or {}
        return v.get("n_new_inside_the_plant", "?"), v.get("n_new", "?")

    print("\nwhat each planted defect did, where it was planted:")
    for name, s in scen.items():
        r = s.get("response") or {}
        if name == "null":
            rep = s["repeat"]
            lab = s["labels"]
            print(f"  null         second scoring identical bit for bit: "
                  f"{all(rep.values())}; "
                  f"{lab['n_quads_labelled']}/{lab['n_quads_scored']} scored quads "
                  f"carry an unambiguous winding label")
        elif name == "pitch_band":
            w_in = r["winding_shift_in_band"]
            w_out = r["winding_shift_outside_band"]
            print(f"  pitch_band   matched winding {w_in['frac_exactly_minus_1'] * 100:.1f}% "
                  f"exactly -1 inside the band "
                  f"({w_in['frac_exactly_minus_1_clear_of_the_edges'] * 100:.1f}% clear of "
                  f"the {r['band_edge_margin_vox']:.0f} vox edge rows), "
                  f"{w_out['frac_exactly_0'] * 100:.1f}% unchanged outside "
                  f"({w_out['frac_exactly_0_clear_of_the_edges'] * 100:.1f}% clear); "
                  f"distance p50 {q(r['reference_distance_in_band'])} -> "
                  f"{q(r['distance_in_band'])} in band")
        elif name == "one_winding":
            inside, total = viol(r)
            print(f"  one_winding  distance p50 on that winding "
                  f"{q(r['reference_distance_on_the_displaced_winding'])} -> "
                  f"{q(r['distance_on_the_displaced_winding'])}, elsewhere "
                  f"{q(r['reference_distance_elsewhere'])} -> {q(r['distance_elsewhere'])}; "
                  f"{inside}/{total} new crossings inside the planted (winding, z) bins")
        elif name == "sheet_swap":
            t = r["patches_touching_the_swap"]
            drops = [x for x in t if x["sheet_consistency_now"] < x["sheet_consistency_ref"]]
            inside, total = viol(r)
            print(f"  sheet_swap   {inside}/{total} new crossings "
                  f"inside the planted (winding, theta) bins "
                  f"({r['worst_violations_inside_the_plant']}/"
                  f"{r['worst_violations_listed']} of the twenty the JSON's "
                  f"offender list carries, of which report.md renders ten); "
                  f"{len(drops)}/{len(t)} patches on the swapped pair lost sheet "
                  f"consistency; distance p50 "
                  f"{q(r['reference_distance_all_points'])} -> "
                  f"{q(r['distance_all_points'])}")
        elif name == "radial_drift":
            ivr = s.get("intrinsic_vs_reference") or {}
            moved = [
                f"{k} {ivr[k][0]}->{ivr[k][1]}"
                for k in ("n_violations", "n_collapsed", "n_inflated")
                if k in ivr and ivr[k][0] != ivr[k][1]
            ]
            print(f"  radial_drift distance p50 {q(r['reference_distance_all_points'])} -> "
                  f"{q(r['distance_all_points'])}; topology counters "
                  f"{'all held' if not moved else 'moved: ' + ', '.join(moved)}")
        elif name == "hole":
            moved = (s.get("intrinsic_vs_reference") or {}).get(
                "windings_whose_validity_changed", []
            )
            print(f"  hole         distance p50 over the hole "
                  f"{q(r['reference_distance_on_the_hole'])} -> "
                  f"{q(r['distance_on_the_hole'])}, elsewhere "
                  f"{q(r['reference_distance_elsewhere'])} -> {q(r['distance_elsewhere'])}; "
                  f"{len(moved)} winding(s) lost validity")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("meshes", nargs="?", help="run meshes dir (not needed with --merge-only)")
    p.add_argument("heldout", nargs="?", help="sealed patches dir (idem)")
    p.add_argument("--out", required=True, help="directory for the scenario JSONs")
    p.add_argument("--umbilicus", default=None)
    p.add_argument("--fit-inputs", default=None)
    p.add_argument("--variant", default="spliced", choices=["spliced", "plain", "any"])
    p.add_argument("--z-range", default=None)
    p.add_argument("--tau", type=float, default=6.0)
    p.add_argument("--unseen-min-dist", type=float, default=2.0)
    p.add_argument("--pitch", type=float, default=None,
                   help="winding pitch in voxels (default: the run's own median)")
    p.add_argument("--defect-z-band", default="10700,10800",
                   help="z band of the pitch_band defect")
    p.add_argument("--defect-theta-band", default="30,90",
                   help="theta band of the sheet_swap defect, degrees in [-180, 180)")
    p.add_argument("--hole-z-band", default="10650,10750")
    p.add_argument("--hole-theta-band", default="-150,-90")
    p.add_argument("--drift-amplitude", type=float, default=3.0)
    p.add_argument("--only", action="append", choices=SCENARIOS,
                   help="run a subset (repeatable); 'null' must have run first")
    p.add_argument("--merge-only", action="store_true",
                   help="rebuild the merged JSON from existing scenario files and stop")
    args = p.parse_args(argv)

    def pair(spec: str) -> tuple[float, float]:
        lo, hi = (float(v) for v in spec.split(","))
        if lo >= hi:
            raise SystemExit(f"error: expected 'lo,hi' with lo < hi, got {spec!r}")
        return lo, hi

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "reference_cache.npz"
    umbilicus = None
    if args.umbilicus:
        umbilicus = json.loads(Path(args.umbilicus).read_text(encoding="utf-8"))
    z_range = pair(args.z_range) if args.z_range else None
    z_band = pair(args.defect_z_band)
    theta_band = tuple(np.radians(pair(args.defect_theta_band)))
    hole_z = pair(args.hole_z_band)
    hole_theta = tuple(np.radians(pair(args.hole_theta_band)))
    wanted = list(args.only) if args.only else list(SCENARIOS)
    meta_path = out_dir / "meta.json"

    def merge() -> int:
        merged = {
            "meta": json.loads(meta_path.read_text(encoding="utf-8")),
            "scenarios": {},
        }
        for name in SCENARIOS:
            path = out_dir / f"scenario_{name}.json"
            if path.exists():
                merged["scenarios"][name] = json.loads(path.read_text(encoding="utf-8"))
        merged_path = out_dir / "planted_defects_real.json"
        merged_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        _print_summary(merged)
        print(f"\nmerged: {merged_path} "
              f"({len(merged['scenarios'])}/{len(SCENARIOS)} scenarios)")
        return 0

    if args.merge_only:
        return merge()
    if not args.meshes or not args.heldout:
        raise SystemExit("error: meshes and heldout are required unless --merge-only")

    t0 = time.time()
    family = load_run_windings(Path(args.meshes), variant=args.variant)
    patches = {
        d.name: load_tifxyz(d)
        for d in sorted(Path(args.heldout).iterdir())
        if d.is_dir() and (d / "meta.json").exists()
    }
    input_family = None
    if args.fit_inputs:
        input_family = {
            d.name: load_tifxyz(d)
            for d in sorted(Path(args.fit_inputs).iterdir())
            if d.is_dir() and (d / "meta.json").exists()
        }
    # The intrinsic block, read for two things: the run's own median pitch,
    # and how tightly its inter-winding gap clusters around that median. The
    # second comes from moving the collapsed/inflated thresholds to +/-25%;
    # the median itself is computed before any threshold is applied, so it is
    # the same number the default call reports. A displacement of exactly the
    # median pitch lands winding k on winding k+1 only where the local gap is
    # close to that median, so this is the ceiling the pitch_band scenario's
    # "exactly -1" fraction has to be read against.
    spread = intrinsic_report(
        family, umbilicus=umbilicus, collapse_frac=0.75, inflate_frac=1.25
    )
    pitch = args.pitch or spread.median_pitch
    within_quarter = (
        spread.n_bins_checked - spread.n_violations - spread.n_collapsed - spread.n_inflated
    )
    # That subtraction is only a count of the bins in the middle if the three
    # kinds partition the bins, i.e. if "collapsed" really does exclude the
    # crossings. Put the thresholds back to back and the three must add up to
    # every bin; if they ever double-count, this number would quietly shrink
    # by the crossing count instead of failing.
    partition = intrinsic_report(
        family, umbilicus=umbilicus, collapse_frac=1.25, inflate_frac=1.25
    )
    counted = partition.n_violations + partition.n_collapsed + partition.n_inflated
    if counted != partition.n_bins_checked:
        raise RuntimeError(
            f"the intrinsic offender kinds do not partition the bins "
            f"({counted} vs {partition.n_bins_checked}); the gap-spread "
            f"statistic would be wrong"
        )
    meta_path.write_text(json.dumps({
        "meshes": str(args.meshes), "heldout": str(args.heldout),
        "fit_inputs": args.fit_inputs, "variant": args.variant,
        "tau": args.tau, "z_range": list(z_range) if z_range else None,
        "unseen_min_dist": args.unseen_min_dist if args.fit_inputs else None,
        "umbilicus": args.umbilicus, "measured_pitch_vox": pitch,
        "n_windings": len(family), "n_patches": len(patches),
        "gap_bins_checked": spread.n_bins_checked,
        "gap_bins_within_25pc_of_the_median_pitch": within_quarter,
        "frac_gap_bins_within_25pc_of_the_median_pitch":
            within_quarter / spread.n_bins_checked,
        "defect_z_band": list(z_band), "defect_theta_band_deg": pair(args.defect_theta_band),
        "hole_z_band": list(hole_z), "hole_theta_band_deg": pair(args.hole_theta_band),
        "drift_amplitude_vox": args.drift_amplitude,
    }, indent=2), encoding="utf-8")
    print(
        f"{len(family)} winding surfaces (w{min(family):03d}..w{max(family):03d}), "
        f"{len(patches)} sealed patches, "
        f"{0 if input_family is None else len(input_family)} fit inputs, "
        f"pitch {pitch:.4f} vox  [{time.time() - t0:.0f}s]",
        flush=True,
    )

    def run(name: str, fam: dict[int, QuadSurface], pats: dict[str, QuadSurface]):
        t = time.time()
        scores, aggregate = score_patches(
            pats, fam, tau=args.tau, z_range=z_range,
            input_family=input_family, unseen_min_dist=args.unseen_min_dist,
        )
        rep = intrinsic_report(fam, umbilicus=umbilicus)
        soup = WindingFamilySoup.from_family(fam).soup
        print(f"  scored {name} in {time.time() - t:.0f}s", flush=True)
        return scores, aggregate, rep, degenerate_face_counts(soup)

    # ---------------- reference: the intact run, and the labels it yields ---
    quad_index = {pid: scored_quad_index(pt, z_range) for pid, pt in patches.items()}

    if "null" in wanted:
        bare_scores, _, _, _ = run("null (unlabelled pass, builds the labels)", family, patches)
        labels, n_labelled = {}, {}
        for s in bare_scores:
            pt = patches[s.patch_id]
            idx = quad_index[s.patch_id]
            centers, _ = pt.quad_centers()
            if z_range is not None:
                centers = centers[
                    (centers[:, 0] >= z_range[0]) & (centers[:, 0] <= z_range[1])
                ]
            if not np.array_equal(centers, s.point_zyx):
                raise RuntimeError(f"{s.patch_id}: quad index does not match the scorer")
            grid, n_ok = winding_label_grid(pt, idx, s.point_winding)
            labels[s.patch_id] = grid
            n_labelled[s.patch_id] = n_ok
        np.savez_compressed(
            cache_path,
            **{f"label__{k}": v for k, v in labels.items()},
            **{f"refwind__{s.patch_id}": s.point_winding for s in bare_scores},
            **{f"refdist__{s.patch_id}": s.point_dist for s in bare_scores},
            **{f"refzyx__{s.patch_id}": s.point_zyx for s in bare_scores},
            **{f"refsheet__{s.patch_id}": s.point_sheet for s in bare_scores},
            n_labelled=np.array([n_labelled[s.patch_id] for s in bare_scores]),
            patch_ids=np.array([s.patch_id for s in bare_scores]),
            pitch=np.array([pitch]),
        )
    if not cache_path.exists():
        raise SystemExit(f"error: {cache_path} missing; run --only null first")
    cache = np.load(cache_path, allow_pickle=False)
    pitch = float(cache["pitch"][0]) if args.pitch is None else pitch
    patch_ids = [str(v) for v in cache["patch_ids"]]
    labels = {pid: cache[f"label__{pid}"] for pid in patch_ids}
    ref = {
        pid: {
            "winding": cache[f"refwind__{pid}"],
            "dist": cache[f"refdist__{pid}"],
            "zyx": cache[f"refzyx__{pid}"],
            "sheet": cache[f"refsheet__{pid}"],
        }
        for pid in patch_ids
    }
    n_labelled = dict(zip(patch_ids, (int(v) for v in cache["n_labelled"])))

    # The labelled patches: same geometry, plus the manufactured winding grid.
    labelled = {
        pid: QuadSurface(
            zyxs=pt.zyxs, scale=pt.scale, path=pt.path, uuid=pt.uuid,
            winding=labels[pid], winding_column_ranges=pt.winding_column_ranges,
            component_winding_ids=pt.component_winding_ids,
        )
        for pid, pt in patches.items()
    }

    # Where the evidence sits, in the coordinates the defects are planted in.
    geom = {}
    for pid in patch_ids:
        zyx = ref[pid]["zyx"]
        centre = resolve_umbilicus(umbilicus, zyx[:, 0])
        yx = zyx[:, 1:] - centre
        geom[pid] = {
            "z": zyx[:, 0],
            "theta": np.arctan2(yx[:, 0], yx[:, 1]),
            "radius": np.linalg.norm(yx, axis=-1),
        }

    def write(name: str, block: dict) -> None:
        (out_dir / f"scenario_{name}.json").write_text(
            json.dumps(block, indent=2, sort_keys=False), encoding="utf-8"
        )
        print(f"  wrote {out_dir / f'scenario_{name}.json'}", flush=True)

    # ---------------- scenarios --------------------------------------------
    # The null needs a second block because the labels it publishes come out of
    # the pass above, and every scenario below has to be scored against the
    # same labelled patches.
    if "null" in wanted:
        scores_a, agg_a, rep_a, deg_a = run("null pass A", family, labelled)
        scores_b, agg_b, rep_b, deg_b = run("null pass B", family, labelled)
        same_points = _identical(_payload(scores_a), _payload(scores_b))
        half_integer = []
        for s in scores_a:
            grid = labels[s.patch_id]
            qm = (grid[:-1, :-1] + grid[1:, :-1] + grid[:-1, 1:] + grid[1:, 1:]) / 4.0
            idx = quad_index[s.patch_id]
            vals = qm[idx[:, 0], idx[:, 1]]
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 2 and float(np.median(vals)) % 1.0 == 0.5:
                half_integer.append(s.patch_id)
        write("null", {
            "plant": {"kind": "none (null control)"},
            "aggregate": _agg_row(agg_a),
            "intrinsic": _intrinsic_row(rep_a),
            "degenerate_faces": deg_a,
            "per_patch": _per_patch_rows(scores_a),
            "labels": {
                "n_patches_labelled": int(sum(1 for v in n_labelled.values() if v >= 2)),
                "n_quads_labelled": int(sum(n_labelled.values())),
                "n_quads_scored": int(sum(len(quad_index[p]) for p in patch_ids)),
                "patches_with_half_integer_median": half_integer,
            },
            "repeat": {
                "per_point_payload_identical": bool(same_points),
                "aggregates_identical": agg_a == agg_b,
                "intrinsic_identical": rep_a.to_dict() == rep_b.to_dict(),
                "degenerate_identical": deg_a == deg_b,
            },
        })

    null_path = out_dir / "scenario_null.json"
    ref_intrinsic = (
        json.loads(null_path.read_text(encoding="utf-8"))["intrinsic"]
        if null_path.exists() else None
    )

    def _intrinsic_vs_reference(rep) -> dict | None:
        """What the ground-truth-free block did, against the intact run's own.

        The bin census is not a counter: vertices sit on theta bin edges, and
        float32 storage moves a handful across after any displacement. The
        counters (violations, collapsed, inflated) are the ones a scenario's
        prediction is about — some plants are meant to move them.
        """
        if ref_intrinsic is None:
            return None
        now = _intrinsic_row(rep)
        moved = [
            {"winding": int(w), "reference": ref_intrinsic["validity_per_winding"][w],
             "now": now["validity_per_winding"][w]}
            for w in ref_intrinsic["validity_per_winding"]
            if ref_intrinsic["validity_per_winding"][w] != now["validity_per_winding"][w]
        ]
        return {
            k: [ref_intrinsic[k], now[k]]
            for k in ("median_pitch", "n_bins_checked", "n_violations",
                      "n_collapsed", "n_inflated")
        } | {"windings_whose_validity_changed": moved}

    reference_bins = violated_bins(family, umbilicus)

    def localize_violations(fam, inside) -> dict:
        """Where the radial-order check gained and lost crossings, against the
        intact run's own. ``inside`` decides whether a bin is in the plant."""
        now = violated_bins(fam, umbilicus)
        new = now - reference_bins
        return {
            "n_violated_bins_reference": len(reference_bins),
            "n_violated_bins_now": len(now),
            "n_new": len(new),
            "n_disappeared": len(reference_bins - now),
            "n_new_inside_the_plant": sum(1 for b in new if inside(b)),
            "n_new_outside_the_plant": sum(1 for b in new if not inside(b)),
        }

    def response(name: str, scores, aggregate, rep, deg, plant: dict, extra: dict) -> None:
        by_id = {s.patch_id: s for s in scores}
        for pid in patch_ids:
            if len(by_id[pid].point_dist) != len(ref[pid]["dist"]):
                raise RuntimeError(f"{pid}: scored point count changed under {name}")
        write(name, {
            "plant": plant,
            "aggregate": _agg_row(aggregate),
            "intrinsic": _intrinsic_row(rep),
            "intrinsic_vs_reference": _intrinsic_vs_reference(rep),
            "degenerate_faces": deg,
            "per_patch": _per_patch_rows(scores),
            "response": extra,
        })

    if "pitch_band" in wanted:
        fam = plant_pitch_band(family, umbilicus, pitch, z_band)
        scores, agg, rep, deg = run("pitch_band", fam, labelled)
        by_id = {s.patch_id: s for s in scores}
        d_w, d_d, inb = [], [], []
        for pid in patch_ids:
            d_w.append(by_id[pid].point_winding - ref[pid]["winding"])
            d_d.append(by_id[pid].point_dist)
            inb.append((geom[pid]["z"] >= z_band[0]) & (geom[pid]["z"] < z_band[1]))
        d_w = np.concatenate(d_w)
        d_d = np.concatenate(d_d)
        inb = np.concatenate(inb)
        ref_d = np.concatenate([ref[pid]["dist"] for pid in patch_ids])
        # Stand clear of the one-quad-row wall the band edges necessarily
        # create: inside it the plant defines no winding, so counting it
        # either way would be reading noise as signal.
        margin = grid_row_spacing(family)
        all_z = np.concatenate([geom[pid]["z"] for pid in patch_ids])
        clear = (np.abs(all_z - z_band[0]) > margin) & (np.abs(all_z - z_band[1]) > margin)
        straddle = [
            pid for pid in patch_ids
            if 0 < ((geom[pid]["z"] >= z_band[0]) & (geom[pid]["z"] < z_band[1])).mean() < 1
        ]
        agree = {s.patch_id: s.winding_agreement for s in scores}
        response("pitch_band", scores, agg, rep, deg, {
            "kind": "whole family displaced +1 pitch inside a z band",
            "pitch_vox": pitch, "z_band": list(z_band),
        }, {
            "n_points_in_band": int(inb.sum()),
            "band_edge_margin_vox": margin,
            "winding_shift_in_band": {
                "median": float(np.median(d_w[inb])),
                "frac_exactly_minus_1": float((d_w[inb] == -1).mean()),
                "n_clear_of_the_edges": int((inb & clear).sum()),
                "frac_exactly_minus_1_clear_of_the_edges": float(
                    (d_w[inb & clear] == -1).mean()
                ),
            },
            "winding_shift_outside_band": {
                "median": float(np.median(d_w[~inb])),
                "frac_exactly_0": float((d_w[~inb] == 0).mean()),
                "n_clear_of_the_edges": int(((~inb) & clear).sum()),
                "frac_exactly_0_clear_of_the_edges": float(
                    (d_w[(~inb) & clear] == 0).mean()
                ),
            },
            "distance_in_band": _quantiles(d_d[inb]),
            "distance_outside_band": _quantiles(d_d[~inb]),
            "reference_distance_in_band": _quantiles(ref_d[inb]),
            "reference_distance_outside_band": _quantiles(ref_d[~inb]),
            "violated_bins": localize_violations(
                fam, lambda b: z_band[0] <= b[1] < z_band[1]
            ),
            "n_patches_straddling_a_band_edge": len(straddle),
            "winding_agreement_straddling": [
                {"patch_id": pid, "agreement": agree[pid],
                 "frac_points_in_band": float(
                     ((geom[pid]["z"] >= z_band[0]) & (geom[pid]["z"] < z_band[1])).mean()
                 )}
                for pid in straddle
            ],
            "winding_agreement_not_straddling": [
                {"patch_id": pid, "agreement": agree[pid]}
                for pid in patch_ids if pid not in straddle
            ],
        })

    if "one_winding" in wanted:
        inb = {
            pid: (geom[pid]["z"] >= z_band[0]) & (geom[pid]["z"] < z_band[1])
            for pid in patch_ids
        }
        band_w = np.concatenate([ref[pid]["winding"][inb[pid]] for pid in patch_ids])
        if len(band_w) == 0:
            raise SystemExit("error: no sealed evidence inside --defect-z-band")
        counts = np.bincount(band_w.astype(np.int64), minlength=max(family) + 1)
        target = int(counts.argmax())
        fam = dict(family)
        fam[target] = displace(
            family[target], umbilicus, pitch,
            where=_vertex_z_mask(family[target], z_band),
        )
        scores, agg, rep, deg = run(f"one_winding (w{target:03d})", fam, labelled)
        by_id = {s.patch_id: s for s in scores}
        on_target = np.concatenate(
            [(ref[pid]["winding"] == target) & inb[pid] for pid in patch_ids]
        )
        d_w = np.concatenate(
            [by_id[pid].point_winding - ref[pid]["winding"] for pid in patch_ids]
        )
        d_d = np.concatenate([by_id[pid].point_dist for pid in patch_ids])
        ref_d = np.concatenate([ref[pid]["dist"] for pid in patch_ids])
        response("one_winding", scores, agg, rep, deg, {
            "kind": "one winding displaced +1 pitch inside the same z band",
            "winding": target, "pitch_vox": pitch, "z_band": list(z_band),
            "n_reference_points_on_that_winding_in_band": int(on_target.sum()),
        }, {
            "distance_on_the_displaced_winding": _quantiles(d_d[on_target]),
            "reference_distance_on_the_displaced_winding": _quantiles(ref_d[on_target]),
            "distance_elsewhere": _quantiles(d_d[~on_target]),
            "reference_distance_elsewhere": _quantiles(ref_d[~on_target]),
            "winding_shift_on_the_displaced_winding": {
                "frac_unchanged": float((d_w[on_target] == 0).mean()),
                "median": float(np.median(d_w[on_target])),
            },
            "winding_shift_elsewhere": {
                "frac_unchanged": float((d_w[~on_target] == 0).mean()),
            },
            # A sheet pushed onto its outer neighbour inverts that one pair,
            # in the z rows it was pushed in, at any theta.
            "violated_bins": localize_violations(
                fam, lambda b: b[0] == target and z_band[0] - 1e-9 <= b[1] < z_band[1]
            ),
        })

    if "sheet_swap" in wanted:
        # Plant the swap where the sealed evidence actually is: the adjacent
        # winding pair carrying the most reference points inside the theta
        # band. Chosen from the reference, so it is fixed before scoring.
        in_theta = {
            pid: (geom[pid]["theta"] >= theta_band[0]) & (geom[pid]["theta"] < theta_band[1])
            for pid in patch_ids
        }
        band_w = np.concatenate([ref[pid]["winding"][in_theta[pid]] for pid in patch_ids])
        counts = np.bincount(band_w.astype(np.int64), minlength=max(family) + 2)
        pair_counts = {
            w: int(counts[w] + counts[w + 1])
            for w in sorted(family) if w + 1 in family
        }
        inner = max(pair_counts, key=lambda w: (pair_counts[w], -w))
        fam = plant_sheet_swap(family, umbilicus, pitch, inner, theta_band)
        scores, agg, rep, deg = run(f"sheet_swap (w{inner:03d}/w{inner + 1:03d})", fam, labelled)
        by_id = {s.patch_id: s for s in scores}
        ref_sheet = {
            pid: float(np.bincount(ref[pid]["sheet"]).max() / len(ref[pid]["sheet"]))
            for pid in patch_ids
        }
        touched = []
        for pid in patch_ids:
            hit = in_theta[pid] & np.isin(ref[pid]["winding"], (inner, inner + 1))
            if hit.any():
                touched.append({
                    "patch_id": pid,
                    "n_points_on_swapped_pair_in_band": int(hit.sum()),
                    "frac_of_patch": float(hit.mean()),
                    "sheet_consistency_ref": ref_sheet[pid],
                    "sheet_consistency_now": by_id[pid].sheet_consistency,
                    "dist_p50_ref": _quantiles(ref[pid]["dist"])["p50"],
                    "dist_p50_now": by_id[pid].dist_p50,
                })
        worst = rep.to_dict()["worst"]
        in_plant = [
            w for w in worst
            if w["kind"] == "violation"
            and w["inner_winding"] == inner
            and w["theta_range"][0] >= theta_band[0] - 1e-9
            and w["theta_range"][1] <= theta_band[1] + 1e-9
        ]
        d_d = np.concatenate([by_id[pid].point_dist for pid in patch_ids])
        ref_d = np.concatenate([ref[pid]["dist"] for pid in patch_ids])
        response("sheet_swap", scores, agg, rep, deg, {
            "kind": "two adjacent windings exchange radial position in a theta band",
            "inner_winding": inner, "outer_winding": inner + 1,
            "theta_band_deg": [float(np.degrees(t)) for t in theta_band],
            "displacement_vox": pitch,
            "n_reference_points_on_the_pair_in_band": int(
                sum(t["n_points_on_swapped_pair_in_band"] for t in touched)
            ),
        }, {
            "patches_touching_the_swap": touched,
            # The exchanged pair, in the theta bins the band bites. A bin's
            # theta_range[0] is its lower edge, so a bin is inside the plant
            # when that edge sits in the band.
            "violated_bins": localize_violations(
                fam,
                lambda b: b[0] == inner and theta_band[0] - 1e-9 <= b[2] < theta_band[1],
            ),
            "worst_violations_inside_the_plant": len(in_plant),
            "worst_violations_listed": len(
                [w for w in worst if w["kind"] == "violation"]
            ),
            "distance_all_points": _quantiles(d_d),
            "reference_distance_all_points": _quantiles(ref_d),
            # keyed by the inner winding of each adjacent pair: why this one
            # was picked, and how much evidence the runners-up carried.
            "points_per_adjacent_pair_in_band": {
                str(w): pair_counts[w] for w in sorted(pair_counts)
                if pair_counts[w] > 0
            },
        })

    if "radial_drift" in wanted:
        fam = plant_radial_drift(family, umbilicus, args.drift_amplitude)
        scores, agg, rep, deg = run("radial_drift", fam, labelled)
        by_id = {s.patch_id: s for s in scores}
        d_d = np.concatenate([by_id[pid].point_dist for pid in patch_ids])
        ref_d = np.concatenate([ref[pid]["dist"] for pid in patch_ids])
        theta = np.concatenate([geom[pid]["theta"] for pid in patch_ids])
        near_zero = np.abs(np.sin(theta)) < 0.25
        response("radial_drift", scores, agg, rep, deg, {
            "kind": "r += amplitude * sin(theta) on every winding",
            "amplitude_vox": args.drift_amplitude,
        }, {
            "distance_all_points": _quantiles(d_d),
            "reference_distance_all_points": _quantiles(ref_d),
            "distance_where_sin_theta_small": _quantiles(d_d[near_zero]),
            "reference_distance_where_sin_theta_small": _quantiles(ref_d[near_zero]),
            "distance_where_sin_theta_large": _quantiles(d_d[~near_zero]),
            "reference_distance_where_sin_theta_large": _quantiles(ref_d[~near_zero]),
            # Nothing is planted in the topology here, so every bin counts as
            # outside: the two "new" columns are the false-alarm count.
            "violated_bins": localize_violations(fam, lambda b: False),
        })

    if "hole" in wanted:
        box = {
            pid: (
                (geom[pid]["z"] >= hole_z[0]) & (geom[pid]["z"] < hole_z[1])
                & (geom[pid]["theta"] >= hole_theta[0])
                & (geom[pid]["theta"] < hole_theta[1])
            )
            for pid in patch_ids
        }
        in_box_w = np.concatenate([ref[pid]["winding"][box[pid]] for pid in patch_ids])
        if len(in_box_w) == 0:
            raise SystemExit("error: no sealed evidence inside --hole-z-band/--hole-theta-band")
        counts = np.bincount(in_box_w.astype(np.int64), minlength=max(family) + 1)
        target = int(counts.argmax())
        fam = plant_hole(family, umbilicus, target, hole_z, hole_theta)
        scores, agg, rep, deg = run(f"hole (w{target:03d})", fam, labelled)
        by_id = {s.patch_id: s for s in scores}
        on_target = np.concatenate(
            [(ref[pid]["winding"] == target) & box[pid] for pid in patch_ids]
        )
        d_d = np.concatenate([by_id[pid].point_dist for pid in patch_ids])
        ref_d = np.concatenate([ref[pid]["dist"] for pid in patch_ids])
        response("hole", scores, agg, rep, deg, {
            "kind": "one winding's vertices invalidated inside a (z, theta) box",
            "winding": target, "z_band": list(hole_z),
            "theta_band_deg": [float(np.degrees(t)) for t in hole_theta],
            "n_reference_points_in_the_box_on_that_winding": int(on_target.sum()),
        }, {
            "distance_on_the_hole": _quantiles(d_d[on_target]),
            "reference_distance_on_the_hole": _quantiles(ref_d[on_target]),
            "distance_elsewhere": _quantiles(d_d[~on_target]),
            "reference_distance_elsewhere": _quantiles(ref_d[~on_target]),
            # Removing material must not invent a crossing anywhere.
            "violated_bins": localize_violations(fam, lambda b: False),
        })

    return merge()


if __name__ == "__main__":
    sys.exit(main())
