"""Real-data null control: overlapping verified patches trace the same sheet,
so the distance from one patch's quad centers (restricted to the partner's
bounding box) to the partner's surface should be small.

Usage: uv run python scripts/real_overlap_check.py <patches_dir> [max_pairs]

Prints the distribution of median/p95 distances over sampled overlapping
pairs. Exit 1 if nothing could be checked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fitbench.geometry import TriangleSoup, surface_distance  # noqa: E402
from fitbench.io_tifxyz import load_tifxyz  # noqa: E402

CORE = ("meta.json", "x.tif", "y.tif", "z.tif")


def complete(d: Path) -> bool:
    return all((d / f).exists() for f in CORE)


def main() -> int:
    patches_dir = Path(sys.argv[1])
    max_pairs = int(sys.argv[2]) if len(sys.argv) > 2 else 150

    with_overlap = []
    for d in sorted(patches_dir.iterdir()):
        f = d / "overlapping.json"
        if d.is_dir() and f.exists() and complete(d):
            ids = json.loads(f.read_text(encoding="utf-8")).get("overlapping", [])
            if ids:
                with_overlap.append((d, ids))
    print(f"patches with a non-empty overlapping list: {len(with_overlap)}")

    rng = np.random.default_rng(0)
    rng.shuffle(with_overlap)

    med, p95, checked = [], [], 0
    for d, ids in with_overlap:
        if checked >= max_pairs:
            break
        partner_dir = None
        for pid in ids:
            cand = patches_dir / pid
            if cand.is_dir() and complete(cand):
                partner_dir = cand
                break
        if partner_dir is None:
            continue
        try:
            patch = load_tifxyz(d)
            partner = load_tifxyz(partner_dir)
        except Exception:  # noqa: BLE001
            continue
        v, f = partner.triangles()
        soup = TriangleSoup(v, f)
        centers, _ = patch.quad_centers()
        pts = centers.astype(np.float64)
        # Restrict to points inside the partner's bbox (the overlap zone),
        # with a small margin; otherwise non-overlapping area dominates.
        lo = partner.valid_zyxs.min(axis=0) - 4
        hi = partner.valid_zyxs.max(axis=0) + 4
        sel = np.all((pts >= lo) & (pts <= hi), axis=1)
        if sel.sum() < 20:
            continue
        result = surface_distance(pts[sel], soup)
        med.append(float(np.median(result.dist)))
        p95.append(float(np.percentile(result.dist, 95)))
        checked += 1

    print(f"pairs checked: {checked}")
    if not checked:
        return 1
    med_a, p95_a = np.array(med), np.array(p95)
    print(f"median distance per pair: p50 {np.percentile(med_a, 50):.2f} vox, "
          f"p90 {np.percentile(med_a, 90):.2f} vox, max {med_a.max():.2f} vox")
    print(f"p95 distance per pair:    p50 {np.percentile(p95_a, 50):.2f} vox, "
          f"p90 {np.percentile(p95_a, 90):.2f} vox, max {p95_a.max():.2f} vox")
    print(f"pairs with median <= 2 vox: {(med_a <= 2).mean() * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
