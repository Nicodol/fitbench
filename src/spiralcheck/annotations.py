"""Score a winding family against villa point-collection winding annotations.

VC3D writes winding evidence as *point collections* (`vc_pointcollections_json`):
ordered points carrying an optional `wind_a` annotation. Two kinds matter here,
and villa's own reader distinguishes them exactly this way
(`scripts/spiral/point_collection.py`, `normalise_pcl_winding_annotations`):

- **relative** collections annotate every point, and the difference of two
  points' `wind_a` *is* the number of windings between them;
- **same-winding** collections annotate none (`wind_a: null`); the assertion is
  that every point of the collection sits on one and the same winding. Villa
  normalises these to `wind_a = 0` everywhere, which makes them the zero-delta
  case of the same rule.

`fit_spiral` already scores these constraints, in `satisfaction_metrics.py`
(`get_unattached_pcl_satisfied_counts`): it id-sorts each collection into a
strip, maps it through the **fitted** scan-to-spiral transform, unwraps the
shifted radius across theta=0 crossings, and requires
`unwrapped_shifted - wind_a * dr_per_winding` to stay within 0.45 pitches of the
strip's snapped median (and the reprojected target to stay within 6 scan
voxels). That measure needs the checkpoint, torch and a CUDA device, and it
reports on the constraints the fit consumed.

This module computes the same quantity from the **exported meshes plus the
umbilicus** — no checkpoint, no torch, no GPU — so a finished run folder can be
checked after the fact, and so a producer with no villa checkpoint at all can be
checked at all. The transposition is one substitution: where villa reads an
unwrapped shifted radius out of its transform, we read the continuous winding
coordinate `u = winding_id + column / columns` off the nearest exported face
(the same coordinate sheet consistency is built on, continuous across the theta
seam), and subtract the azimuth travelled, which `u` accumulates and a winding
index must not:

    W = u - theta / 2pi          (theta unwrapped along the collection)
    N = W - wind_a               (villa's `unwrapped_shifted - windings * dr`)

`N` is constant along a collection exactly when the fit honours the annotation.
Its absolute value carries an arbitrary offset (the mesh column origin and the
umbilicus azimuth origin need not coincide), so only differences are read: a
point disagrees when its `N` is at least half a turn from the collection's
median. Half a turn is the same decision boundary villa uses, and the same one
`sheet_components` uses.

Two limits are structural rather than incidental, and both are reported next to
every number:

- a point far from every exported surface has no meaningful nearest winding, so
  the verdict is taken over points within `tau` and the rest are counted, not
  guessed;
- the azimuth correction is computed in scan space about the umbilicus while `u`
  follows the fit's own deformed grid. The two agree only up to the deformation,
  and `wrap_index_spread` reports the residual, which is the instrument's noise
  floor against a decision boundary of 0.5.

Prior art, stated because this checks the same annotations from a different
side: villa's `find_inconsistent_windings.py` derives the winding number a point
*should* have from these very collections, propagating absolute anchors across a
patch graph and measuring the holonomy of relative-annotation loops. It audits
the annotations' mutual consistency, and it rebuilds the fit's spiral transform
from a checkpoint to do it. Here the annotations are taken as given and the
*output surfaces* are the subject.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geometry import surface_distance
from .intrinsic import resolve_umbilicus
from .metrics import WindingFamilySoup

# Half a turn: the boundary between "the same winding" and "the next one".
# Matches SHEET_MAX_JUMP_TURNS and villa's 0.45-pitch spiral-space tolerance.
WRAP_DECISION_TURNS = 0.5

_JSON_VERSION_KEY = "vc_pointcollections_json_version"
_SUPPORTED_JSON_VERSIONS = ("1",)


@dataclass
class PointCollection:
    """One villa point collection, id-sorted (villa's own strip order)."""

    name: str
    source: str
    point_ids: np.ndarray  # (N,) int64
    zyx: np.ndarray  # (N, 3) float64
    wind_a: np.ndarray  # (N,) float64, NaN where unannotated
    winding_is_absolute: bool

    @property
    def n_points(self) -> int:
        return len(self.point_ids)

    @property
    def kind(self) -> str:
        """`relative` when the collection carries winding annotations,
        `same-winding` when it carries none. Villa draws the same line, and
        keeps it in `has_winding_annotations` precisely because 0-filling the
        unannotated case would otherwise erase it."""
        return "relative" if np.isfinite(self.wind_a).any() else "same-winding"

    def normalised_wind_a(self) -> tuple[np.ndarray, int]:
        """Villa's `normalise_pcl_winding_annotations`, as a pure function.

        All-unannotated collections become all-zero (the same-winding
        assertion); mixed collections drop their unannotated points, which is
        villa's behaviour and is reported rather than silently absorbed.
        Returns the annotations and the number of points dropped.
        """
        finite = np.isfinite(self.wind_a)
        if not finite.any():
            return np.zeros(self.n_points, dtype=np.float64), 0
        return self.wind_a, int((~finite).sum())


def load_point_collections(paths) -> list[PointCollection]:
    """Read villa point-collection JSON files.

    Mirrors `scripts/spiral/point_collection.py`: the version key is checked,
    points are keyed by integer id and sorted by it, and a point's position is
    `zyx` when present, else `p` reversed (villa stores `p` as x, y, z).
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    out: list[PointCollection] = []
    for path in paths:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get(_JSON_VERSION_KEY)
        if version not in _SUPPORTED_JSON_VERSIONS:
            raise ValueError(
                f"{path}: unsupported {_JSON_VERSION_KEY} {version!r} "
                f"(supported: {', '.join(_SUPPORTED_JSON_VERSIONS)})"
            )
        for raw_id, collection in sorted(
            data.get("collections", {}).items(), key=lambda kv: int(kv[0])
        ):
            points = collection.get("points", {})
            if not points:
                continue
            items = sorted(points.items(), key=lambda kv: int(kv[0]))
            zyx = np.array(
                [
                    p["zyx"] if "zyx" in p else [p["p"][2], p["p"][1], p["p"][0]]
                    for _, p in items
                ],
                dtype=np.float64,
            )
            wind_a = np.array(
                [
                    np.nan if p.get("wind_a") is None else float(p["wind_a"])
                    for _, p in items
                ],
                dtype=np.float64,
            )
            metadata = collection.get("metadata", {}) or {}
            out.append(
                PointCollection(
                    name=collection.get("name", f"collection_{raw_id}"),
                    source=path.name,
                    point_ids=np.array([int(pid) for pid, _ in items], dtype=np.int64),
                    zyx=zyx,
                    wind_a=wind_a,
                    winding_is_absolute=bool(metadata.get("winding_is_absolute", False)),
                )
            )
    return out


@dataclass
class CollectionScore:
    """What the exported meshes say about one annotated collection."""

    name: str
    source: str
    kind: str
    n_points: int
    n_in_window: int
    n_within_tau: int
    n_agree: int
    tau: float
    dist_p50: float | None
    dist_max: float | None
    wrap_index_spread: float | None
    n_unannotated_dropped: int
    offenders: list[dict] = field(default_factory=list)
    point_wrap_offset: np.ndarray | None = None
    point_dist: np.ndarray | None = None

    @property
    def agreement(self) -> float | None:
        """Fraction of decidable points the fit places on the annotated winding.

        `None` when no point is decidable (nothing within `tau` inside the
        window), which is a coverage statement, not a score of 0.
        """
        if self.n_within_tau == 0:
            return None
        return self.n_agree / self.n_within_tau

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "kind": self.kind,
            "n_points": self.n_points,
            "n_in_window": self.n_in_window,
            "n_within_tau": self.n_within_tau,
            "n_agree": self.n_agree,
            "agreement": self.agreement,
            "tau": self.tau,
            "dist_p50": self.dist_p50,
            "dist_max": self.dist_max,
            "wrap_index_spread": self.wrap_index_spread,
            "n_unannotated_dropped": self.n_unannotated_dropped,
            "offenders": self.offenders,
        }


def score_collection(
    collection: PointCollection,
    family_soup: WindingFamilySoup,
    umbilicus=None,
    tau: float = 6.0,
    z_range: tuple[float, float] | None = None,
) -> CollectionScore:
    """Score one annotated collection against a run's winding family.

    See the module docstring for the definition of the wrap index `N`. Points
    outside `z_range` are not scored (a run only claims to model its own
    window); points farther than `tau` from every surface are counted but not
    judged, because their nearest winding is not a decision the geometry
    supports.
    """
    wind_a, n_dropped = collection.normalised_wind_a()
    keep = np.isfinite(wind_a)
    zyx, wind_a = collection.zyx[keep], wind_a[keep]

    if z_range is not None:
        inside = (zyx[:, 0] >= z_range[0]) & (zyx[:, 0] <= z_range[1])
        zyx, wind_a = zyx[inside], wind_a[inside]

    empty = CollectionScore(
        name=collection.name,
        source=collection.source,
        kind=collection.kind,
        n_points=collection.n_points,
        n_in_window=len(zyx),
        n_within_tau=0,
        n_agree=0,
        tau=tau,
        dist_p50=None,
        dist_max=None,
        wrap_index_spread=None,
        n_unannotated_dropped=n_dropped,
    )
    if len(zyx) == 0:
        return empty

    result = surface_distance(zyx, family_soup.soup)
    u = family_soup.face_u[result.face_idx]

    # Azimuth travelled along the collection, in turns. `u` accumulates it; a
    # winding index must not, so it is subtracted. Unwrapping follows the
    # collection's own point order, which is villa's strip order.
    yx = resolve_umbilicus(umbilicus, zyx[:, 0])
    theta = np.arctan2(zyx[:, 1] - yx[:, 0], zyx[:, 2] - yx[:, 1])
    turns = np.unwrap(theta) / (2.0 * np.pi)

    wrap_index = u - turns - wind_a

    decidable = result.dist <= tau
    n_within_tau = int(decidable.sum())
    if n_within_tau == 0:
        empty.dist_p50 = float(np.percentile(result.dist, 50))
        empty.dist_max = float(result.dist.max())
        # Distances are reported even when no verdict is: a caller profiling
        # where the undecidable evidence sits would otherwise silently drop
        # the collections that are *entirely* undecidable, which are exactly
        # the ones such a profile is about.
        empty.point_dist = result.dist
        return empty

    # Only differences of the wrap index are meaningful (its zero is the
    # arbitrary offset between the mesh column origin and the azimuth origin),
    # so the collection's own median is the reference.
    reference = float(np.median(wrap_index[decidable]))
    offset = wrap_index - reference
    agree = decidable & (np.abs(offset) < WRAP_DECISION_TURNS)

    offenders = []
    for i in np.nonzero(decidable & ~agree)[0]:
        offenders.append(
            {
                "z": float(zyx[i, 0]),
                "y": float(zyx[i, 1]),
                "x": float(zyx[i, 2]),
                "theta_deg": float(np.degrees(theta[i])),
                "wrap_offset": float(offset[i]),
                "wrap_offset_rounded": int(np.round(offset[i])),
                "dist": float(result.dist[i]),
            }
        )

    return CollectionScore(
        name=collection.name,
        source=collection.source,
        kind=collection.kind,
        n_points=collection.n_points,
        n_in_window=len(zyx),
        n_within_tau=n_within_tau,
        n_agree=int(agree.sum()),
        tau=tau,
        dist_p50=float(np.percentile(result.dist, 50)),
        dist_max=float(result.dist.max()),
        wrap_index_spread=float(np.abs(offset[agree]).max()) if agree.any() else None,
        n_unannotated_dropped=n_dropped,
        offenders=offenders,
        point_wrap_offset=offset,
        point_dist=result.dist,
    )


def aggregate_collection_scores(scores: list[CollectionScore]) -> dict:
    """Pool per-collection scores, overall and per kind.

    Pooled over *points*, not collections: a 59-point traced path and a
    2-point pair are not equal evidence. The per-collection counts are in the
    per-collection block for anyone who wants the other weighting.
    """

    def block(subset: list[CollectionScore]) -> dict:
        within = sum(s.n_within_tau for s in subset)
        agree = sum(s.n_agree for s in subset)
        spreads = [s.wrap_index_spread for s in subset if s.wrap_index_spread is not None]
        decided = [s for s in subset if s.n_within_tau > 0]
        # A collection with one decidable point is perfect by construction: the
        # reference is that point's own wrap index. Counting those among the
        # successes would flatter the fit, so they are separated out.
        informative = [s for s in subset if s.n_within_tau >= 2]
        return {
            "n_collections": len(subset),
            "n_collections_decidable": len(decided),
            "n_collections_perfect": sum(1 for s in decided if s.n_agree == s.n_within_tau),
            "n_collections_informative": len(informative),
            "n_collections_informative_perfect": sum(
                1 for s in informative if s.n_agree == s.n_within_tau
            ),
            "n_points": sum(s.n_points for s in subset),
            "n_points_in_window": sum(s.n_in_window for s in subset),
            "n_points_within_tau": within,
            "n_points_agree": agree,
            "agreement": (agree / within) if within else None,
            "wrap_index_spread_max": max(spreads) if spreads else None,
        }

    out = {"all": block(scores)}
    for kind in ("relative", "same-winding"):
        subset = [s for s in scores if s.kind == kind]
        if subset:
            out[kind] = block(subset)
    return out


def score_collections(
    collections: list[PointCollection],
    family_soup: WindingFamilySoup,
    umbilicus=None,
    tau: float = 6.0,
    z_range: tuple[float, float] | None = None,
) -> tuple[list[CollectionScore], dict]:
    scores = [
        score_collection(c, family_soup, umbilicus=umbilicus, tau=tau, z_range=z_range)
        for c in collections
    ]
    return scores, aggregate_collection_scores(scores)


def render_annotation_markdown(payload: dict) -> str:
    """One-screen summary of an annotation report."""
    agg = payload["aggregate"]
    meta = payload.get("meta", {})
    lines = [
        "# spiralcheck winding-annotation agreement",
        "",
        "Winding annotations scored against a run's exported surfaces, from the",
        "meshes and the umbilicus alone (no checkpoint, no GPU). A point is",
        "*decidable* when a winding surface lies within tau of it; undecidable",
        "points are counted, never guessed.",
        "",
    ]
    if meta:
        lines += [
            (
                f"- meshes: `{meta.get('meshes', '?')}` "
                f"({meta.get('n_windings', '?')} windings, "
                f"variant `{meta.get('variant', '?')}`)"
            ),
            f"- annotations: {', '.join(meta.get('pcl', []) or ['?'])}",
            f"- tau: {meta.get('tau', '?')} vox; z range: {meta.get('z_range') or 'all'}",
            "",
        ]
    lines += [
        "| set | collections | points | in window | decidable | agree | agreement |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("all", "relative", "same-winding"):
        if key not in agg:
            continue
        b = agg[key]
        pct = "n/a" if b["agreement"] is None else f"{100 * b['agreement']:.1f}%"
        lines.append(
            f"| {key} | {b['n_collections']} | {b['n_points']} | "
            f"{b['n_points_in_window']} | {b['n_points_within_tau']} | "
            f"{b['n_points_agree']} | {pct} |"
        )
    a = agg["all"]
    lines += [
        "",
        (
            f"{a['n_collections_informative_perfect']} of "
            f"{a['n_collections_informative']} collections with at least two "
            f"decidable points are honoured throughout. Collections with a "
            f"single decidable point are perfect by construction and are "
            f"excluded from that count."
        ),
    ]
    spread = agg["all"]["wrap_index_spread_max"]
    if spread is not None:
        lines += [
            "",
            (
                f"Largest wrap-index spread among agreeing points: "
                f"**{spread:.3f} turns** against a decision boundary of "
                f"{WRAP_DECISION_TURNS}. That ratio is the instrument's margin; "
                f"read a verdict as marginal when it approaches 1."
            ),
        ]
    offending = [c for c in payload["collections"] if c["offenders"]]
    lines += ["", "## Collections the fit does not honour", ""]
    if not offending:
        lines.append("None: every decidable point sits on its annotated winding.")
    else:
        lines += [
            "| collection | source | kind | decidable | agree | worst offset (turns) |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
        for c in sorted(offending, key=lambda c: (c["agreement"] or 0.0)):
            worst = max(c["offenders"], key=lambda o: abs(o["wrap_offset"]))
            lines.append(
                f"| {c['name']} | {c['source']} | {c['kind']} | {c['n_within_tau']} | "
                f"{c['n_agree']} | {worst['wrap_offset']:+.2f} |"
            )
    undecidable = [
        c for c in payload["collections"] if c["n_in_window"] > 0 and c["n_within_tau"] == 0
    ]
    if undecidable:
        lines += [
            "",
            f"{len(undecidable)} collection(s) in the window have no point within tau of "
            "any surface, so the fit is not judged on them: "
            + ", ".join(sorted(c["name"] for c in undecidable))
            + ".",
        ]
    return "\n".join(lines) + "\n"


def write_annotation_report(
    out_dir: str | Path,
    scores: list[CollectionScore],
    aggregate: dict,
    meta: dict | None = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta or {},
        "aggregate": aggregate,
        "collections": [s.to_dict() for s in scores],
    }
    (out_dir / "annotations.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "annotations.md").write_text(
        render_annotation_markdown(payload), encoding="utf-8"
    )
    return out_dir / "annotations.json"
