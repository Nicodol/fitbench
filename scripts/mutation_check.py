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
SRC = ROOT / "src" / "fitbench"

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
]


def run_pytest() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
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
