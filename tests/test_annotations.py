"""Winding annotations: villa's point-collection format, and the wrap index.

The published real-data number (VALIDATION.md section 10) rests on three
properties, so each has a test that fails when it stops holding: the loader
reads villa's coordinate convention rather than a guessed one; the wrap index
subtracts the azimuth a collection travels, without which any collection
spanning more than half a turn would be reported as broken; and a point too far
from every surface is declined rather than assigned a winding.
"""

import json

import numpy as np
import pytest

from spiralcheck.annotations import (
    WRAP_DECISION_TURNS,
    aggregate_collection_scores,
    load_point_collections,
    render_annotation_markdown,
    score_collection,
    write_annotation_report,
)
from spiralcheck.metrics import WindingFamilySoup
from spiralcheck.synthetic import make_family

PITCH = 10.0
CENTER = (0.0, 0.0)
FIRST = 10


def family_soup():
    return WindingFamilySoup.from_family(
        make_family(
            num_windings=8, first_winding=FIRST, pitch=PITCH, z_count=16, center_yx=CENTER
        )
    )


def point_on_winding(winding: int, theta: float, z: float, radial_offset: float = 0.0):
    """A point exactly on the ideal scroll, in villa's ``p`` order (x, y, z)."""
    total = winding * 2 * np.pi + theta
    radius = PITCH * total / (2 * np.pi) + radial_offset
    return [
        float(CENTER[1] + np.cos(total) * radius),
        float(CENTER[0] + np.sin(total) * radius),
        float(z),
    ]


def write_pcl(tmp_path, name, collections):
    """``collections``: list of (collection name, [(p, wind_a), ...], metadata)."""
    payload = {"vc_pointcollections_json_version": "1", "collections": {}}
    for i, (col_name, points, metadata) in enumerate(collections):
        payload["collections"][str(i + 1)] = {
            "name": col_name,
            "metadata": metadata,
            "points": {
                str(1000 + j): {"p": p, "wind_a": w, "creation_time": 0}
                for j, (p, w) in enumerate(points)
            },
        }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def same_winding_collection(tmp_path, winding, thetas, z=20.0, name="same_wrap1"):
    points = [(point_on_winding(winding, t, z), None) for t in thetas]
    return load_point_collections(
        write_pcl(tmp_path, "same.json", [(name, points, {"winding_is_absolute": False})])
    )[0]


def test_loader_follows_villa_coordinate_and_ordering_conventions(tmp_path):
    """``p`` is (x, y, z) and points are id-sorted, as villa's reader does it.

    A loader that took ``p`` as (z, y, x) would still run and still produce
    numbers, which is exactly why this is pinned.
    """
    path = write_pcl(
        tmp_path,
        "c.json",
        [("col9", [([1.0, 2.0, 3.0], 5.0), ([4.0, 5.0, 6.0], 7.0)], {})],
    )
    (col,) = load_point_collections(path)
    assert col.name == "col9"
    assert col.source == "c.json"
    np.testing.assert_allclose(col.zyx, [[3.0, 2.0, 1.0], [6.0, 5.0, 4.0]])
    np.testing.assert_allclose(col.wind_a, [5.0, 7.0])
    assert col.point_ids.tolist() == [1000, 1001]
    assert col.kind == "relative"


def test_loader_reads_zyx_key_when_present(tmp_path):
    payload = {
        "vc_pointcollections_json_version": "1",
        "collections": {
            "1": {
                "name": "c",
                "points": {"1": {"zyx": [7.0, 8.0, 9.0], "p": [0.0, 0.0, 0.0]}},
            }
        },
    }
    path = tmp_path / "z.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    (col,) = load_point_collections(path)
    np.testing.assert_allclose(col.zyx, [[7.0, 8.0, 9.0]])


def test_loader_rejects_unsupported_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"vc_pointcollections_json_version": "2"}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        load_point_collections(path)


def test_unannotated_collection_normalises_to_zero_like_villa(tmp_path):
    """Villa's ``normalise_pcl_winding_annotations``: no annotation anywhere
    means "same winding", which is the zero-delta case, not missing data."""
    col = same_winding_collection(tmp_path, 12, [0.1, 0.3])
    assert col.kind == "same-winding"
    assert not np.isfinite(col.wind_a).any()
    normalised, dropped = col.normalised_wind_a()
    np.testing.assert_array_equal(normalised, [0.0, 0.0])
    assert dropped == 0


def test_mixed_annotation_drops_unannotated_points_and_says_so(tmp_path):
    points = [
        (point_on_winding(12, 0.1, 20.0), 0.0),
        (point_on_winding(12, 0.2, 20.0), None),
        (point_on_winding(13, 0.3, 20.0), 1.0),
    ]
    (col,) = load_point_collections(
        write_pcl(tmp_path, "m.json", [("col1", points, {})])
    )
    score = score_collection(col, family_soup(), umbilicus=CENTER)
    assert score.n_unannotated_dropped == 1
    assert score.n_in_window == 2


def test_honoured_same_winding_collection_scores_one(tmp_path):
    col = same_winding_collection(tmp_path, 13, np.linspace(0.2, 1.2, 9))
    score = score_collection(col, family_soup(), umbilicus=CENTER)
    assert score.n_within_tau == 9
    assert score.agreement == 1.0
    assert score.offenders == []
    assert score.wrap_index_spread < WRAP_DECISION_TURNS / 10


def test_azimuth_correction_keeps_a_long_arc_on_one_winding(tmp_path):
    """A collection following one winding for three quarters of a turn is
    honoured, and its wrap index barely moves.

    The continuous winding coordinate ``u`` grows by 0.75 over this arc, which
    is past the half-turn decision boundary, so an implementation that forgot to
    subtract the azimuth would report this clean collection as broken. The
    spread assertion is what distinguishes "the correction is applied" from
    "the arc happened to stay inside one winding id".
    """
    thetas = np.linspace(0.1, 0.1 + 1.5 * np.pi, 12)
    col = same_winding_collection(tmp_path, 14, thetas)
    soup = family_soup()
    score = score_collection(col, soup, umbilicus=CENTER)
    assert score.agreement == 1.0

    from spiralcheck.geometry import surface_distance

    u = soup.face_u[surface_distance(col.zyx, soup.soup).face_idx]
    assert u.max() - u.min() > 0.6  # uncorrected, this alone would trip the rule
    assert score.wrap_index_spread < 0.1


def test_point_displaced_one_pitch_is_reported_a_whole_turn_off(tmp_path):
    """The planted failure is one winding, and the reported offset is one turn."""
    thetas = np.linspace(0.2, 1.0, 8)
    points = [(point_on_winding(13, t, 20.0), None) for t in thetas]
    points[4] = (point_on_winding(13, thetas[4], 20.0, radial_offset=PITCH), None)
    (col,) = load_point_collections(
        write_pcl(tmp_path, "d.json", [("same_wrap2", points, {})])
    )
    score = score_collection(col, family_soup(), umbilicus=CENTER)
    assert score.n_within_tau == 8
    assert score.n_agree == 7
    assert len(score.offenders) == 1
    assert score.offenders[0]["wrap_offset_rounded"] == 1
    assert abs(score.offenders[0]["wrap_offset"] - 1.0) < 0.05


def test_relative_deltas_are_read_from_the_annotation(tmp_path):
    """Points annotated one winding apart must land one winding apart.

    The same geometry annotated as *same* winding must fail, which is what
    proves the annotation is read at all rather than the geometry alone.
    """
    theta = 0.7
    geometry = [point_on_winding(13 + k, theta, 20.0) for k in range(4)]
    honoured = load_point_collections(
        write_pcl(
            tmp_path,
            "rel.json",
            [("col1", [(p, float(k)) for k, p in enumerate(geometry)], {})],
        )
    )[0]
    contradicted = load_point_collections(
        write_pcl(
            tmp_path, "same.json", [("col2", [(p, None) for p in geometry], {})]
        )
    )[0]
    soup = family_soup()
    assert score_collection(honoured, soup, umbilicus=CENTER).agreement == 1.0
    bad = score_collection(contradicted, soup, umbilicus=CENTER)
    assert bad.n_within_tau == 4
    assert bad.n_agree < 4


def test_far_points_are_declined_not_assigned(tmp_path):
    """A point nowhere near the family lowers coverage, never the agreement."""
    points = [(point_on_winding(13, t, 20.0), None) for t in (0.3, 0.5, 0.7)]
    points.append(([9999.0, 9999.0, 20.0], None))
    (col,) = load_point_collections(
        write_pcl(tmp_path, "far.json", [("same_wrap3", points, {})])
    )
    score = score_collection(col, family_soup(), umbilicus=CENTER, tau=6.0)
    assert score.n_in_window == 4
    assert score.n_within_tau == 3
    assert score.agreement == 1.0
    assert score.dist_max > 1000.0


def test_collection_with_no_decidable_point_reports_none_not_zero(tmp_path):
    (col,) = load_point_collections(
        write_pcl(tmp_path, "off.json", [("same_wrap4", [([9999.0, 9999.0, 20.0], None)], {})])
    )
    score = score_collection(col, family_soup(), umbilicus=CENTER)
    assert score.n_within_tau == 0
    assert score.agreement is None
    assert score.n_agree == 0
    assert score.dist_p50 is not None  # coverage is still reported
    # Per-point distances survive too. A caller profiling where the
    # undecidable evidence sits would otherwise drop exactly the collections
    # that are entirely undecidable, undercounting the thing being profiled.
    assert score.point_dist is not None
    assert len(score.point_dist) == 1


def test_z_range_excludes_points_outside_the_fitted_window(tmp_path):
    points = [(point_on_winding(13, 0.4, z), None) for z in (10.0, 20.0, 300.0)]
    (col,) = load_point_collections(
        write_pcl(tmp_path, "zr.json", [("same_wrap5", points, {})])
    )
    soup = family_soup()
    assert score_collection(col, soup, umbilicus=CENTER).n_in_window == 3
    windowed = score_collection(col, soup, umbilicus=CENTER, z_range=(0.0, 40.0))
    assert windowed.n_in_window == 2


def test_single_decidable_point_is_excluded_from_the_informative_count(tmp_path):
    """One decidable point is perfect by construction: it is its own reference."""
    lone = load_point_collections(
        write_pcl(
            tmp_path,
            "lone.json",
            [
                (
                    "same_wrap6",
                    [(point_on_winding(13, 0.4, 20.0), None), ([9999.0, 9999.0, 20.0], None)],
                    {},
                )
            ],
        )
    )[0]
    pair = same_winding_collection(tmp_path, 13, [0.4, 0.6], name="same_wrap7")
    soup = family_soup()
    scores = [
        score_collection(lone, soup, umbilicus=CENTER),
        score_collection(pair, soup, umbilicus=CENTER),
    ]
    agg = aggregate_collection_scores(scores)["all"]
    assert scores[0].n_within_tau == 1
    assert agg["n_collections_perfect"] == 2
    assert agg["n_collections_informative"] == 1
    assert agg["n_collections_informative_perfect"] == 1


def test_evenly_split_collection_indicts_both_sides(tmp_path):
    """A two-point collection whose points disagree has no majority.

    The reference is the collection's median wrap index, which for two points
    sits exactly between them, so both are half a turn away and both are
    reported. The metric cannot say which point is misplaced because the
    evidence does not say either; this is a documented shape of the answer,
    not a rounding accident.
    """
    points = [
        (point_on_winding(14, 0.5, 20.0), None),
        (point_on_winding(14, 0.5, 20.0, radial_offset=PITCH), None),
    ]
    (col,) = load_point_collections(
        write_pcl(tmp_path, "tie.json", [("same_wrap11", points, {})])
    )
    score = score_collection(col, family_soup(), umbilicus=CENTER)
    assert score.n_within_tau == 2
    assert score.n_agree == 0
    assert len(score.offenders) == 2


def test_aggregate_pools_over_points_not_collections(tmp_path):
    """A 9-point path and a 2-point pair are not equal evidence."""
    big = same_winding_collection(tmp_path, 13, np.linspace(0.2, 1.0, 9), name="big")
    small_points = [
        (point_on_winding(14, 0.5, 20.0), None),
        (point_on_winding(14, 0.5, 20.0, radial_offset=PITCH), None),
    ]
    small = load_point_collections(
        write_pcl(tmp_path, "s.json", [("small", small_points, {})])
    )[0]
    soup = family_soup()
    scores = [
        score_collection(big, soup, umbilicus=CENTER),
        score_collection(small, soup, umbilicus=CENTER),
    ]
    agg = aggregate_collection_scores(scores)["all"]
    assert (scores[0].n_agree, scores[0].n_within_tau) == (9, 9)
    assert (scores[1].n_agree, scores[1].n_within_tau) == (0, 2)
    assert agg["n_points_within_tau"] == 11
    # Point-weighted: 9/11. Averaging the two per-collection agreements would
    # give (1.0 + 0.0) / 2 = 0.5, which is the weighting this metric rejects.
    assert agg["agreement"] == pytest.approx(9 / 11)


def test_kinds_are_aggregated_separately(tmp_path):
    same = same_winding_collection(tmp_path, 13, [0.3, 0.5, 0.7], name="same_wrap8")
    rel_points = [
        (point_on_winding(13 + k, 0.7, 20.0), float(k)) for k in range(3)
    ]
    rel = load_point_collections(
        write_pcl(tmp_path, "r.json", [("col1", rel_points, {})])
    )[0]
    soup = family_soup()
    agg = aggregate_collection_scores(
        [
            score_collection(same, soup, umbilicus=CENTER),
            score_collection(rel, soup, umbilicus=CENTER),
        ]
    )
    assert agg["same-winding"]["n_points"] == 3
    assert agg["relative"]["n_points"] == 3
    assert agg["all"]["n_points"] == 6


def test_report_names_offenders_and_undecidable_collections(tmp_path):
    broken_points = [(point_on_winding(13, t, 20.0), None) for t in (0.2, 0.4, 0.6)]
    broken_points[1] = (point_on_winding(13, 0.4, 20.0, radial_offset=PITCH), None)
    broken = load_point_collections(
        write_pcl(tmp_path, "b.json", [("same_wrap9", broken_points, {})])
    )[0]
    nowhere = load_point_collections(
        write_pcl(tmp_path, "n.json", [("same_wrap10", [([9999.0, 9999.0, 20.0], None)], {})])
    )[0]
    soup = family_soup()
    scores = [
        score_collection(broken, soup, umbilicus=CENTER),
        score_collection(nowhere, soup, umbilicus=CENTER),
    ]
    out = write_annotation_report(
        tmp_path / "rep", scores, aggregate_collection_scores(scores), meta={"tau": 6.0}
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["collections"][0]["offenders"]
    text = render_annotation_markdown(payload)
    assert "same_wrap9" in text
    assert "same_wrap10" in text
    assert (out.parent / "annotations.md").exists()
