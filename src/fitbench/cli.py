"""Command-line interface for fitbench. See DESIGN.md for the method."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _load_patches_dir(path: Path):
    from .io_tifxyz import load_tifxyz

    patches = {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "meta.json").exists():
            patches[d.name] = load_tifxyz(d)
    if not patches:
        raise SystemExit(f"no tifxyz patch directories in {path}")
    return patches


def _load_umbilicus(spec: str | None):
    if spec is None:
        return None
    p = Path(spec)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        return data  # (K, 3) rows of [z, y, x]
    parts = [float(v) for v in spec.split(",")]
    if len(parts) == 2:
        return tuple(parts)
    raise SystemExit(f"cannot interpret umbilicus spec: {spec!r}")


def cmd_score(args) -> int:
    from .intrinsic import intrinsic_report
    from .io_tifxyz import load_run_windings
    from .metrics import score_patches
    from .report import write_report
    from .split import audit_fit_inputs

    if args.manifest and args.fit_inputs:
        offenders = audit_fit_inputs(args.manifest, args.fit_inputs)
        if offenders:
            print("REFUSED: fit inputs contain held-out patches:", file=sys.stderr)
            for o in offenders:
                print(f"  - {o}", file=sys.stderr)
            return 3

    family = load_run_windings(Path(args.meshes), variant=args.variant)
    patches = _load_patches_dir(Path(args.patches))
    scores, aggregate = score_patches(patches, family, tau=args.tau)
    intrinsic = None
    if not args.no_intrinsic and len(family) >= 2:
        intrinsic = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))
    meta = {
        "fitbench": __version__,
        "meshes": str(args.meshes),
        "patches": str(args.patches),
        "variant": args.variant,
        "n_windings": len(family),
    }
    report = write_report(
        Path(args.out), scores, aggregate, intrinsic,
        family=family, meta=meta, overlay_slices=args.overlays,
    )
    print(f"report: {report}")
    print(json.dumps(aggregate, indent=2))
    return 0


def cmd_intrinsic(args) -> int:
    from .intrinsic import intrinsic_report
    from .io_tifxyz import load_run_windings
    from .report import write_report

    family = load_run_windings(Path(args.meshes), variant=args.variant)
    rep = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))
    meta = {"fitbench": __version__, "meshes": str(args.meshes), "n_windings": len(family)}
    report = write_report(Path(args.out), None, None, rep, meta=meta, overlay_slices=0)
    print(f"report: {report}")
    print(json.dumps(rep.to_dict(), indent=2))
    return 0


def cmd_split(args) -> int:
    from .split import split_patches

    manifest = split_patches(
        Path(args.src), Path(args.out), heldout_frac=args.frac, seed=args.seed
    )
    print(json.dumps({k: manifest[k] for k in ("n_patches", "n_heldout", "seed")}, indent=2))
    return 0


def cmd_compare(args) -> int:
    from .report import compare_reports

    out = compare_reports(args.report_a, args.report_b, args.out)
    print(f"comparison: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fitbench")
    parser.add_argument("--version", action="version", version=f"fitbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    p = sub.add_parser("score", help="score a run's windings against held-out patches")
    p.add_argument("--meshes", required=True, help="run meshes dir (wNNN[_spliced] or combined)")
    p.add_argument("--patches", required=True, help="directory of held-out tifxyz patches")
    p.add_argument("--out", required=True, help="output report directory")
    p.add_argument("--tau", type=float, default=6.0, help="distance tolerance in voxels")
    p.add_argument("--variant", default="spliced", choices=["spliced", "plain", "any"])
    p.add_argument("--umbilicus", default=None, help="'y,x' constant or json polyline [z,y,x]")
    p.add_argument("--manifest", default=None, help="split_manifest.json to audit against")
    p.add_argument("--fit-inputs", default=None, help="fit input patches dir to audit")
    p.add_argument("--overlays", type=int, default=2, help="number of overlay PNG slices")
    p.add_argument("--no-intrinsic", action="store_true")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("intrinsic", help="ground-truth-free checks only")
    p.add_argument("--meshes", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--variant", default="spliced", choices=["spliced", "plain", "any"])
    p.add_argument("--umbilicus", default=None)
    p.set_defaults(func=cmd_intrinsic)

    p = sub.add_parser("split", help="seeded held-out split of a patch directory")
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frac", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=20260731)
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("compare", help="delta table between two report.json files")
    p.add_argument("report_a")
    p.add_argument("report_b")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
