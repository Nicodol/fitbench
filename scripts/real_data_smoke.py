"""Smoke test of the tifxyz loader against real verified patches.

Usage: uv run python scripts/real_data_smoke.py <patches_dir> [sample_size]

Skips directories that are not fully synced yet (missing core files), loads a
deterministic sample of the rest, and prints structure statistics. Exit code 1
if any complete directory fails to load.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fitbench.io_tifxyz import load_tifxyz  # noqa: E402

CORE = ("meta.json", "x.tif", "y.tif", "z.tif")


def main() -> int:
    patches_dir = Path(sys.argv[1])
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    dirs = sorted(d for d in patches_dir.iterdir() if d.is_dir())
    complete = [d for d in dirs if all((d / f).exists() for f in CORE)]
    print(f"directories: {len(dirs)} total, {len(complete)} complete (synced)")

    rng = np.random.default_rng(0)
    sample = [complete[i] for i in rng.choice(len(complete), min(sample_size, len(complete)), replace=False)]

    failures = []
    shapes, valid_fracs, z_spans = [], [], []
    n_mask = n_winding = n_winding_grid = 0
    for d in sample:
        try:
            s = load_tifxyz(d)
        except Exception as exc:  # noqa: BLE001
            failures.append((d.name, repr(exc)))
            continue
        shapes.append(s.zyxs.shape[:2])
        valid_fracs.append(float(s.valid_vertex_mask.mean()))
        z = s.valid_zyxs[:, 0]
        z_spans.append((float(z.min()), float(z.max())))
        if (d / "mask.tif").exists():
            n_mask += 1
        if s.winding is not None:
            n_winding += 1
            if isinstance(s.winding, np.ndarray):
                n_winding_grid += 1

    print(f"loaded: {len(shapes)}/{len(sample)} ok, {len(failures)} failures")
    for name, err in failures[:10]:
        print(f"  FAIL {name}: {err}")
    if shapes:
        hs = np.array([s[0] for s in shapes])
        ws = np.array([s[1] for s in shapes])
        vf = np.array(valid_fracs)
        z_lo = min(z[0] for z in z_spans)
        z_hi = max(z[1] for z in z_spans)
        print(f"grid rows: min {hs.min()} median {int(np.median(hs))} max {hs.max()}")
        print(f"grid cols: min {ws.min()} median {int(np.median(ws))} max {ws.max()}")
        print(f"valid fraction: p10 {np.percentile(vf, 10):.2f} median {np.median(vf):.2f}")
        print(f"z range across sample: {z_lo:.0f} .. {z_hi:.0f}")
        print(f"with mask.tif: {n_mask}, with winding: {n_winding} (grids: {n_winding_grid})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
