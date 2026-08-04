"""Exercise winding agreement against real VC3D winding annotations.

The winding-agreement channel of this suite had never met a real winding label:
0 of the 4,922 PHerc. Paris 4 verified patches carry a `winding.tif`, so every
real report printed `winding agreement: not computed`. Winding evidence on this
scroll exists in another shape entirely — villa point collections, which VC3D
writes and `fit_spiral` consumes as constraints — and `spiralcheck annotations`
scores a run against them from the exported meshes alone.

This script runs that check on a real run and, when the run folder carries
villa's own `satisfied_fitted.json`, joins the two verdicts collection by
collection. That join is the point: villa scores the same constraints through
the fitted transform, on GPU, inside the fit; this suite scores them from the
meshes and the umbilicus, on CPU, afterwards. Agreement between two instruments
that share no code is the only external calibration this channel has.

It also reports the two things a bare agreement number would hide: how much of
the evidence is decidable at all (a point far from every exported surface has no
nearest winding worth reporting), and how the verdict moves when that tolerance
is relaxed.

Usage (paths are this project's; nothing here is hard-coded to them):

    python scripts/winding_annotations_real.py \
        --meshes .../meshes/fitted_quality2 \
        --pcl .../abs_winding.json --pcl .../relative_windings.json \
        --pcl .../same_windings.json \
        --umbilicus .../umbilicus.json \
        --satisfied .../satisfied_fitted.json \
        --z-range 10600,10900 --out examples/winding_annotations_real.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from spiralcheck.annotations import (
    aggregate_collection_scores,
    load_point_collections,
    score_collection,
)
from spiralcheck.io_tifxyz import load_run_windings
from spiralcheck.metrics import WindingFamilySoup

# Relaxed tolerances the headline number is checked against. tau = 6 vox is the
# protocol's; the others say whether the verdict is an artefact of that choice.
TAU_SWEEP = (2.0, 4.0, 6.0, 10.0, 20.0)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--meshes", required=True)
    p.add_argument("--pcl", required=True, action="append")
    p.add_argument("--umbilicus", required=True)
    p.add_argument("--satisfied", default=None, help="villa satisfied_fitted.json")
    p.add_argument("--variant", default="plain", choices=("spliced", "plain", "any"))
    p.add_argument("--tau", type=float, default=6.0)
    p.add_argument("--z-range", default=None)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    z_range = None
    if args.z_range:
        lo, hi = (float(v) for v in args.z_range.split(","))
        z_range = (lo, hi)

    umbilicus = json.loads(Path(args.umbilicus).read_text(encoding="utf-8"))
    family = load_run_windings(Path(args.meshes), variant=args.variant)
    soup = WindingFamilySoup.from_family(family)
    collections = load_point_collections(args.pcl)
    print(f"{len(family)} windings, {len(collections)} collections")

    scores = [
        score_collection(c, soup, umbilicus=umbilicus, tau=args.tau, z_range=z_range)
        for c in collections
    ]
    aggregate = aggregate_collection_scores(scores)

    # Sensitivity: the same verdict at other decidability tolerances. Distances
    # do not depend on tau, so this re-decides rather than re-projects.
    sweep = {}
    for tau in TAU_SWEEP:
        s = [
            score_collection(c, soup, umbilicus=umbilicus, tau=tau, z_range=z_range)
            for c in collections
        ]
        b = aggregate_collection_scores(s)["all"]
        sweep[f"{tau:g}"] = {
            "n_points_within_tau": b["n_points_within_tau"],
            "n_points_agree": b["n_points_agree"],
            "agreement": b["agreement"],
        }

    # Where the undecidable evidence sits: the z window's edges are sampled
    # thinly by the exported grids, so a point 4 vox inside the window can be
    # 15 vox from the nearest face while an identical point mid-window is not.
    z_undecidable, z_decidable = [], []
    for score, collection in zip(scores, collections, strict=True):
        if score.point_dist is None:
            continue
        zs = collection.zyx[:, 0]
        if z_range is not None:
            zs = zs[(zs >= z_range[0]) & (zs <= z_range[1])]
        ok = score.point_dist <= args.tau
        z_decidable += zs[ok].tolist()
        z_undecidable += zs[~ok].tolist()

    def z_profile(values):
        if not values:
            return None
        a = np.asarray(values)
        return {
            "n": int(a.size),
            "z_p50": float(np.percentile(a, 50)),
            "z_min": float(a.min()),
            "z_max": float(a.max()),
            "n_within_20vox_of_window_edge": (
                int(((a - z_range[0] <= 20) | (z_range[1] - a <= 20)).sum())
                if z_range
                else None
            ),
        }

    payload = {
        "meshes": str(args.meshes),
        "variant": args.variant,
        "n_windings": len(family),
        "pcl": [str(p) for p in args.pcl],
        "tau": args.tau,
        "z_range": args.z_range,
        "aggregate": aggregate,
        "tau_sweep": sweep,
        "decidability_vs_z": {
            "decidable": z_profile(z_decidable),
            "undecidable": z_profile(z_undecidable),
        },
        "collections": [s.to_dict() for s in scores],
    }

    if args.satisfied:
        payload["villa_comparison"] = compare_with_villa(
            scores, json.loads(Path(args.satisfied).read_text(encoding="utf-8"))
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(aggregate["all"], indent=2))
    print(f"wrote {out}")
    return 0


def compare_with_villa(scores, satisfied: dict) -> dict:
    """Join this suite's per-collection verdict with villa's own.

    The two are not the same measurement and must not be reported as one.
    Villa counts a point satisfied when it lies in the right winding band *and*
    within 6 scan voxels of the reprojected target, through the fitted
    transform. That conjunction merges two failures: a point on the wrong
    winding, and a point on the right winding in the wrong place. This suite
    asks only the first question, and declines to answer at all beyond tau. So
    the comparable quantity is not the fraction but the verdict: which
    collections does each instrument refuse to call clean?

    A collection this suite cannot decide is *not* counted as flagged. Silence
    and accusation are different outputs, and folding them together would
    manufacture agreement (or disagreement) that was never measured.
    """
    villa = {p["name"]: p for p in satisfied.get("pcls", [])}
    rows, undecidable = [], []
    for s in scores:
        v = villa.get(s.name)
        if v is None:
            continue
        villa_flags = v["fraction"] < 1.0
        ours_flags = s.agreement is not None and s.agreement < 1.0
        rows.append(
            {
                "name": s.name,
                "kind": s.kind,
                "villa_satisfied": v["satisfied_points"],
                "villa_total": v["total_points"],
                "villa_fraction": v["fraction"],
                "spiralcheck_agree": s.n_agree,
                "spiralcheck_decidable": s.n_within_tau,
                "spiralcheck_agreement": s.agreement,
                "spiralcheck_dist_p50": s.dist_p50,
                "villa_flags": villa_flags,
                "spiralcheck_flags": ours_flags,
                "undecidable_here": s.agreement is None,
            }
        )
        if s.agreement is None:
            undecidable.append(s.name)

    decided = [r for r in rows if not r["undecidable_here"]]
    same = [r for r in decided if r["villa_flags"] == r["spiralcheck_flags"]]
    return {
        "n_collections_compared": len(rows),
        "n_undecidable_here": len(undecidable),
        "collections_undecidable_here": sorted(undecidable),
        "n_collections_decided": len(decided),
        "n_same_flag": len(same),
        "flag_concordance": (len(same) / len(decided)) if decided else None,
        "collections_flagged_by_both": sorted(
            r["name"] for r in decided if r["villa_flags"] and r["spiralcheck_flags"]
        ),
        "collections_flagged_only_by_villa": sorted(
            r["name"] for r in decided if r["villa_flags"] and not r["spiralcheck_flags"]
        ),
        "collections_flagged_only_here": sorted(
            r["name"] for r in decided if r["spiralcheck_flags"] and not r["villa_flags"]
        ),
        "rows": sorted(rows, key=lambda r: r["villa_fraction"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
