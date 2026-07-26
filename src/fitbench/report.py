"""Report generation: JSON, Markdown summary, and PNG overlays."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .intrinsic import IntrinsicReport
from .io_tifxyz import QuadSurface
from .metrics import PatchScore


def overlay_slice(
    family: dict[int, QuadSurface],
    scores: list[PatchScore],
    z_center: float,
    dz: float,
    path: Path,
    tau: float,
) -> None:
    """One z-slab overlay: winding vertices in gray, patch points colored by distance."""
    fig, ax = plt.subplots(figsize=(9, 9))
    for wid in sorted(family):
        pts = family[wid].valid_zyxs
        sel = np.abs(pts[:, 0] - z_center) <= dz / 2
        if sel.any():
            ax.plot(pts[sel, 2], pts[sel, 1], ".", color="0.75", ms=1.5, zorder=1)
    drew = False
    for s in scores:
        sel = np.abs(s.point_zyx[:, 0] - z_center) <= dz / 2
        if sel.any():
            sc = ax.scatter(
                s.point_zyx[sel, 2],
                s.point_zyx[sel, 1],
                c=s.point_dist[sel],
                cmap="viridis",
                vmin=0.0,
                vmax=max(tau, 1e-6),
                s=14,
                zorder=2,
            )
            drew = True
    if drew:
        fig.colorbar(sc, ax=ax, label="distance to nearest winding (vox)")
    ax.set_aspect("equal")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(f"held-out patches vs windings, z = {z_center:.0f} +/- {dz / 2:.0f}")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _md_table(rows: list[list[str]], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def write_report(
    out_dir: str | Path,
    scores: list[PatchScore] | None,
    aggregate: dict | None,
    intrinsic: IntrinsicReport | None,
    family: dict[int, QuadSurface] | None = None,
    meta: dict | None = None,
    overlay_slices: int = 2,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload: dict = {"meta": meta or {}}
    if aggregate is not None:
        payload["heldout_aggregate"] = aggregate
        payload["heldout_patches"] = [s.to_dict() for s in (scores or [])]
    if intrinsic is not None:
        payload["intrinsic"] = intrinsic.to_dict()
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["# fitbench report", ""]
    if meta:
        lines += [f"- {k}: {v}" for k, v in meta.items()] + [""]
    if aggregate is not None:
        lines += ["## Held-out aggregate", ""]
        lines += [
            _md_table(
                [
                    ["points", str(aggregate["n_points"])],
                    ["dist p50 / p90 / p99 (vox)",
                     f"{aggregate['dist_p50']:.3f} / {aggregate['dist_p90']:.3f} / {aggregate['dist_p99']:.3f}"],
                    [f"within tau = {aggregate['tau']}", f"{aggregate['frac_within_tau'] * 100:.1f}%"],
                    ["single-winding consistency (mean / min)",
                     f"{aggregate['mean_single_winding_consistency']:.3f} / {aggregate['min_single_winding_consistency']:.3f}"],
                    ["winding agreement", str(aggregate["mean_winding_agreement"])],
                ],
                ["metric", "value"],
            ),
            "",
        ]
        rows = [
            [s.patch_id, str(s.n_points), f"{s.dist_p50:.2f}", f"{s.dist_p99:.2f}",
             f"{s.frac_within_tau * 100:.0f}%", str(s.modal_winding),
             f"{s.single_winding_consistency:.2f}"]
            for s in sorted(scores or [], key=lambda s: -s.dist_p99)
        ]
        lines += ["## Per patch (worst first)", "",
                  _md_table(rows, ["patch", "pts", "p50", "p99", "<tau", "winding", "consistency"]), ""]
    if intrinsic is not None:
        lines += ["## Intrinsic checks", ""]
        lines += [
            _md_table(
                [
                    ["median pitch (vox)", f"{intrinsic.median_pitch:.2f}"],
                    ["bins checked", str(intrinsic.n_bins_checked)],
                    ["violations (crossings)",
                     f"{intrinsic.n_violations} ({intrinsic.violated_bin_fraction * 100:.2f}%)"],
                    ["collapsed gaps",
                     f"{intrinsic.n_collapsed} ({intrinsic.collapsed_bin_fraction * 100:.2f}%)"],
                    ["inflated gaps", str(intrinsic.n_inflated)],
                ],
                ["check", "value"],
            ),
            "",
        ]
        if intrinsic.worst:
            rows = [
                [w["kind"], f"{w['gap']:.2f}", str(w["inner_winding"]),
                 f"{w['z_range'][0]:.0f}..{w['z_range'][1]:.0f}",
                 f"{w['theta_range'][0]:.2f}..{w['theta_range'][1]:.2f}"]
                for w in intrinsic.worst[:10]
            ]
            lines += ["### Worst offenders", "",
                      _md_table(rows, ["kind", "gap", "inner wind", "z", "theta"]), ""]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    if family and scores and overlay_slices > 0:
        all_z = np.concatenate([s.point_zyx[:, 0] for s in scores])
        z_lo, z_hi = float(all_z.min()), float(all_z.max())
        dz = max((z_hi - z_lo) / max(overlay_slices, 1), 1.0)
        for i in range(overlay_slices):
            zc = z_lo + (i + 0.5) * (z_hi - z_lo) / overlay_slices
            overlay_slice(
                family, scores, zc, dz, out_dir / f"overlay_z{int(zc):05d}.png",
                tau=aggregate["tau"] if aggregate else 6.0,
            )
    return out_dir / "report.json"


def compare_reports(report_a: str | Path, report_b: str | Path, out_path: str | Path) -> Path:
    """Delta table between two report.json files (aggregate metrics only)."""
    a = json.loads(Path(report_a).read_text(encoding="utf-8"))
    b = json.loads(Path(report_b).read_text(encoding="utf-8"))
    rows = []
    for section in ("heldout_aggregate", "intrinsic"):
        sa, sb = a.get(section, {}), b.get(section, {})
        for key in sorted(set(sa) & set(sb)):
            va, vb = sa[key], sb[key]
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                rows.append([f"{section}.{key}", f"{va:.4g}", f"{vb:.4g}", f"{vb - va:+.4g}"])
    text = "# fitbench compare\n\n" + _md_table(rows, ["metric", "A", "B", "B - A"]) + "\n"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path
