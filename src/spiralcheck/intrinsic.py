"""Intrinsic (ground-truth-free) checks on a winding family.

The family is binned in (z, theta) around the umbilicus; within each bin every
winding contributes the mean radius of its vertices. A physical scroll's
windings are radially ordered everywhere, so:

- a *violation* is an adjacent winding pair whose radial gap is <= 0 in a bin
  (sheet crossing or swap);
- a *collapsed gap* is a positive gap far below the family's median pitch
  (sheets fused);
- an *inflated gap* is a gap far above it (skipped material or a hole).

Everything is reported per bin and aggregated, with the worst offenders
localized so a human can jump straight to (z, theta).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .io_tifxyz import QuadSurface


def resolve_umbilicus(umbilicus, z_values: np.ndarray) -> np.ndarray:
    """Umbilicus (y, x) per z sample.

    Accepts a constant (y, x) pair, a callable z -> (y, x), a polyline (K, 3)
    of [z, y, x] rows, or villa's umbilicus.json structure (a dict with a
    'control_points' list of {z, y, x} objects). Defaults to the origin.
    """
    if umbilicus is None:
        return np.zeros((len(z_values), 2))
    if callable(umbilicus):
        return np.asarray([umbilicus(z) for z in z_values], dtype=np.float64)
    if isinstance(umbilicus, dict):
        pts = umbilicus.get("control_points")
        if not pts:
            raise ValueError("umbilicus dict must contain a non-empty 'control_points' list")
        umbilicus = [[p["z"], p["y"], p["x"]] for p in pts]
    umb = np.asarray(umbilicus, dtype=np.float64)
    if umb.shape == (2,):
        return np.broadcast_to(umb, (len(z_values), 2)).copy()
    if umb.ndim == 2 and umb.shape[1] == 3:
        order = np.argsort(umb[:, 0])
        zs, ys, xs = umb[order, 0], umb[order, 1], umb[order, 2]
        return np.stack(
            [np.interp(z_values, zs, ys), np.interp(z_values, zs, xs)], axis=-1
        )
    raise ValueError(f"unsupported umbilicus spec of shape {getattr(umb, 'shape', None)}")


@dataclass
class IntrinsicReport:
    winding_ids: list[int]
    z_edges: np.ndarray
    theta_bins: int
    median_pitch: float
    n_bins_checked: int
    n_violations: int
    violated_bin_fraction: float
    n_collapsed: int
    collapsed_bin_fraction: float
    n_inflated: int
    worst: list[dict]  # top offenders, kinds interleaved by severity rank: bin, winding pair, gap
    validity_per_winding: dict[int, float]

    def to_dict(self) -> dict:
        return {
            "winding_ids": self.winding_ids,
            "theta_bins": self.theta_bins,
            "z_bins": len(self.z_edges) - 1,
            "median_pitch": self.median_pitch,
            "n_bins_checked": self.n_bins_checked,
            "n_violations": self.n_violations,
            "violated_bin_fraction": self.violated_bin_fraction,
            "n_collapsed": self.n_collapsed,
            "collapsed_bin_fraction": self.collapsed_bin_fraction,
            "n_inflated": self.n_inflated,
            "worst": self.worst,
            "validity_per_winding": {str(k): v for k, v in self.validity_per_winding.items()},
        }


def intrinsic_report(
    family: dict[int, QuadSurface],
    umbilicus=None,
    z_bins: int = 10,
    theta_bins: int = 48,
    min_count: int = 3,
    collapse_frac: float = 0.2,
    inflate_frac: float = 2.5,
    top_n: int = 20,
) -> IntrinsicReport:
    if len(family) < 2:
        raise ValueError("intrinsic checks need at least two windings")
    wids = sorted(family)

    all_z = np.concatenate([s.valid_zyxs[:, 0] for s in family.values()])
    z_lo, z_hi = float(all_z.min()), float(all_z.max())
    z_edges = np.linspace(z_lo, z_hi + 1e-6, z_bins + 1)
    z_centers = (z_edges[:-1] + z_edges[1:]) / 2
    umb = resolve_umbilicus(umbilicus, z_centers)  # (z_bins, 2)

    # Mean radius per (winding, z bin, theta bin).
    sums = np.zeros((len(wids), z_bins, theta_bins))
    counts = np.zeros((len(wids), z_bins, theta_bins), dtype=np.int64)
    validity = {}
    for wi, wid in enumerate(wids):
        s = family[wid]
        validity[wid] = float(s.valid_vertex_mask.mean())
        pts = s.valid_zyxs.astype(np.float64)
        zi = np.clip(np.searchsorted(z_edges, pts[:, 0], side="right") - 1, 0, z_bins - 1)
        yx = pts[:, 1:] - umb[zi]
        radius = np.linalg.norm(yx, axis=-1)
        theta = np.arctan2(yx[:, 0], yx[:, 1])  # [-pi, pi)
        ti = np.clip(
            ((theta + np.pi) / (2 * np.pi) * theta_bins).astype(np.int64), 0, theta_bins - 1
        )
        np.add.at(sums, (wi, zi, ti), radius)
        np.add.at(counts, (wi, zi, ti), 1)

    with np.errstate(invalid="ignore"):
        mean_r = np.where(counts >= min_count, sums / np.maximum(counts, 1), np.nan)

    # Adjacent-pair gaps, normalized by winding id delta (ids may skip).
    gaps = []
    records = []  # (gap_per_winding, wid_inner, zi, ti)
    for wi in range(len(wids) - 1):
        delta_id = wids[wi + 1] - wids[wi]
        gap = (mean_r[wi + 1] - mean_r[wi]) / delta_id
        ok = np.isfinite(gap)
        for zi, ti in zip(*np.nonzero(ok)):
            g = float(gap[zi, ti])
            gaps.append(g)
            records.append((g, wids[wi], int(zi), int(ti)))

    if not gaps:
        raise ValueError("no (z, theta) bin has two adjacent windings with enough vertices")
    gaps_arr = np.array(gaps)
    median_pitch = float(np.median(gaps_arr))

    violations = gaps_arr <= 0.0
    collapsed = (~violations) & (gaps_arr < collapse_frac * median_pitch)
    inflated = gaps_arr > inflate_frac * median_pitch

    # One offender list, kinds interleaved by severity rank (rank k of every
    # kind precedes rank k+1 of any kind): an abundant kind must not crowd the
    # others out of the table's top rows. Severity within a kind: most
    # negative gap (violation), closest to zero (collapsed), farthest above
    # the pitch (inflated).
    ranked: dict[str, np.ndarray] = {}
    for kind, mask, sort_key in (
        ("violation", violations, gaps_arr),
        ("collapsed", collapsed, gaps_arr),
        ("inflated", inflated, -gaps_arr),
    ):
        idx = np.nonzero(mask)[0]
        ranked[kind] = idx[np.argsort(sort_key[idx], kind="stable")]
    worst = []
    for rank in range(top_n):
        if len(worst) >= top_n:
            break
        for kind, idx in ranked.items():
            if rank < len(idx) and len(worst) < top_n:
                g, wid_inner, zi, ti = records[int(idx[rank])]
                worst.append(
                    {
                        "gap": g,
                        "kind": kind,
                        "inner_winding": wid_inner,
                        "z_range": [float(z_edges[zi]), float(z_edges[zi + 1])],
                        "theta_range": [
                            float(-np.pi + ti * 2 * np.pi / theta_bins),
                            float(-np.pi + (ti + 1) * 2 * np.pi / theta_bins),
                        ],
                    }
                )

    n = len(gaps_arr)
    return IntrinsicReport(
        winding_ids=wids,
        z_edges=z_edges,
        theta_bins=theta_bins,
        median_pitch=median_pitch,
        n_bins_checked=n,
        n_violations=int(violations.sum()),
        violated_bin_fraction=float(violations.mean()),
        n_collapsed=int(collapsed.sum()),
        collapsed_bin_fraction=float(collapsed.mean()),
        n_inflated=int(inflated.sum()),
        worst=worst,
        validity_per_winding=validity,
    )
