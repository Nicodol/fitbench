"""Metric validation on the synthetic fixture: null controls then planted defects."""

import numpy as np
import pytest

from parrhesia.io_tifxyz import INVALID, QuadSurface
from parrhesia.metrics import WindingFamilySoup, score_patch, score_patches
from parrhesia.synthetic import (
    collapse_gap,
    make_family,
    radial_drift,
    sample_patch,
    swap_band,
)

PITCH = 10.0


@pytest.fixture(scope="module")
def clean_family():
    return make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)


@pytest.fixture(scope="module")
def heldout_patches():
    """Analytic patches on three windings, never derived from the family meshes."""
    z_range = (8.0, 52.0)
    return {
        "p11": sample_patch(11, PITCH, (0.4, 1.6), z_range),
        "p13": sample_patch(13, PITCH, (2.0, 3.4), z_range),
        "p14": sample_patch(14, PITCH, (4.0, 5.5), z_range),
    }


def chordal_bound(patches, family):
    """Max expected null-control distance: both the patch grid and the family
    triangulation are chordal approximations of the same smooth spiral, so the
    worst-case gap is the sum of the two sagittas at the largest radius."""
    bound = 0.0
    theta_count = next(iter(family.values())).zyxs.shape[1]
    for p in patches.values():
        r = np.linalg.norm(p.valid_zyxs[:, 1:], axis=-1).max()
        cols = p.zyxs.shape[1]
        # patch theta step is unknown here; recover it from its own arc length
        first, last = p.zyxs[0, 0, 1:], p.zyxs[0, -1, 1:]
        arc = np.arccos(
            np.clip(np.dot(first, last) / (np.linalg.norm(first) * np.linalg.norm(last)), -1, 1)
        )
        sag_patch = (r * arc / (cols - 1)) ** 2 / (8 * r)
        sag_family = (2 * np.pi * r / theta_count) ** 2 / (8 * r)
        bound = max(bound, sag_patch + sag_family)
    return bound


def test_null_control(clean_family, heldout_patches):
    scores, agg = score_patches(heldout_patches, clean_family, tau=6.0)
    by_id = {s.patch_id: s for s in scores}
    # Distances bounded by the computed chordal discretization, far below tau.
    assert agg["dist_max"] < 1.5 * chordal_bound(heldout_patches, clean_family)
    assert agg["frac_within_tau"] == 1.0
    # Perfect single-winding consistency and correct assignment.
    assert agg["min_single_winding_consistency"] == 1.0
    assert by_id["p11"].modal_winding == 11
    assert by_id["p13"].modal_winding == 13
    assert by_id["p14"].modal_winding == 14
    # Normals agree to a few degrees (chordal effect only: half the coarser
    # angular step, with margin).
    assert agg["normal_angle_p90_deg"] < 8.0


def test_z_range_restricts_scoring(clean_family):
    """A fit only models its own z window: points outside must not be scored."""
    patch = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0), rows=12)
    full = score_patch(patch, WindingFamilySoup.from_family(clean_family), patch_id="p")
    windowed = score_patch(
        patch, WindingFamilySoup.from_family(clean_family), patch_id="p", z_range=(20.0, 40.0)
    )
    assert windowed.n_points < full.n_points
    assert (windowed.point_zyx[:, 0] >= 20.0).all() and (windowed.point_zyx[:, 0] <= 40.0).all()

    # A patch entirely outside the window raises rather than scoring nothing.
    with pytest.raises(ValueError):
        score_patch(
            patch, WindingFamilySoup.from_family(clean_family), patch_id="p",
            z_range=(500.0, 600.0),
        )


def test_score_patches_skips_out_of_window(clean_family):
    near = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0))
    far = sample_patch(12, PITCH, (2.0, 3.0), (400.0, 460.0))
    scores, agg = score_patches({"near": near, "far": far}, clean_family, z_range=(8.0, 52.0))
    assert [s.patch_id for s in scores] == ["near"]
    assert agg["n_patches"] == 1 and agg["n_patches_skipped"] == 1
    assert agg["z_range"] == [8.0, 52.0]


def test_determinism(clean_family, heldout_patches):
    _, agg1 = score_patches(heldout_patches, clean_family)
    _, agg2 = score_patches(heldout_patches, clean_family)
    assert agg1 == agg2


def test_radial_drift_detected_by_distance_not_topology(clean_family, heldout_patches):
    drifted = radial_drift(clean_family, amplitude=3.0)
    _scores, agg = score_patches(heldout_patches, drifted, tau=6.0)
    # Distance grows to the drift amplitude at the worst theta...
    assert agg["dist_p99"] > 2.0
    # ...bounded by the amplitude plus chordal slack...
    assert agg["dist_max"] < 3.0 + 1.5 * chordal_bound(heldout_patches, clean_family)
    # ...but consistency stays perfect: drift is not a sheet switch.
    assert agg["min_single_winding_consistency"] == 1.0


def test_swap_band_detected_by_consistency(clean_family):
    # Patch on winding 11 straddling the swapped theta band [1.0, 2.0).
    patch = sample_patch(11, PITCH, (0.5, 2.5), (8.0, 52.0), cols=20)
    swapped = swap_band(clean_family, 11, 12, theta_band=(1.0, 2.0))
    fam_soup = WindingFamilySoup.from_family(swapped)
    score = score_patch(patch, fam_soup, patch_id="straddle")
    # Inside the band the nearest surface is now labeled 12, outside it is 11:
    # consistency must drop well below 1 while distances stay tiny.
    assert score.dist_max < 0.2
    assert score.single_winding_consistency < 0.85
    assert sorted(np.unique(score.point_winding)) == [11, 12]


def test_collapse_detected_by_distance(clean_family):
    # Family's winding 12 collapses onto 11 in a band; a held-out patch that
    # lies where winding 12 should be is suddenly far from every surface.
    collapsed = collapse_gap(clean_family, 12, theta_band=(3.0, 4.0), factor=0.95)
    patch = sample_patch(12, PITCH, (3.1, 3.9), (8.0, 52.0))
    fam_soup = WindingFamilySoup.from_family(collapsed)
    score = score_patch(patch, fam_soup, patch_id="on-collapsed")
    assert score.dist_p50 > PITCH * 0.4  # several voxels: unmissable
    assert score.frac_within_tau < 0.5


def make_two_winding_patch():
    """A patch whose left part lies on winding 11 and right part on winding 12,
    separated by an invalid column, with a winding.tif-style grid (0 and 1)."""
    left = sample_patch(11, PITCH, (0.4, 1.2), (8.0, 52.0), rows=8, cols=5)
    right = sample_patch(12, PITCH, (1.4, 2.6), (8.0, 52.0), rows=8, cols=8)
    sep = np.full((8, 1, 3), INVALID, dtype=np.float32)
    zyxs = np.concatenate([left.zyxs, sep, right.zyxs], axis=1)
    winding = np.concatenate(
        [np.zeros((8, 5)), np.zeros((8, 1)), np.ones((8, 8))], axis=1
    ).astype(np.float32)
    return QuadSurface(zyxs=zyxs, scale=left.scale, winding=winding)


def test_winding_agreement_null_and_broken(clean_family):
    patch = make_two_winding_patch()
    ok = score_patch(patch, WindingFamilySoup.from_family(clean_family), patch_id="two-wind")
    assert ok.winding_agreement == 1.0

    # Swap the two windings across the full circle: the fit's labeling of the
    # two sheets is now inverted, and the relative-winding agreement collapses.
    broken = swap_band(clean_family, 11, 12, theta_band=(0.0, 2 * np.pi))
    bad = score_patch(patch, WindingFamilySoup.from_family(broken), patch_id="two-wind")
    assert bad.winding_agreement is not None and bad.winding_agreement < 0.7

    # The published aggregate must reflect it too (an aggregate replaced by a
    # constant would pass any per-patch test).
    _, agg_ok = score_patches({"tw": patch}, clean_family)
    _, agg_bad = score_patches({"tw": patch}, broken)
    assert agg_ok["mean_winding_agreement"] == 1.0
    assert agg_bad["mean_winding_agreement"] < 0.7


def test_normal_agreement_fires_on_tilted_patch(clean_family):
    """A patch whose rows are alternately pushed in/out radially stays close to
    the surface but its quads tilt hard: the normal metric must fire (its null
    control alone cannot prove the metric is alive)."""
    patch = sample_patch(12, PITCH, (0.5, 1.5), (8.0, 52.0), rows=8, cols=12)
    zyxs = patch.zyxs.astype(np.float64)
    radial = zyxs[..., 1:] / np.linalg.norm(zyxs[..., 1:], axis=-1, keepdims=True)
    amp = 2.0 * (-1.0) ** np.arange(zyxs.shape[0])
    zyxs[..., 1:] = zyxs[..., 1:] + radial * amp[:, None, None]
    tilted = QuadSurface(zyxs.astype(np.float32), patch.scale)

    soup = WindingFamilySoup.from_family(clean_family)
    flat = score_patch(patch, soup, patch_id="flat")
    score = score_patch(tilted, soup, patch_id="tilted")
    # rows are ~6.3 vox apart, alternating +/-2 vox radially: tilt ~32 deg
    assert score.dist_max < 2.5  # still on the sheet...
    assert score.normal_angle_p50_deg > 15.0  # ...but the orientation is wrong
    assert flat.normal_angle_p50_deg < 8.0

    # And the point-weighted aggregate must move with it.
    _, agg_flat = score_patches({"p": patch}, clean_family)
    _, agg_tilt = score_patches({"p": tilted}, clean_family)
    assert agg_tilt["normal_angle_p90_deg"] > agg_flat["normal_angle_p90_deg"] + 10.0


def test_aggregates_match_per_point_data(clean_family, heldout_patches):
    """The published aggregates must be recomputable from the per-point payload:
    an aggregate short-circuited to a constant fails here."""
    scores, agg = score_patches(heldout_patches, clean_family, tau=6.0)
    all_dist = np.sort(np.concatenate([s.point_dist for s in scores]))
    for name, q in [("dist_p50", 50), ("dist_p90", 90), ("dist_p99", 99)]:
        assert agg[name] == float(np.percentile(all_dist, q))
    assert agg["dist_max"] == float(all_dist.max())
    assert agg["frac_within_tau"] == float((all_dist <= 6.0).mean())
    assert agg["mean_single_winding_consistency"] == 1.0
    assert agg["mean_sheet_consistency"] == 1.0
    assert agg["min_sheet_consistency"] == 1.0
    assert agg["n_points"] == sum(s.n_points for s in scores)


def test_seam_crossing_patch_is_one_sheet(clean_family):
    """A perfect patch crossing the theta seam legitimately spans windings w
    and w+1 (that is what winding indexing means on a spiral), so the raw
    modal-winding fraction drops by construction; the sheet consistency built
    on the continuous winding coordinate must stay exactly 1."""
    soup = WindingFamilySoup.from_family(clean_family)
    seam = sample_patch(13, PITCH, (-0.5, 0.5), (8.0, 52.0), rows=10, cols=20)
    s = score_patch(seam, soup, patch_id="seam")
    # p50, not max: the synthetic family itself has no bridging quad at the
    # seam (its windings are open grids over [0, 2pi)), so a few edge points
    # see a chordal gap. The patch is on the ideal spiral everywhere.
    assert s.dist_p50 < 0.5
    assert s.single_winding_consistency < 1.0  # structural split across 12/13
    assert sorted(np.unique(s.point_winding)) == [12, 13]
    assert s.sheet_consistency == 1.0  # but it is one continuous sheet

    # A true sheet switch away from the seam must still fire on both.
    swapped = swap_band(clean_family, 11, 12, theta_band=(1.0, 2.0))
    straddle = sample_patch(11, PITCH, (0.5, 2.5), (8.0, 52.0), cols=20)
    bad = score_patch(straddle, WindingFamilySoup.from_family(swapped), patch_id="switch")
    assert bad.sheet_consistency < 0.85
    assert bad.single_winding_consistency < 0.85


def test_evidence_leakage_and_unseen_aggregate(clean_family):
    """A near-duplicate of a held-out patch among the fit inputs (jittered, so
    no hash can catch it) must show up in the leakage profile, and the unseen
    aggregate must keep only the genuinely far evidence."""
    # Different sizes on purpose: with equal point counts, inverting the
    # unseen selection or the leakage fractions would produce the same numbers
    # and this test could not tell (found by the mutation audit).
    held_a = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0), rows=8, cols=12)
    held_b = sample_patch(13, PITCH, (2.0, 3.4), (8.0, 52.0), rows=8, cols=16)
    leak = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0), normal_jitter=0.1)

    scores, agg = score_patches(
        {"a": held_a, "b": held_b}, clean_family,
        input_family={"leak": leak}, unseen_min_dist=2.0,
    )
    by_id = {s.patch_id: s for s in scores}
    n_a, n_b = by_id["a"].n_points, by_id["b"].n_points

    leakage = agg["evidence_leakage"]
    assert leakage["n_input_patches"] == 1
    # patch a sits within jitter distance of the leaked input; patch b is on
    # another winding two turns away.
    assert abs(leakage["frac_within_2_vox"] - n_a / (n_a + n_b)) < 0.02
    assert by_id["a"].n_points_unseen < 0.02 * n_a
    assert by_id["b"].n_points_unseen == n_b

    unseen = agg["unseen"]
    assert unseen["n_patches"] == 1  # a has too few unseen points and is excluded
    assert unseen["n_patches_excluded"] == 1
    assert unseen["n_points"] == n_b
    assert unseen["dist_p50"] < 1.0
    assert unseen["mean_sheet_consistency"] == 1.0

    # Without fit inputs there must be no leakage/unseen section at all.
    _, agg_plain = score_patches({"a": held_a, "b": held_b}, clean_family)
    assert "evidence_leakage" not in agg_plain and "unseen" not in agg_plain


def test_nan_vertices_are_invalid_not_fatal(clean_family):
    """Non-finite coordinates are invalid data, not crashes and not silent
    skips: the rest of the patch must still be scored."""
    patch = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0))
    zyxs = patch.zyxs.copy()
    zyxs[:2, :3] = np.nan
    # The loader maps non-finite to the sentinel; scoring the normalized
    # surface must succeed on the remaining valid quads.
    norm = zyxs.copy()
    norm[~np.isfinite(norm).all(axis=-1)] = INVALID
    normalized = QuadSurface(zyxs=norm, scale=patch.scale)
    s = score_patch(normalized, WindingFamilySoup.from_family(clean_family), patch_id="nan")
    assert s.n_points < patch.quad_centers()[0].shape[0]
    assert np.isfinite(s.point_dist).all()


def test_sheet_consistency_multi_turn_band(clean_family):
    """A perfect band following the spiral across two full turns is ONE
    sheet. A fixed-width window over u misreads any patch longer than the
    window (real Paris 4 bands span 12+ turns); the component-based
    definition must score it 1.0."""
    band = sample_patch(
        11, PITCH, (0.2, 0.2 + 4 * np.pi), (8.0, 52.0), rows=6, cols=120
    )
    s = score_patch(band, WindingFamilySoup.from_family(clean_family), patch_id="band")
    assert s.dist_p50 < 0.5
    assert s.single_winding_consistency < 0.7  # structural: the band spans windings
    assert s.sheet_consistency == 1.0  # but it is one continuous sheet


def test_leakage_union_over_multiple_inputs(clean_family):
    """The leakage measurement must be the union over ALL fit inputs,
    verified against an independent per-input minimum: a soup broken past
    input number one flatters the unseen numbers (review-2 blocking finding)."""
    from parrhesia.geometry import TriangleSoup, surface_distance

    held = {
        "a": sample_patch(11, PITCH, (0.4, 1.4), (8.0, 52.0), rows=8, cols=12),
        "b": sample_patch(13, PITCH, (2.0, 3.0), (8.0, 52.0), rows=8, cols=16),
        "c": sample_patch(14, PITCH, (4.0, 5.0), (8.0, 52.0), rows=8, cols=20),
    }
    inputs = {
        "i1": sample_patch(11, PITCH, (0.4, 1.4), (8.0, 52.0), rows=7, cols=11,
                           normal_jitter=0.1),
        "i2": sample_patch(13, PITCH, (2.0, 3.0), (8.0, 52.0), rows=6, cols=9,
                           normal_jitter=0.1),
        "i3": sample_patch(14, PITCH, (4.0, 5.0), (8.0, 52.0), rows=10, cols=7,
                           normal_jitter=0.1),
    }
    scores, agg = score_patches(
        held, clean_family, input_family=inputs, unseen_min_dist=2.0
    )
    all_ref = []
    for s in scores:
        dmin = np.full(s.n_points, np.inf)
        for surf in inputs.values():
            v, f = surf.triangles()
            soup = TriangleSoup(v.astype(np.float64), f)
            dmin = np.minimum(dmin, surface_distance(s.point_zyx, soup).dist)
        np.testing.assert_allclose(s.point_input_dist, dmin, atol=1e-9)
        assert s.n_points_unseen == int((dmin > 2.0).sum())
        all_ref.append(dmin)
    ref = np.concatenate(all_ref)
    leak = agg["evidence_leakage"]
    for t in (0.5, 1.0, 2.0, 6.0):
        assert leak[f"frac_within_{t:g}_vox"] == float((ref <= t).mean())


def test_absolute_distance_anchor(clean_family):
    """A patch displaced radially by a known delta must read that delta,
    bracketed both sides: this pins any consistent rescaling of the
    published distances, which per-defect threshold tests cannot."""
    delta = 3.7
    patch = sample_patch(12, PITCH, (0.6, 1.4), (8.0, 52.0))
    zyxs = patch.zyxs.astype(np.float64)
    r = np.linalg.norm(zyxs[..., 1:], axis=-1, keepdims=True)
    zyxs[..., 1:] = zyxs[..., 1:] * (r + delta) / r
    moved = QuadSurface(zyxs.astype(np.float32), patch.scale)
    s = score_patch(moved, WindingFamilySoup.from_family(clean_family), patch_id="m")
    slack = 1.5 * chordal_bound({"p": patch}, clean_family) + 0.01
    assert delta - slack <= s.dist_p50 <= delta + slack
    assert delta - slack <= s.dist_max <= delta + slack


def test_aggregates_are_point_weighted_and_min_is_min(clean_family):
    """Two patches of very different sizes and different consistencies: the
    weighted aggregate must be exact and differ from the unweighted one, and
    min must be a min. All-1.0 null fixtures cannot pin any of this."""
    small_bad = sample_patch(11, PITCH, (0.5, 2.5), (8.0, 52.0), rows=4, cols=8)
    big_good = sample_patch(13, PITCH, (2.0, 3.4), (8.0, 52.0), rows=12, cols=24)
    swapped = swap_band(clean_family, 11, 12, theta_band=(1.0, 2.0))
    scores, agg = score_patches({"bad": small_bad, "good": big_good}, swapped)
    by_id = {s.patch_id: s for s in scores}
    assert by_id["bad"].sheet_consistency < 1.0
    assert by_id["good"].sheet_consistency == 1.0

    order = [s.patch_id for s in scores]
    w = np.array([by_id[p].n_points for p in order], dtype=np.float64)
    for metric in ("sheet_consistency", "single_winding_consistency"):
        vals = np.array([getattr(by_id[p], metric) for p in order])
        weighted = float(np.average(vals, weights=w))
        assert agg[f"mean_{metric}"] == weighted
        assert abs(weighted - float(np.mean(vals))) > 1e-9
        assert agg[f"min_{metric}"] == float(vals.min())
        assert agg[f"min_{metric}"] < agg[f"mean_{metric}"]
    angle_vals = np.array([by_id[p].normal_angle_p90_deg for p in order])
    assert agg["normal_angle_p90_deg"] == float(np.average(angle_vals, weights=w))


def test_engine_errors_propagate(clean_family, monkeypatch):
    """Only PatchSkip may be skipped; any other failure must propagate
    loudly instead of silently shrinking the evaluation set."""
    import parrhesia.metrics as m

    patch = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0))

    def boom(pts, soup, **kw):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(m, "surface_distance", boom)
    with pytest.raises(RuntimeError, match="engine exploded"):
        m.score_patches({"p": patch}, clean_family)


def test_tau_flows_into_fractions(clean_family):
    """tau must actually be used: a patch sitting ~4 vox off the surface is
    fully outside tau=2 and fully inside tau=6."""
    patch = sample_patch(12, PITCH, (0.6, 1.4), (8.0, 52.0))
    zyxs = patch.zyxs.astype(np.float64)
    r = np.linalg.norm(zyxs[..., 1:], axis=-1, keepdims=True)
    zyxs[..., 1:] = zyxs[..., 1:] * (r + 4.0) / r
    moved = QuadSurface(zyxs.astype(np.float32), patch.scale)
    s2, agg2 = score_patches({"p": moved}, clean_family, tau=2.0)
    s6, agg6 = score_patches({"p": moved}, clean_family, tau=6.0)
    assert agg2["tau"] == 2.0 and agg6["tau"] == 6.0
    assert agg2["frac_within_tau"] == 0.0
    assert agg6["frac_within_tau"] == 1.0
    # The per-patch fraction must use tau too, not a hardcoded default.
    assert s2[0].frac_within_tau == 0.0
    assert s6[0].frac_within_tau == 1.0


def test_unseen_min_dist_flows_into_selection(clean_family):
    """The unseen threshold must flow through: an input sitting ~1.5 vox from
    the evidence flips between seen and unseen as the threshold crosses it."""
    held = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0))
    zyxs = held.zyxs.astype(np.float64)
    r = np.linalg.norm(zyxs[..., 1:], axis=-1, keepdims=True)
    zyxs[..., 1:] = zyxs[..., 1:] * (r + 1.5) / r
    inp = QuadSurface(zyxs.astype(np.float32), held.scale)
    s1, agg1 = score_patches(
        {"h": held}, clean_family, input_family={"i": inp}, unseen_min_dist=1.0
    )
    s2, agg2 = score_patches(
        {"h": held}, clean_family, input_family={"i": inp}, unseen_min_dist=2.0
    )
    assert s1[0].n_points_unseen == s1[0].n_points
    assert s2[0].n_points_unseen == 0
    assert agg1["unseen"]["n_points"] == s1[0].n_points
    assert agg1["unseen"]["unseen_min_dist"] == 1.0
    assert agg2["unseen"]["n_points"] == 0
    assert agg2["unseen"]["n_patches_excluded"] == 1


def test_min_unseen_points_boundary(clean_family):
    """The 8-point floor for entering the unseen aggregate is load-bearing:
    7 unseen points exclude a patch, 14 include it."""
    held = sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0), rows=8, cols=12)
    # Inputs identical to the held patch over a theta prefix: uncovered quad
    # columns sit >= one column pitch (~12 vox) from the input surface.
    cover_all_but_one = sample_patch(11, PITCH, (0.4, 1.46), (8.0, 52.0), rows=8, cols=20)
    cover_all_but_two = sample_patch(11, PITCH, (0.4, 1.35), (8.0, 52.0), rows=8, cols=20)

    s1, agg1 = score_patches(
        {"h": held}, clean_family, input_family={"i": cover_all_but_one},
        unseen_min_dist=2.0,
    )
    assert s1[0].n_points_unseen == 7
    assert agg1["unseen"]["n_patches"] == 0
    assert agg1["unseen"]["n_patches_excluded"] == 1

    s2, agg2 = score_patches(
        {"h": held}, clean_family, input_family={"i": cover_all_but_two},
        unseen_min_dist=2.0,
    )
    assert s2[0].n_points_unseen == 14
    assert agg2["unseen"]["n_patches"] == 1
    assert agg2["unseen"]["n_points"] == 14
