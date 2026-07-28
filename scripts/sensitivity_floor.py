"""The smallest planted defect each metric actually catches.

DESIGN.md's validation plan asks for a sensitivity floor, and a reader is
entitled to ask "how small a defect would this have missed?". For each defect
class, sweep its magnitude upward on the synthetic fixture and report the
first magnitude whose metric leaves the null-control band. The band is the
clean value plus a margin derived from the fixture's own chordal
discretization, so the floor is a property of the metric, not of a
hand-picked threshold.

    uv run python scripts/sensitivity_floor.py
"""

from __future__ import annotations

import numpy as np

from parrhesia.intrinsic import intrinsic_report
from parrhesia.io_tifxyz import QuadSurface
from parrhesia.metrics import WindingFamilySoup, score_patch, score_patches
from parrhesia.synthetic import (
    collapse_gap,
    make_family,
    radial_drift,
    sample_patch,
    swap_band,
)

PITCH = 10.0


def family():
    return make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)


def heldout():
    z = (8.0, 52.0)
    return {
        "p11": sample_patch(11, PITCH, (0.4, 1.6), z),
        "p13": sample_patch(13, PITCH, (2.0, 3.4), z),
        "p14": sample_patch(14, PITCH, (4.0, 5.5), z),
    }


def chordal_bound(patches, fam):
    """Worst-case null-control distance: patch grid and family triangulation
    are two chordal approximations of the same smooth spiral."""
    bound = 0.0
    theta_count = next(iter(fam.values())).zyxs.shape[1]
    for p in patches.values():
        r = np.linalg.norm(p.valid_zyxs[:, 1:], axis=-1).max()
        cols = p.zyxs.shape[1]
        first, last = p.zyxs[0, 0, 1:], p.zyxs[0, -1, 1:]
        arc = np.arccos(
            np.clip(np.dot(first, last) / (np.linalg.norm(first) * np.linalg.norm(last)), -1, 1)
        )
        sag_patch = (r * arc / (cols - 1)) ** 2 / (8 * r)
        sag_family = (2 * np.pi * r / theta_count) ** 2 / (8 * r)
        bound = max(bound, sag_patch + sag_family)
    return bound


def floor_radial_drift():
    fam, held = family(), heldout()
    limit_slack = 2.0 * chordal_bound(held, fam)
    _, null = score_patches(held, fam)
    limit = null["dist_p99"] + limit_slack
    for amp in np.arange(0.1, 4.01, 0.1):
        _, agg = score_patches(held, radial_drift(fam, amplitude=float(amp)))
        if agg["dist_p99"] > limit:
            return float(amp), f"dist_p99 {agg['dist_p99']:.2f} > {limit:.2f} vox"
    return None, "not detected up to 4 vox"


def floor_sheet_swap():
    fam = family()
    patch = sample_patch(11, PITCH, (0.5, 2.5), (8.0, 52.0), cols=40)
    null = score_patch(patch, WindingFamilySoup.from_family(fam), patch_id="p").sheet_consistency
    for width in np.arange(0.05, 1.51, 0.05):
        swapped = swap_band(fam, 11, 12, theta_band=(1.0, 1.0 + float(width)))
        s = score_patch(patch, WindingFamilySoup.from_family(swapped), patch_id="p")
        if s.sheet_consistency < null - 0.02:
            frac = width / (2.5 - 0.5)
            return float(width), (f"sheet consistency {s.sheet_consistency:.3f} "
                                  f"({frac * 100:.0f}% of the patch span swapped)")
    return None, "not detected up to 1.5 rad"


def floor_gap_collapse_intrinsic():
    fam = family()
    null = intrinsic_report(fam).n_collapsed
    for factor in np.arange(0.05, 0.96, 0.05):
        rep = intrinsic_report(collapse_gap(fam, 12, theta_band=(3.0, 4.0), factor=float(factor)))
        if rep.n_collapsed > null:
            return float(factor), (f"{rep.n_collapsed} collapsed bins "
                                   f"(gap left at {(1 - factor) * 100:.0f}% of nominal)")
    return None, "not detected up to 95% collapse"


def floor_gap_collapse_distance():
    fam = family()
    patch = sample_patch(12, PITCH, (3.1, 3.9), (8.0, 52.0))
    soup = WindingFamilySoup.from_family(fam)
    null = score_patch(patch, soup, patch_id="p").dist_p50
    limit = null + 2.0 * chordal_bound({"p": patch}, fam)
    for factor in np.arange(0.05, 0.96, 0.05):
        collapsed = collapse_gap(fam, 12, theta_band=(3.0, 4.0), factor=float(factor))
        s = score_patch(patch, WindingFamilySoup.from_family(collapsed), patch_id="p")
        if s.dist_p50 > limit:
            return float(factor), (f"dist_p50 {s.dist_p50:.2f} > {limit:.2f} vox "
                                   f"({factor * PITCH:.1f} vox of displacement)")
    return None, "not detected up to 95% collapse"


def floor_normal_tilt():
    fam = family()
    base = sample_patch(12, PITCH, (0.5, 1.5), (8.0, 52.0), rows=8, cols=12)
    soup = WindingFamilySoup.from_family(fam)
    null = score_patch(base, soup, patch_id="p").normal_angle_p50_deg
    for amp in np.arange(0.05, 2.01, 0.05):
        zyxs = base.zyxs.astype(np.float64)
        radial = zyxs[..., 1:] / np.linalg.norm(zyxs[..., 1:], axis=-1, keepdims=True)
        sign = float(amp) * (-1.0) ** np.arange(zyxs.shape[0])
        zyxs[..., 1:] = zyxs[..., 1:] + radial * sign[:, None, None]
        s = score_patch(QuadSurface(zyxs.astype(np.float32), base.scale), soup, patch_id="p")
        if s.normal_angle_p50_deg > null + 5.0:
            return float(amp), f"angle p50 {s.normal_angle_p50_deg:.1f} deg (null {null:.1f})"
    return None, "not detected up to 2 vox"


CHECKS = [
    ("radial drift (vox)", floor_radial_drift),
    ("swapped band width (rad)", floor_sheet_swap),
    ("gap collapse, held-out distance", floor_gap_collapse_distance),
    ("gap collapse, intrinsic label", floor_gap_collapse_intrinsic),
    ("row tilt amplitude (vox)", floor_normal_tilt),
]


def main() -> int:
    print(f"Sensitivity floors on the synthetic fixture (pitch {PITCH:.0f} vox)\n")
    for name, fn in CHECKS:
        value, why = fn()
        got = f"{value:.2f}" if value is not None else "none"
        print(f"{name:34s} floor {got:>6s}   {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
