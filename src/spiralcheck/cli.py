"""Command-line interface for spiralcheck. See DESIGN.md for the method."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from . import __version__


def _die(message: str) -> None:
    """Predictable input mistakes (a mistyped path, an invalid option value)
    deserve one explanatory line and exit 2, not a traceback: the traceback
    format is reserved for bugs in this tool."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _load_patches_dir(path: Path) -> tuple[dict, dict[str, str]]:
    """Load every tifxyz child directory; collect per-patch load errors instead
    of letting one corrupted directory (e.g. a partial sync) abort the run."""
    from .io_tifxyz import load_tifxyz

    if not path.is_dir():
        _die(f"not a directory: {path}")
    patches, errors = {}, {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "meta.json").exists():
            try:
                patches[d.name] = load_tifxyz(d)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors[d.name] = f"{type(exc).__name__}: {exc}"
                print(f"warning: could not load patch {d.name}: {exc}", file=sys.stderr)
    if not patches:
        _die(f"no loadable tifxyz patch directory in {path}")
    return patches, errors


def _load_umbilicus(spec: str | None):
    if spec is None:
        return None
    p = Path(spec)
    if p.is_dir():
        _die(f"--umbilicus: {p} is a directory; expected 'y,x' or a json file")
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"--umbilicus: {p} is not valid JSON: {exc}")
        _check_umbilicus_shape(data, spec)
        return data  # villa umbilicus.json, or (K, 3) rows of [z, y, x]
    try:
        parts = [float(v) for v in spec.split(",")]
    except ValueError:
        parts = []
    if len(parts) == 2 and all(math.isfinite(v) for v in parts):
        return tuple(parts)
    _die(f"cannot interpret umbilicus spec {spec!r}: expected 'y,x' or an existing json file")


def _check_umbilicus_shape(data, spec: str) -> None:
    """A syntactically valid JSON of the wrong shape used to surface as a
    traceback minutes into the run, from inside the intrinsic checks. Resolve
    it against a dummy z now, with the real resolver, so shape mistakes die
    early and with the input's name attached."""
    import numpy as np

    from .intrinsic import resolve_umbilicus

    try:
        resolve_umbilicus(data, np.zeros(1))
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        _die(f"--umbilicus: {spec}: {exc}")


def _parse_z_range(spec: str | None) -> tuple[float, float] | None:
    if not spec:
        return None
    try:
        parts = [float(v) for v in spec.split(",")]
    except ValueError:
        parts = []
    if len(parts) != 2 or not all(map(math.isfinite, parts)) or parts[0] >= parts[1]:
        _die(f"--z-range expects 'z_min,z_max', got {spec!r}")
    return (parts[0], parts[1])


def cmd_score(args) -> int:
    from .intrinsic import intrinsic_report
    from .io_tifxyz import load_run_windings
    from .metrics import NoScorablePoint, score_patches
    from .report import write_report
    from .split import audit_fit_inputs, audit_scored_patches

    # Validate every option before the first heavy load, so a typo in the last
    # flag is not discovered minutes into the run, one loading step at a time.
    # "not (x > 0)" rather than "x <= 0": both comparisons are False for NaN,
    # and NaN must be refused, not scored into the report.
    if not args.tau > 0:
        _die(f"--tau must be a positive number, got {args.tau}")
    # A non-positive threshold would let every scored point count as unseen,
    # which silently turns the report's central guarantee into a tautology.
    if not args.unseen_min_dist > 0:
        _die(
            f"--unseen-min-dist must be a positive number, got {args.unseen_min_dist}: "
            "a non-positive threshold would report seen evidence as unseen"
        )
    z_range = _parse_z_range(args.z_range)
    _load_umbilicus(args.umbilicus)  # validate now; reparsed cheaply at use site
    if not Path(args.meshes).is_dir():
        _die(f"--meshes: not a directory: {args.meshes}")
    if not Path(args.patches).is_dir():
        _die(f"--patches: not a directory: {args.patches}")
    if args.fit_inputs and not Path(args.fit_inputs).is_dir():
        _die(f"--fit-inputs: not a directory: {args.fit_inputs}")
    if args.manifest and not Path(args.manifest).is_file():
        _die(f"--manifest: not a file: {args.manifest}")

    audit_meta: dict = {}
    if args.manifest:
        try:
            unlisted, listed, n_heldout = audit_scored_patches(args.manifest, args.patches)
        except (NotADirectoryError, FileNotFoundError, json.JSONDecodeError) as exc:
            _die(str(exc))
        except (KeyError, TypeError, AttributeError) as exc:
            _die(
                f"--manifest: {args.manifest} does not look like a split "
                f"manifest ({type(exc).__name__}: {exc})"
            )
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
            try:
                offenders = audit_fit_inputs(args.manifest, args.fit_inputs)
            except (KeyError, TypeError, AttributeError) as exc:
                _die(
                    f"--manifest: {args.manifest} does not look like a split "
                    f"manifest ({type(exc).__name__}: {exc})"
                )
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

    try:
        family = load_run_windings(Path(args.meshes), variant=args.variant)
    except (FileNotFoundError, ValueError) as exc:
        _die(str(exc))
    except KeyError as exc:
        _die(f"cannot load meshes from {args.meshes}: missing key {exc} in a meta.json")
    if args.fit_inputs is None:
        n_spliced = sum(
            1 for s in family.values() if s.path is not None and "_spliced" in s.path.name
        )
        if n_spliced:
            print(
                f"warning: {n_spliced} of {len(family)} loaded windings are the "
                "_spliced variant, which embeds the fit's own input patches "
                "verbatim, and no --fit-inputs was given: distances near any "
                "input partly measure the splice, not the fit, and nothing "
                "here can tell those points apart. Pass --fit-inputs to "
                "measure the leakage and score the unseen evidence "
                "separately, or score --variant plain (see DESIGN.md, "
                "Operating point).",
                file=sys.stderr,
            )
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
    try:
        scores, aggregate = score_patches(
            patches, family, tau=args.tau, z_range=z_range,
            input_family=input_family, unseen_min_dist=args.unseen_min_dist,
        )
    except NoScorablePoint as exc:
        _die(str(exc))
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
        "spiralcheck": __version__,
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

    try:
        family = load_run_windings(Path(args.meshes), variant=args.variant)
    except (FileNotFoundError, ValueError) as exc:
        _die(str(exc))
    if args.umbilicus is None:
        print(
            "warning: intrinsic checks without --umbilicus assume the scroll "
            "axis at (y, x) = (0, 0); for real scans pass the dataset "
            "umbilicus.json (results are meaningless otherwise).",
            file=sys.stderr,
        )
    rep = intrinsic_report(family, umbilicus=_load_umbilicus(args.umbilicus))
    meta = {
        "spiralcheck": __version__,
        "meshes": str(args.meshes),
        "n_windings": len(family),
        "umbilicus": args.umbilicus,
    }
    report = write_report(Path(args.out), None, None, rep, meta=meta, overlay_slices=0)
    print(f"report: {report}")
    print(json.dumps(rep.to_dict(), indent=2))
    return 0


def cmd_annotations(args) -> int:
    from .annotations import (
        load_point_collections,
        score_collections,
        write_annotation_report,
    )
    from .io_tifxyz import load_run_windings
    from .metrics import WindingFamilySoup

    z_range = _parse_z_range(args.z_range)
    if args.tau <= 0:
        _die(f"--tau must be a positive number, got {args.tau}")
    umbilicus = _load_umbilicus(args.umbilicus)
    if umbilicus is None:
        print(
            "warning: without --umbilicus the azimuth correction assumes the "
            "scroll axis at (y, x) = (0, 0); on real scans the wrap index is "
            "meaningless without it.",
            file=sys.stderr,
        )
    try:
        family = load_run_windings(Path(args.meshes), variant=args.variant)
    except (FileNotFoundError, ValueError) as exc:
        _die(str(exc))
    try:
        collections = load_point_collections(args.pcl)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        _die(f"--pcl: {exc}")
    if not collections:
        _die(f"no point collection with any point in {args.pcl}")

    scores, aggregate = score_collections(
        collections,
        WindingFamilySoup.from_family(family),
        umbilicus=umbilicus,
        tau=args.tau,
        z_range=z_range,
    )
    meta = {
        "spiralcheck": __version__,
        "meshes": str(args.meshes),
        "variant": args.variant,
        "n_windings": len(family),
        "pcl": [str(p) for p in args.pcl],
        "umbilicus": args.umbilicus,
        "tau": args.tau,
        "z_range": args.z_range,
    }
    out = write_annotation_report(Path(args.out), scores, aggregate, meta=meta)
    print(f"report: {out}")
    print(json.dumps(aggregate, indent=2))
    return 0


def cmd_split(args) -> int:
    from .split import split_patches

    if not Path(args.src).is_dir():
        _die(f"--src: not a directory: {args.src}")
    if not 0.0 < args.frac < 1.0:
        _die(f"--frac must be strictly between 0 and 1, got {args.frac}")
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

    try:
        out = compare_reports(args.report_a, args.report_b, args.out)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _die(str(exc))
    print(f"comparison: {out}")
    return 0


# Demo geometry: one deliberately damaged synthetic scroll. The swap exchanges
# two windings inside a theta band (the classic sheet switch: distances stay
# small, identity is wrong); the collapse pulls one winding onto its inner
# neighbor (a spacing defect distances also cannot see from the patch side).
_DEMO_PITCH = 10.0
_DEMO_SWAP = (13, 14, (1.0, 2.2))
_DEMO_COLLAPSE = (16, (4.0, 5.0), 0.9)
# (winding, theta range) per held-out patch: some on the planted defects, some
# on healthy regions so the null rows are visible in the same table. The last
# band runs past 2*pi: it crosses the theta seam into the next winding and
# carries its relative winding.tif annotation, so winding agreement is
# exercised end to end (and the seam legitimately puts that patch's raw
# single-winding fraction below 1, defects or not: that is what winding ids do
# at the seam, and why sheet consistency exists).
_DEMO_PATCHES = [
    (11, (0.4, 1.6)),
    (12, (2.0, 3.2)),
    (13, (1.2, 2.4)),
    (14, (1.0, 2.2)),
    (15, (4.2, 5.4)),
    (16, (4.0, 5.2)),
    (12, (5.0, 6.2)),
    (17, (0.2, 1.4)),
    (12, (5.6, 8.4)),
]


def _q(path) -> str:
    """Quote a path for the copy-pastable hints when it contains spaces."""
    s = str(path)
    return f'"{s}"' if " " in s else s


def cmd_demo(args) -> int:
    from .io_tifxyz import save_tifxyz
    from .synthetic import collapse_gap, make_family, sample_patch, swap_band

    out = Path(args.out)
    if out.exists() and not out.is_dir():
        _die(f"--out: {out} exists and is not a directory")
    scroll = make_family(num_windings=8, first_winding=10, pitch=_DEMO_PITCH, z_count=20)
    fit = scroll
    if not args.clean:
        w1, w2, band = _DEMO_SWAP
        fit = swap_band(scroll, w1, w2, band)
        winding, band, factor = _DEMO_COLLAPSE
        fit = collapse_gap(fit, winding, band, factor=factor)

    meshes = out / "meshes"
    for wid, surface in fit.items():
        save_tifxyz(surface, meshes / f"w{wid:03d}", uuid=f"w{wid:03d}")
    patches_dir = out / "heldout"
    for i, (wid, band) in enumerate(_DEMO_PATCHES):
        multi = band[1] > 2 * math.pi
        patch = sample_patch(wid, _DEMO_PITCH, band, (8.0, 68.0), with_winding_grid=multi)
        end_w = wid + int(band[1] // (2 * math.pi))
        name = f"patch{i}_w{wid}" + (f"-w{end_w}" if multi else "")
        save_tifxyz(patch, patches_dir / name, uuid=name)

    kind = "clean (null control)" if args.clean else "defective"
    print(f"demo scroll: 8 windings (w10..w17), pitch {_DEMO_PITCH:g} vox, {kind}")
    if not args.clean:
        print(
            f"planted: windings {_DEMO_SWAP[0]}/{_DEMO_SWAP[1]} swapped in theta "
            f"[{_DEMO_SWAP[2][0]:g}, {_DEMO_SWAP[2][1]:g}) (sheet switch), and "
            f"winding {_DEMO_COLLAPSE[0]}'s gap collapsed by {_DEMO_COLLAPSE[2]:.0%} "
            f"in theta [{_DEMO_COLLAPSE[1][0]:g}, {_DEMO_COLLAPSE[1][1]:g})"
        )
    print(f"scoring {len(_DEMO_PATCHES)} held-out patches sampled from the clean scroll...")
    rc = main([
        "score", "--meshes", str(meshes), "--patches", str(patches_dir),
        "--out", str(out / "report"), "--variant", "plain", "--umbilicus", "0,0",
    ])
    if rc != 0:
        return rc
    print()
    if args.clean:
        print("null control: every alarm above must be silent (distances ~0, "
              "sheet consistency 1.0, winding agreement 1.0, no intrinsic "
              "violations). One patch crosses the theta seam, so its raw "
              "single-winding fraction sits below 1 even here: the seam is "
              "why the sheet metric exists.")
    else:
        print("read the report: the swap fires the identity checks (winding "
              "agreement on the seam-crossing patch, intrinsic violations, "
              "and sheet consistency < 1 where a patch straddles the swap "
              "edge) while its distances stay near zero, because a surface "
              "one winding out of place is still close to something. The "
              "collapse shows up under collapsed gaps and as the large "
              "distances on the collapsed winding's patch.")
        clean_out = out.parent / (out.name + "_clean")
        print("compare against the clean twin:")
        print(f"  uv run spiralcheck demo --clean --out {_q(clean_out)}")
        print(f"  uv run spiralcheck compare {_q(clean_out / 'report' / 'report.json')} "
              f"{_q(out / 'report' / 'report.json')} --out {_q(out.parent / 'demo_compare.md')}")
    return 0


def _add_variant_flag(p) -> None:
    p.add_argument(
        "--variant", default="spliced", choices=["spliced", "plain", "any"],
        help="which winding directories to load: 'spliced' prefers wNNN_spliced "
        "(falls back to wNNN per winding), 'plain' loads wNNN only. The spliced "
        "export embeds the fit's own input patches verbatim, so score it with "
        "--fit-inputs or read DESIGN.md (Operating point) first",
    )


def _add_umbilicus_flag(p) -> None:
    p.add_argument(
        "--umbilicus", default=None,
        help="scroll axis for the intrinsic checks: 'y,x' constant or a villa "
        "umbilicus.json polyline of [z, y, x] rows. Omitted: the axis is "
        "assumed at (y, x) = (0, 0), which is right for the demo scroll and "
        "meaningless for real scans (a warning says so at run time)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spiralcheck",
        description="Held-out geometric evaluation for whole-scroll surface "
        "fits. New here? 'spiralcheck demo --out demo/' runs the whole tool "
        "on a synthetic scroll with no data needed; the README's Getting "
        "started section shows the real invocation.",
    )
    parser.add_argument("--version", action="version", version=f"spiralcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)
    fmt = {"formatter_class": argparse.ArgumentDefaultsHelpFormatter}

    p = sub.add_parser(
        "score", help="score a run's windings against held-out patches", **fmt,
        epilog="exit codes: 0 scored; 2 invalid option or unreadable input; "
        "3 fit inputs contain held-out patches; 4 scored patches are not the "
        "manifest's held-out side; 5 unloadable fit inputs (see the two "
        "--allow-* flags).",
    )
    p.add_argument(
        "--meshes", required=True, default=argparse.SUPPRESS,
        help="run meshes directory: wNNN[_spliced] winding dirs or one "
        "combined surface, e.g. out/<run>/meshes/fitted_<tag>",
    )
    p.add_argument(
        "--patches", required=True, default=argparse.SUPPRESS,
        help="directory of held-out tifxyz patches to score",
    )
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="report directory to write: report.json, report.md, overlay PNGs",
    )
    p.add_argument(
        "--tau", type=float, default=6.0,
        help="distance tolerance in voxels of the mesh grid",
    )
    _add_variant_flag(p)
    _add_umbilicus_flag(p)
    p.add_argument(
        "--z-range", default=None,
        help="'z_min,z_max' of the fitted window: patch points outside it are "
        "not scored (a run only claims to model its own window)",
    )
    p.add_argument(
        "--manifest", default=None,
        help="split_manifest.json to audit against: refuses to score patches "
        "that are not its held-out side",
    )
    p.add_argument(
        "--fit-inputs", default=None,
        help="fit input patches dir: hash-audited against --manifest and used "
        "for the geometric evidence-leakage measurement plus the unseen-only "
        "aggregate",
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
    p.add_argument(
        "--overlays", type=int, default=2,
        help="number of overlay PNG slices to render (0 disables)",
    )
    p.add_argument(
        "--no-intrinsic", action="store_true",
        help="skip the ground-truth-free intrinsic checks",
    )
    p.set_defaults(func=cmd_score)

    p = sub.add_parser(
        "intrinsic", help="ground-truth-free checks only (no patches needed)", **fmt,
        epilog="exit codes: 0 checks written; 2 invalid option or unreadable input.",
    )
    p.add_argument(
        "--meshes", required=True, default=argparse.SUPPRESS,
        help="run meshes directory: wNNN[_spliced] winding dirs or one combined surface",
    )
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="report directory to write: report.json, report.md",
    )
    _add_variant_flag(p)
    _add_umbilicus_flag(p)
    p.set_defaults(func=cmd_intrinsic)

    p = sub.add_parser(
        "annotations",
        help="score a run against VC3D winding annotations (point collections)",
        **fmt,
        epilog="the same constraints villa scores inside the fit, measured from "
        "the exported meshes instead of the checkpoint; exit codes: 0 scored; "
        "2 invalid option or unreadable input.",
    )
    p.add_argument(
        "--meshes", required=True, default=argparse.SUPPRESS,
        help="run meshes directory: wNNN[_spliced] winding dirs or one combined surface",
    )
    p.add_argument(
        "--pcl", required=True, default=argparse.SUPPRESS, action="append",
        help="villa point-collection JSON (repeat for several files)",
    )
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="report directory to write: annotations.json, annotations.md",
    )
    p.add_argument(
        "--tau", type=float, default=6.0,
        help="a point farther than this (vox) from every surface is counted as "
        "undecidable rather than assigned a winding",
    )
    p.add_argument(
        "--z-range", default=None,
        help="'z_min,z_max' of the fitted window: annotated points outside it "
        "are not scored (a run only claims to model its own window)",
    )
    _add_variant_flag(p)
    _add_umbilicus_flag(p)
    p.set_defaults(func=cmd_annotations)

    p = sub.add_parser(
        "split", help="seeded held-out split of a patch directory", **fmt,
        epilog="patches are grouped into near-duplicate families before "
        "splitting, and a whole family goes to one side; see DESIGN.md, "
        "Held-out protocol. exit codes: 0 split written; 2 invalid option "
        "or unreadable input.",
    )
    p.add_argument(
        "--src", required=True, default=argparse.SUPPRESS,
        help="directory of verified tifxyz patches to split",
    )
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="output directory: fit/, heldout/, split_manifest.json",
    )
    p.add_argument(
        "--frac", type=float, default=0.2,
        help="fraction of patch families to hold out (the patch-level "
        "fraction lands close but not equal; the manifest records both)",
    )
    p.add_argument("--seed", type=int, default=20260731, help="deterministic split seed")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser(
        "compare", help="delta table between two report.json files", **fmt,
        epilog="deltas read B - A: positive means B is larger. The table "
        "records both file paths; it fails (exit 2) when the two files share "
        "no numeric report metric.",
    )
    p.add_argument("report_a", help="report.json of run A (the baseline)")
    p.add_argument("report_b", help="report.json of run B")
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="path of the Markdown FILE to write (one file, not a directory; "
        "give it a .md name)",
    )
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser(
        "demo",
        help="generate a small synthetic scroll with planted defects and score "
        "it: a full run of the tool with no data needed", **fmt,
        epilog="exit codes: 0 demo written and scored; 2 invalid option.",
    )
    p.add_argument(
        "--out", required=True, default=argparse.SUPPRESS,
        help="directory for the demo scroll and its report",
    )
    p.add_argument(
        "--clean", action="store_true",
        help="plant no defect: the null control, where every alarm must stay silent",
    )
    p.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
