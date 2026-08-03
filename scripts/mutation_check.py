"""Mutation audit: inject deliberate bugs one at a time and require the test
suite to fail on every one of them (and to pass unmutated).

This is the test of the tests: a suite that stays green while the geometry
sign is flipped, the axes are scrambled, or an alarm is disabled would be
worthless. Run from the repo root:

    uv run python scripts/mutation_check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "spiralcheck"

MUTATIONS = [
    ("geometry.py", "    ab = b - a\n", "    ab = a - b\n",
     "flip the edge vector sign in closest-point-on-triangle"),
    ("geometry.py", "radii = ub + soup.r_max + 1e-9", "radii = ub * 0.0 + 1e-9",
     "break the exactness bound of the KD-tree candidate radius"),
    ("io_tifxyz.py", "return v[:-1, :-1] & v[1:, :-1] & v[:-1, 1:] & v[1:, 1:]",
     "return v[:-1, :-1] | v[1:, :-1] | v[:-1, 1:] | v[1:, 1:]",
     "treat quads with invalid corners as valid"),
    ("io_tifxyz.py", 'for coord in "zyx"', 'for coord in "xyz"',
     "scramble the z/y/x axis order at load time"),
    ("metrics.py", "frac_within_tau=float((dist <= tau).mean())",
     "frac_within_tau=float((dist >= tau).mean())",
     "invert the within-tolerance comparison"),
    ("intrinsic.py", "violations = gaps_arr <= 0.0", "violations = gaps_arr <= -1e9",
     "disable the sheet-crossing alarm"),
    ("intrinsic.py", "theta = np.arctan2(yx[:, 0], yx[:, 1])",
     "theta = np.arctan2(yx[:, 1], yx[:, 0])",
     "swap the angle convention used to localize defects"),
    ("split.py", 'side = "heldout" if i in heldout_idx else "fit"', 'side = "fit"',
     "never actually hold out any patch"),
    # The next batch answers the 2026-07-28 external test-quality review: every
    # one of these survived the suite as it was, so each now has a dedicated test.
    ("metrics.py",
     'cosine = np.abs(np.einsum("ij,ij->i", patch_normals, face_normals)).clip(0.0, 1.0)',
     "cosine = np.ones(len(patch_normals))",
     "kill the normal-agreement metric (angle always zero)"),
    ("metrics.py",
     ('"mean_single_winding_consistency": float(\n'
      "            np.average([s.single_winding_consistency for s in scores], weights=weights)\n"
      "        ),"),
     '"mean_single_winding_consistency": 0.0,',
     "replace the published consistency aggregate by a constant"),
    ("metrics.py",
     ('        "tau": tau,\n'
      '        "dist_p50": float(np.percentile(all_dist, 50)),\n'
      '        "dist_p90": float(np.percentile(all_dist, 90)),'),
     ('        "tau": tau,\n'
      '        "dist_p50": float(np.percentile(all_dist, 50)),\n'
      '        "dist_p90": 0.0,'),
     "replace the published dist_p90 aggregate by a constant"),
    ("metrics.py",
     "[s.winding_agreement for s in with_agreement],",
     "[0.0 for s in with_agreement],",
     "replace the winding-agreement aggregate by a constant"),
    ("metrics.py",
     "smooth = np.abs(u[ia] - u[ib]) <= max_jump",
     "smooth = np.abs(u[ia] - u[ib]) <= 1e9",
     "kill the sheet-consistency metric (every neighbor counts as smooth)"),
    ("metrics.py",
     "mask = s.point_input_dist > unseen_min_dist",
     "mask = s.point_input_dist < unseen_min_dist",
     "invert the unseen-evidence selection"),
    ("metrics.py",
     'f"frac_within_{t:g}_vox": float((all_input_dist <= t).mean())',
     'f"frac_within_{t:g}_vox": float((all_input_dist >= t).mean())',
     "invert the evidence-leakage fractions"),
    ("cli.py",
     "z_range = (parts[0], parts[1])",
     "z_range = (parts[1], parts[0])",
     "swap min and max in the CLI --z-range parsing"),
    ("geometry.py", "_EPS = 1e-12", "_EPS = 1e-3",
     "widen the degeneracy guard by nine orders of magnitude"),
    ("intrinsic.py",
     "inflated = gaps_arr > inflate_frac * median_pitch",
     "inflated = gaps_arr > 1e18",
     "kill the inflated-gap indicator"),
    ("intrinsic.py",
     "yx = pts[:, 1:] - umb[zi]",
     "yx = pts[:, 1:]",
     "ignore the umbilicus when computing radii"),
    ("split.py",
     ('    while True:\n'
      '        before = name\n'
      '        for rx in _FAMILY_CUTS:\n'
      '            stripped = rx.sub("", name)\n'
      '            if stripped:  # never let a cut empty the name\n'
      '                name = stripped\n'
      '        if name == before:\n'
      '            return name'),
     "    return name",
     "disable the family grouping (siblings may straddle the split)"),
    ("split.py",
     '_GEOMETRY_FILES = ("x.tif", "y.tif", "z.tif", "mask.tif", "winding.tif")',
     '_GEOMETRY_FILES = ("meta.json", "x.tif", "y.tif", "z.tif", "mask.tif", "winding.tif")',
     "let a metadata rewrite change the geometry hash (audit evasion)"),
    ("split.py",
     'for meta in sorted(root.rglob("meta.json")):',
     'for meta in sorted(root.glob("meta.json")):',
     "make the audit scan non-recursive (nested copies invisible)"),
    ("io_tifxyz.py",
     "block = surface.zyxs[:, j0 : min(j1 + 1, width)]",
     "block = surface.zyxs[:, j0:j1]",
     "drop the shared-seam column when splitting a combined surface"),
    # Batch three, answering the 2026-07-28 late review of v0.2: fifteen
    # counter-mutations survived that suite; each now has a dedicated test.
    ("metrics.py",
     "    dist = result.dist\n    return PatchScore(",
     "    dist = result.dist * 0.9\n    return PatchScore(",
     "shrink every published distance by 10 percent, consistently"),
    ("metrics.py",
     "np.average([s.sheet_consistency for s in scores], weights=weights)",
     "np.average([s.sheet_consistency for s in scores], weights=None)",
     "drop the point-weighting of the sheet-consistency aggregate"),
    ("metrics.py",
     "np.average([s.single_winding_consistency for s in scores], weights=weights)",
     "np.average([s.single_winding_consistency for s in scores], weights=None)",
     "drop the point-weighting of the raw consistency aggregate"),
    ("metrics.py",
     '"min_sheet_consistency": float(min(s.sheet_consistency for s in scores)),',
     '"min_sheet_consistency": float(max(s.sheet_consistency for s in scores)),',
     "report the max as the min sheet consistency"),
    ("metrics.py",
     "        except PatchSkip:",
     "        except Exception:",
     "silently fold any engine error into the skip count"),
    ("metrics.py",
     ("        for surface in input_family.values():\n"
      "            v, f = surface.triangles()\n"
      "            vertices.append(v.astype(np.float64))\n"
      "            faces.append(f + offset)"),
     ("        for surface in input_family.values():\n"
      "            v, f = surface.triangles()\n"
      "            vertices.append(v.astype(np.float64))\n"
      "            faces.append(f)"),
     "break the fit-input soup past the first input (leakage understated)"),
    ("metrics.py",
     "frac_within_tau=float((dist <= tau).mean()),",
     "frac_within_tau=float((dist <= DEFAULT_TAU).mean()),",
     "ignore tau in the per-patch fraction"),
    ("metrics.py",
     "_MIN_UNSEEN_POINTS = 8",
     "_MIN_UNSEEN_POINTS = 1",
     "lower the unseen-points exclusion floor to 1"),
    ("metrics.py",
     "LEAKAGE_THRESHOLDS = (0.5, 1.0, 2.0, 6.0)",
     "LEAKAGE_THRESHOLDS = (2.0,)",
     "drop three of the four published leakage-profile thresholds"),
    ("split.py",
     "picked = fam_keys[block[int(rng.integers(0, len(block)))]]",
     "picked = fam_keys[block[0]]",
     "ignore the seed: always hold out the lowest-z family of each window"),
    ("split.py",
     "        return (bbox[0][2] + bbox[1][2]) / 2.0  # bbox rows are xyz; z is index 2",
     "        return (bbox[0][0] + bbox[1][0]) / 2.0  # bbox rows are xyz; z is index 2",
     "stratify on x instead of z"),
    ("split.py",
     "            if other != k:\n                merged_key[k] = other",
     "            if other != k:\n                pass",
     "disable the geometry-hash family merge (twins may straddle)"),
    ("cli.py",
     "        intrinsic = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))",
     "        intrinsic = intrinsic_report(family, umbilicus=None)",
     "drop the --umbilicus plumbing in the score command"),
    ("cli.py",
     "            input_family=input_family, unseen_min_dist=args.unseen_min_dist,",
     "            input_family=input_family, unseen_min_dist=2.0,",
     "hardcode the unseen threshold, making the flag decorative"),
    ("cli.py",
     "                return 5",
     "                return 0",
     "accept unloadable fit inputs without refusing"),
    # Batch four, answering the 2026-07-29 review of v0.3: the rewritten
    # sheet metric and the unseen block had almost no mutation coverage, and
    # both reviewers found surviving counter-mutations there.
    ("metrics.py",
     '    for key, (da, db) in (("row", (1, 0)), ("col", (0, 1))):',
     '    for key, (da, db) in (("col", (0, 1)),):',
     "drop row adjacency from the sheet graph"),
    ("metrics.py",
     '        edges[key] = (ia[smooth], ib[smooth])',
     ('        edges[key] = (ia[smooth][:0], ib[smooth][:0]) if key == "col" '
      'else (ia[smooth], ib[smooth])'),
     "drop column adjacency from the sheet graph"),
    ("metrics.py",
     "            if abs((u[ib] - u[ia]) - predicted) <= max_jump:",
     "            if True:",
     "merge every pair of sheet components unconditionally"),
    ("metrics.py",
     "            if abs((u[ib] - u[ia]) - predicted) <= max_jump:",
     "            if False:",
     "never merge sheet components across a hole"),
    ("metrics.py",
     "        return float(np.median(u[ib] - u[ia])) if len(ia) else 0.0",
     "        return 0.0",
     "ignore the patch's own u-drift when bridging holes"),
    ("metrics.py",
     ("        patch_sheet.append(largest_sheet_fraction(s.point_sheet[mask]))\n"
      "        patch_weights.append(k)  # weight by unseen points, not by patch size"),
     ("        patch_sheet.append(largest_sheet_fraction(s.point_sheet[mask]))\n"
      "        patch_weights.append(s.n_points)"),
     "weight the unseen aggregate by patch size instead of unseen points"),
    ("metrics.py",
     '        "min_sheet_consistency": float(min(patch_sheet)),',
     '        "min_sheet_consistency": float(max(patch_sheet)),',
     "report the max as the min in the unseen aggregate"),
    ("metrics.py",
     ('        "frac_within_tau": float((all_dist <= tau).mean()),\n'
      '        "mean_sheet_consistency": float(np.average(patch_sheet, weights=weights)),'),
     ('        "frac_within_tau": float((all_dist <= DEFAULT_TAU).mean()),\n'
      '        "mean_sheet_consistency": float(np.average(patch_sheet, weights=weights)),'),
     "ignore tau in the unseen aggregate"),
    ("metrics.py",
     ('        "normal_angle_p90_deg": float(np.percentile(all_angles, 90)),\n'
      '        "mean_winding_agreement": ('),
     ('        "normal_angle_p90_deg": float(\n'
      '            np.average([s.normal_angle_p90_deg for s in scores], weights=weights)\n'
      "        ),\n"
      '        "mean_winding_agreement": ('),
     "mix estimators: per-patch mean p90 in the main aggregate, pooled in unseen"),
    ("metrics.py",
     "        dist_p99=float(np.percentile(dist, 99)),",
     "        dist_p99=float(np.percentile(dist, 90)),",
     "publish p90 as p99 in the per-patch table"),
    # Deliberately NOT in this list, and why (a mutation the suite cannot
    # kill would inflate the score without proving anything):
    #   - removing `other = resolve(other)` in the geometry-hash merge is an
    #     equivalent mutant in every reachable configuration, because
    #     `resolve` already follows chains; it only differs by admitting a
    #     cycle that the surrounding code cannot construct.
    #   - disabling the split self-check cannot change any output: the hash
    #     merge makes a poisoned split unreachable by construction, which is
    #     exactly why the check is a tripwire on that construction and not a
    #     recoverable branch.
    ("split.py",
     "    n_blocks = max(1, round(len(order) * heldout_frac))",
     "    n_blocks = max(1, round(len(order) * heldout_frac / 2))",
     "hold out half the requested family fraction"),
    ("split.py",
     "            if stripped:  # never let a cut empty the name",
     "            if True:  # never let a cut empty the name",
     "let a family key reduce to the empty string"),
    ("cli.py",
     '        audit_meta["manifest_n_heldout"] = n_heldout',
     '        audit_meta["manifest_n_heldout"] = 0',
     "publish a constant manifest held-out count"),
    ("cli.py",
     '            audit_meta["fit_inputs_load_errors"] = len(input_errors)',
     '            audit_meta["fit_inputs_load_errors"] = 1',
     "report every batch of unloadable inputs as a single error"),
    ("report.py",
     "    if scores is not None:",
     "    if scores is not None and False:",
     "stop purging stale overlays"),
    ("report.py",
     '                    ["winding agreement", _winding_agreement_cell(aggregate)],',
     '                    ["winding agreement", str(aggregate["mean_winding_agreement"])],',
     "render a missing winding-agreement metric as a bare None again"),
]


def run_pytest() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, check=False,  # non-zero is the signal here
    )
    return proc.returncode


def main() -> int:
    print("control run (no mutation): ", end="", flush=True)
    rc = run_pytest()
    print("PASS" if rc == 0 else f"FAIL (rc={rc})")
    if rc != 0:
        print("aborting: the unmutated suite must pass first")
        return 1

    total = len(MUTATIONS)
    print(f"{total} mutations, one full pytest run each: expect several "
          "minutes (a few seconds per run on a desktop CPU)")
    caught, missed = 0, []
    for i, (filename, old, new, label) in enumerate(MUTATIONS, start=1):
        path = SRC / filename
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            print(f"[{i}/{total}] [{filename}] SKIP (pattern count {original.count(old)}): {label}")
            missed.append(label + " (pattern not found)")
            continue
        path.write_text(original.replace(old, new), encoding="utf-8")
        try:
            rc = run_pytest()
        finally:
            path.write_text(original, encoding="utf-8")
        detected = rc != 0
        caught += detected
        print(f"[{i}/{total}] [{filename}] {'DETECTED' if detected else '*** SURVIVED ***'}: {label}")
        if not detected:
            missed.append(label)

    print(f"\n{caught}/{len(MUTATIONS)} mutations detected by the suite")
    if missed:
        print("NOT DETECTED:")
        for label in missed:
            print(f"  - {label}")
        return 1
    print("final control run: ", end="", flush=True)
    rc = run_pytest()
    print("PASS" if rc == 0 else f"FAIL (rc={rc})")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
