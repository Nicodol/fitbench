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
SRC = ROOT / "src" / "parrhesia"

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
     "return float((right - np.arange(len(u))).max() / len(u))",
     "return 1.0",
     "kill the sheet-consistency metric (always perfect)"),
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
     '    for rx in _FAMILY_CUTS:\n        name = rx.sub("", name)\n    return name',
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

    caught, missed = 0, []
    for filename, old, new, label in MUTATIONS:
        path = SRC / filename
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            print(f"[{filename}] SKIP (pattern count {original.count(old)}): {label}")
            missed.append(label + " (pattern not found)")
            continue
        path.write_text(original.replace(old, new), encoding="utf-8")
        try:
            rc = run_pytest()
        finally:
            path.write_text(original, encoding="utf-8")
        detected = rc != 0
        caught += detected
        print(f"[{filename}] {'DETECTED' if detected else '*** SURVIVED ***'}: {label}")
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
