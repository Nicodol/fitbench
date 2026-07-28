"""Command-line interface for parrhesia. See DESIGN.md for the method."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _load_patches_dir(path: Path) -> tuple[dict, dict[str, str]]:
    """Load every tifxyz child directory; collect per-patch load errors instead
    of letting one corrupted directory (e.g. a partial sync) abort the run."""
    from .io_tifxyz import load_tifxyz

    patches, errors = {}, {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "meta.json").exists():
            try:
                patches[d.name] = load_tifxyz(d)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors[d.name] = f"{type(exc).__name__}: {exc}"
                print(f"warning: could not load patch {d.name}: {exc}", file=sys.stderr)
    if not patches:
        raise SystemExit(f"no loadable tifxyz patch directory in {path}")
    return patches, errors


def _load_umbilicus(spec: str | None):
    if spec is None:
        return None
    p = Path(spec)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        return data  # villa umbilicus.json, or (K, 3) rows of [z, y, x]
    parts = [float(v) for v in spec.split(",")]
    if len(parts) == 2:
        return tuple(parts)
    raise SystemExit(f"cannot interpret umbilicus spec: {spec!r}")


def cmd_score(args) -> int:
    from .intrinsic import intrinsic_report
    from .io_tifxyz import load_run_windings
    from .metrics import score_patches
    from .report import write_report
    from .split import audit_fit_inputs, audit_scored_patches

    if args.tau <= 0:
        raise SystemExit(f"--tau must be positive, got {args.tau}")

    audit_meta: dict = {}
    if args.manifest:
        try:
            unlisted, listed, n_heldout = audit_scored_patches(args.manifest, args.patches)
        except (NotADirectoryError, FileNotFoundError) as exc:
            raise SystemExit(str(exc)) from exc
        # Directory counts, not scored counts: the aggregate's n_patches and
        # n_patches_skipped say how many of these were actually scored.
        audit_meta["patches_dir_listed_in_manifest"] = listed
        audit_meta["manifest_n_heldout"] = n_heldout
        if listed < n_heldout:
            print(
                f"note: --patches offers {listed} of the manifest's {n_heldout} "
                "held-out patches (a z window legitimately restricts this; a "
                "cherry-pick would look the same, so the counts are recorded "
                "in the report).",
                file=sys.stderr,
            )
        if unlisted and not args.allow_unlisted_patches:
            print(
                "REFUSED: --patches contains directories that are not the "
                "manifest's held-out side (scoring the fit's own inputs under "
                "a held-out label?):",
                file=sys.stderr,
            )
            for name in unlisted[:20]:
                print(f"  - {name}", file=sys.stderr)
            if len(unlisted) > 20:
                print(f"  ... and {len(unlisted) - 20} more", file=sys.stderr)
            print(
                "pass --allow-unlisted-patches to score them anyway.",
                file=sys.stderr,
            )
            return 4
        if unlisted:
            audit_meta["patches_dir_unlisted"] = len(unlisted)
        if args.fit_inputs:
            offenders = audit_fit_inputs(args.manifest, args.fit_inputs)
            if offenders:
                print("REFUSED: fit inputs contain held-out patches:", file=sys.stderr)
                for o in offenders:
                    print(f"  - {o}", file=sys.stderr)
                return 3
            audit_meta["fit_inputs_hash_audit"] = "clean"
        else:
            print(
                "note: --manifest without --fit-inputs: the scored set was "
                "checked against the manifest, but the fit inputs were not "
                "audited for held-out contamination.",
                file=sys.stderr,
            )

    family = load_run_windings(Path(args.meshes), variant=args.variant)
    patches, load_errors = _load_patches_dir(Path(args.patches))
    input_family = None
    if args.fit_inputs:
        input_family, input_errors = _load_patches_dir(Path(args.fit_inputs))
        if input_errors:
            if not args.allow_input_load_errors:
                print(
                    f"REFUSED: {len(input_errors)} fit-input patch(es) could not "
                    "be loaded, so the leakage measurement would silently skip "
                    "them and flatter the unseen numbers:",
                    file=sys.stderr,
                )
                for name, err in list(input_errors.items())[:10]:
                    print(f"  - {name}: {err}", file=sys.stderr)
                print(
                    "fix the inputs, or pass --allow-input-load-errors to "
                    "accept the weaker guarantee.",
                    file=sys.stderr,
                )
                return 5
            audit_meta["fit_inputs_load_errors"] = len(input_errors)
    z_range = None
    if args.z_range:
        parts = [float(v) for v in args.z_range.split(",")]
        if len(parts) != 2 or parts[0] >= parts[1]:
            raise SystemExit(f"--z-range expects 'z_min,z_max', got {args.z_range!r}")
        z_range = (parts[0], parts[1])
    scores, aggregate = score_patches(
        patches, family, tau=args.tau, z_range=z_range,
        input_family=input_family, unseen_min_dist=args.unseen_min_dist,
    )
    intrinsic = None
    if not args.no_intrinsic and len(family) >= 2:
        if args.umbilicus is None:
            print(
                "warning: intrinsic checks without --umbilicus assume the "
                "scroll axis at (y, x) = (0, 0); for real scans pass the "
                "dataset umbilicus.json (results are meaningless otherwise).",
                file=sys.stderr,
            )
        intrinsic = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))
    meta = {
        "parrhesia": __version__,
        "meshes": str(args.meshes),
        "patches": str(args.patches),
        "variant": args.variant,
        "n_windings": len(family),
        "tau": args.tau,
        "z_range": args.z_range,
        "umbilicus": args.umbilicus,
        "manifest": args.manifest,
        "fit_inputs": args.fit_inputs,
        "unseen_min_dist": args.unseen_min_dist if args.fit_inputs else None,
        **audit_meta,
    }
    if load_errors:
        meta["patch_load_errors"] = load_errors
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
    if args.umbilicus is None:
        print(
            "warning: intrinsic checks without --umbilicus assume the scroll "
            "axis at (y, x) = (0, 0); for real scans pass the dataset "
            "umbilicus.json (results are meaningless otherwise).",
            file=sys.stderr,
        )
    rep = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))
    meta = {
        "parrhesia": __version__,
        "meshes": str(args.meshes),
        "n_windings": len(family),
        "umbilicus": args.umbilicus,
    }
    report = write_report(Path(args.out), None, None, rep, meta=meta, overlay_slices=0)
    print(f"report: {report}")
    print(json.dumps(rep.to_dict(), indent=2))
    return 0


def cmd_split(args) -> int:
    from .split import split_patches

    manifest = split_patches(
        Path(args.src), Path(args.out), heldout_frac=args.frac, seed=args.seed
    )
    print(
        json.dumps(
            {k: manifest[k] for k in ("n_patches", "n_families", "n_heldout", "seed")},
            indent=2,
        )
    )
    return 0


def cmd_compare(args) -> int:
    from .report import compare_reports

    out = compare_reports(args.report_a, args.report_b, args.out)
    print(f"comparison: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parrhesia")
    parser.add_argument("--version", action="version", version=f"parrhesia {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    p = sub.add_parser("score", help="score a run's windings against held-out patches")
    p.add_argument("--meshes", required=True, help="run meshes dir (wNNN[_spliced] or combined)")
    p.add_argument("--patches", required=True, help="directory of held-out tifxyz patches")
    p.add_argument("--out", required=True, help="output report directory")
    p.add_argument("--tau", type=float, default=6.0, help="distance tolerance in voxels")
    p.add_argument("--variant", default="spliced", choices=["spliced", "plain", "any"])
    p.add_argument("--umbilicus", default=None, help="'y,x' constant or json polyline [z,y,x]")
    p.add_argument(
        "--z-range", default=None,
        help="'z_min,z_max' of the fitted window: patch points outside it are not scored",
    )
    p.add_argument("--manifest", default=None, help="split_manifest.json to audit against")
    p.add_argument(
        "--fit-inputs", default=None,
        help="fit input patches dir: hash-audited against --manifest and used "
        "for the geometric evidence-leakage measurement",
    )
    p.add_argument(
        "--unseen-min-dist", type=float, default=2.0,
        help="points within this distance (vox) of a fit input surface count "
        "as seen evidence; the 'unseen' aggregate scores only the rest",
    )
    p.add_argument(
        "--allow-unlisted-patches", action="store_true",
        help="proceed even if --patches contains directories that are not the "
        "manifest's held-out side (they are still scored like the rest; the "
        "unlisted count is recorded in the report meta)",
    )
    p.add_argument(
        "--allow-input-load-errors", action="store_true",
        help="proceed even if some --fit-inputs patches cannot be loaded "
        "(weakens the leakage measurement; the error count is recorded)",
    )
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
