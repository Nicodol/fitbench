"""Why a distance-only evaluation cannot judge a scroll fit, measured.

A winding family fills space at the pitch: every point inside the modelled
region is within half a pitch of *some* sheet. So a surface that is one full
winding out of place is still close to something, and any metric that reduces
to "how far is the evidence from the nearest surface" is blind to it. That is
not a corner case, it is the characteristic failure of scroll fitting.

This is a control with a known answer, run on real data: displace the
held-out evidence radially around the true umbilicus by a measured multiple
of the run's own pitch, rescore against the real fitted surfaces, and report
what each metric does. The distance percentiles should barely move; the
winding the evidence is matched to should move by exactly the number of
pitches applied.

    uv run python scripts/pitch_blindness.py <meshes_dir> <heldout_dir> \
        --umbilicus <umbilicus.json> --z-range 10600,10900
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from spiralcheck.intrinsic import intrinsic_report, resolve_umbilicus
from spiralcheck.io_tifxyz import QuadSurface, load_run_windings, load_tifxyz
from spiralcheck.metrics import score_patches


def displace(surface: QuadSurface, umbilicus, delta: float) -> QuadSurface:
    """Move every valid vertex radially away from the umbilicus by ``delta``."""
    zyxs = surface.zyxs.astype(np.float64).copy()
    valid = surface.valid_vertex_mask
    centre = resolve_umbilicus(umbilicus, zyxs[..., 0][valid])
    block = zyxs[valid]
    yx = block[:, 1:] - centre
    r = np.linalg.norm(yx, axis=-1, keepdims=True)
    block[:, 1:] = centre + yx / np.maximum(r, 1e-9) * (r + delta)
    zyxs[valid] = block
    return QuadSurface(zyxs.astype(np.float32), surface.scale)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("meshes")
    p.add_argument("heldout")
    p.add_argument("--umbilicus", default=None)
    p.add_argument("--variant", default="spliced", choices=["spliced", "plain", "any"])
    p.add_argument("--z-range", default=None)
    p.add_argument("--pitch", type=float, default=None,
                   help="winding pitch in voxels (default: the run's own median)")
    args = p.parse_args(argv)

    umbilicus = None
    if args.umbilicus:
        umbilicus = json.loads(Path(args.umbilicus).read_text(encoding="utf-8"))
    z_range = None
    if args.z_range:
        lo, hi = (float(v) for v in args.z_range.split(","))
        z_range = (lo, hi)

    family = load_run_windings(Path(args.meshes), variant=args.variant)
    patches = {d.name: load_tifxyz(d) for d in sorted(Path(args.heldout).iterdir())
               if d.is_dir() and (d / "meta.json").exists()}
    pitch = args.pitch or intrinsic_report(family, umbilicus=umbilicus).median_pitch
    print(f"{len(family)} winding surfaces, {len(patches)} held-out patches, "
          f"pitch {pitch:.2f} vox\n")

    scores, base = score_patches(patches, family, z_range=z_range)
    base_modal = {s.patch_id: s.modal_winding for s in scores}

    print(f"{'displacement':>26s} {'dist p50':>9s} {'dist p99':>9s} {'within tau':>11s} "
          f"{'winding shift':>14s}")
    print(f"{'none (reference)':>26s} {base['dist_p50']:9.2f} {base['dist_p99']:9.2f} "
          f"{base['frac_within_tau'] * 100:10.1f}% {'-':>14s}")

    rows = []
    for turns in (0.5, 1.0, 2.0):
        delta = turns * pitch
        moved = {k: displace(v, umbilicus, delta) for k, v in patches.items()}
        s2, agg = score_patches(moved, family, z_range=z_range)
        shift = float(np.median([x.modal_winding - base_modal[x.patch_id] for x in s2]))
        label = f"{turns:g} pitch ({delta:.1f} vox)"
        print(f"{label:>26s} {agg['dist_p50']:9.2f} {agg['dist_p99']:9.2f} "
              f"{agg['frac_within_tau'] * 100:10.1f}% {shift:+14.1f}")
        rows.append((turns, agg["dist_p50"], agg["frac_within_tau"], shift))

    d50 = max(abs(r[1] - base["dist_p50"]) for r in rows)
    tau = max(abs(r[2] - base["frac_within_tau"]) for r in rows)
    whole = [r for r in rows if r[0] in (1.0, 2.0)]
    ok_shift = all(abs(r[3] - r[0]) < 0.25 for r in whole)
    print(f"\ndistance p50 never moves by more than {d50:.2f} vox and within-tau by more "
          f"than {tau * 100:.1f} points,\nwhile the matched winding follows the "
          f"displacement exactly: {'yes' if ok_shift else 'NO'}")
    print("A distance-only evaluation cannot see a whole-pitch error. Winding identity can,\n"
          "and measuring it without the fit's own transform is the point of this suite.")
    return 0 if ok_shift else 1


if __name__ == "__main__":
    raise SystemExit(main())
