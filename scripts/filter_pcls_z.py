"""Filter a villa point-collections JSON to a z window.

Small-window fit_spiral runs pay a per-collection cost in the pure-Python
point-to-patch linking fallback, even for collections entirely outside the
fitted z range. This utility keeps only in-window points so the linking stage
scales with the window, not the scroll.

Usage:
    python filter_pcls_z.py IN.json OUT.json Z_MIN Z_MAX [--min-points N]

Points may carry 'zyx' ([z, y, x]) or 'p' ([x, y, z]); both are handled,
matching villa's reader. Collections left with fewer than --min-points points
(default 1) are dropped. All other collection metadata is preserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def point_z(point: dict) -> float:
    if "zyx" in point:
        return float(point["zyx"][0])
    return float(point["p"][2])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("z_min", type=float)
    parser.add_argument("z_max", type=float)
    parser.add_argument("--min-points", type=int, default=1)
    args = parser.parse_args()

    data = json.loads(Path(args.src).read_text(encoding="utf-8"))
    collections = data.get("collections", {})
    kept, dropped_points, dropped_collections = {}, 0, 0
    for cid, collection in collections.items():
        points = collection.get("points", {})
        in_window = {
            pid: p for pid, p in points.items()
            if args.z_min <= point_z(p) <= args.z_max
        }
        dropped_points += len(points) - len(in_window)
        if len(in_window) >= args.min_points:
            new_collection = dict(collection)
            new_collection["points"] = in_window
            kept[cid] = new_collection
        else:
            dropped_collections += 1

    out = dict(data)
    out["collections"] = kept
    Path(args.dst).parent.mkdir(parents=True, exist_ok=True)
    Path(args.dst).write_text(json.dumps(out), encoding="utf-8")
    print(
        f"{Path(args.src).name}: kept {len(kept)}/{len(collections)} collections "
        f"({dropped_collections} dropped, {dropped_points} out-of-window points removed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
