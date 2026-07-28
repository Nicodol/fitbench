"""Metric validation on the synthetic fixture: null controls then planted defects."""

import numpy as np
import pytest

from fitbench.io_tifxyz import INVALID, QuadSurface
from fitbench.metrics import WindingFamilySoup, score_patch, score_patches
from fitbench.synthetic import (
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
