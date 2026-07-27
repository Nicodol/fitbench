"""Select the tifxyz patches that overlap a z window.

Small-window spiral fits load every patch of the scroll into RAM and
triangulate them during point-to-patch linking, even when the fitted z range
covers a few hundred slices: on PHerc. Paris 4 that exhausts 62 GB. Feeding
the fit a z-filtered view of the patch directory keeps memory proportional to
the window.

Usage:
    python filter_patches_z.py SRC_DIR DST_DIR Z_MIN Z_MAX [--margin 200] [--copy]

By default DST_DIR is populated with directory junctions (no extra disk, no
admin rights needed on Windows); --copy makes real copies. The z extent comes
from meta.json's bbox when present (rows are [x, y, z]), else from z.tif.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

CORE = ("meta.json", "x.tif", "y.tif", "z.tif")


def patch_z_range(patch_dir: Path) -> tuple[float, float] | None:
    try:
        meta = json.loads((patch_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    bbox = meta.get("bbox")
    if bbox and bbox[0][2] != -1.0:
        return float(bbox[0][2]), float(bbox[1][2])
    try:
        import tifffile

        z = tifffile.imread(patch_dir / "z.tif")
    except Exception:  # noqa: BLE001 - unreadable patch, treat as unknown
        return None
    valid = z != -1.0
    if not valid.any():
        return None
    return float(z[valid].min()), float(z[valid].max())


def link_dir(src: Path, dst: Path, copy: bool) -> None:
    if dst.exists():
        return
    if copy:
        shutil.copytree(src, dst)
    elif sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            check=True, capture_output=True,
        )
    else:
        dst.symlink_to(src, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("z_min", type=float)
    parser.add_argument("z_max", type=float)
    parser.add_argument("--margin", type=float, default=200.0)
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()

    src_dir, dst_dir = Path(args.src), Path(args.dst)
    dst_dir.mkdir(parents=True, exist_ok=True)
    lo, hi = args.z_min - args.margin, args.z_max + args.margin

    total = kept = incomplete = unknown = 0
    for d in sorted(src_dir.iterdir()):
        if not d.is_dir():
            continue
        total += 1
        if not all((d / f).exists() for f in CORE):
            incomplete += 1
            continue
        extent = patch_z_range(d)
        if extent is None:
            unknown += 1
            continue
        if extent[1] >= lo and extent[0] <= hi:
            link_dir(d, dst_dir / d.name, args.copy)
            kept += 1

    print(
        f"{src_dir.name}: kept {kept}/{total} patches overlapping "
        f"z [{lo:.0f}, {hi:.0f}] ({incomplete} incomplete, {unknown} unreadable)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
