"""Is the difference between two runs bigger than the luck of the draw?

A held-out score depends on which patches happened to be held out. This
resamples the scored patches with replacement (the same selection applied to
both runs, so the comparison stays paired), recomputes each point-weighted
aggregate, and reports percentile intervals for each run and for the
difference. An interval on the difference that spans zero means the two runs
are not separated by that metric on this evidence, whatever the point
estimates look like.

    uv run python scripts/bootstrap_ci.py report_a/report.json report_b/report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

METRICS = (
    "sheet_consistency",
    "single_winding_consistency",
    "dist_p50",
    "frac_within_tau",
    "normal_angle_p90_deg",
)


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "heldout_patches" not in data:
        raise SystemExit(f"{path}: no per-patch scores (was it an intrinsic-only report?)")
    return {r["patch_id"]: r for r in data["heldout_patches"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report_a")
    p.add_argument("report_b")
    p.add_argument("--draws", type=int, default=20000)
    p.add_argument("--seed", type=int, default=20260731)
    args = p.parse_args(argv)

    a_by_id, b_by_id = load(Path(args.report_a)), load(Path(args.report_b))
    shared = sorted(set(a_by_id) & set(b_by_id))
    if not shared:
        raise SystemExit("the two reports share no patch")
    if len(shared) != len(a_by_id) or len(shared) != len(b_by_id):
        print(f"note: comparing the {len(shared)} shared patches "
              f"({len(a_by_id)} and {len(b_by_id)} scored)")
    print(f"bootstrap over {len(shared)} patches, {args.draws} paired draws")
    print("values are point-weighted means of PER-PATCH numbers; for a "
          "percentile metric that is\nthe mean of per-patch percentiles, which "
          "is not the pooled percentile the report\npublishes. Read this table "
          "for the direction and the stability of a gap, not as a\nrestatement "
          "of the headline aggregates.\n")

    a_w = np.array([a_by_id[k]["n_points"] for k in shared], dtype=np.float64)
    b_w = np.array([b_by_id[k]["n_points"] for k in shared], dtype=np.float64)
    rng = np.random.default_rng(args.seed)
    idx = rng.integers(0, len(shared), size=(args.draws, len(shared)))

    print(f"{'metric':30s} {'A':>19s} {'B':>19s} {'A - B':>21s}")
    for m in METRICS:
        if m not in a_by_id[shared[0]]:
            continue
        a_v = np.array([a_by_id[k][m] for k in shared], dtype=np.float64)
        b_v = np.array([b_by_id[k][m] for k in shared], dtype=np.float64)
        a_boot = (a_v[idx] * a_w[idx]).sum(1) / a_w[idx].sum(1)
        b_boot = (b_v[idx] * b_w[idx]).sum(1) / b_w[idx].sum(1)
        d = a_boot - b_boot
        a_lo, a_hi = np.percentile(a_boot, [2.5, 97.5])
        b_lo, b_hi = np.percentile(b_boot, [2.5, 97.5])
        d_lo, d_hi = np.percentile(d, [2.5, 97.5])
        a_pt = float(np.average(a_v, weights=a_w))
        b_pt = float(np.average(b_v, weights=b_w))
        note = "" if (d_lo > 0) == (d_hi > 0) else "  spans zero"
        print(f"{m:30s} {a_pt:7.3f} [{a_lo:6.3f},{a_hi:6.3f}]"
              f" {b_pt:7.3f} [{b_lo:6.3f},{b_hi:6.3f}]"
              f" {a_pt - b_pt:7.3f} [{d_lo:6.3f},{d_hi:6.3f}]{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
