"""Intrinsic checks: silent on clean and drifted families, loud on topology defects."""

import numpy as np

from fitbench.intrinsic import intrinsic_report, resolve_umbilicus
from fitbench.synthetic import collapse_gap, make_family, punch_holes, radial_drift, swap_band

PITCH = 10.0
BAND = (1.0, 2.0)


def family():
    return make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)


def band_overlaps(rec, band, slack):
    """Circular check: does the record's bin midpoint fall in the band (mod 2 pi)?"""
    t0, t1 = rec["theta_range"]
    mid = ((t0 + t1) / 2) % (2 * np.pi)
    lo = (band[0] - slack) % (2 * np.pi)
    hi = (band[1] + slack) % (2 * np.pi)
    if lo <= hi:
        return lo <= mid <= hi
    return mid >= lo or mid <= hi


def test_clean_family_is_silent():
    rep = intrinsic_report(family())
    assert rep.n_violations == 0
    assert rep.n_collapsed == 0
    assert abs(rep.median_pitch - PITCH) / PITCH < 0.02
    assert all(v == 1.0 for v in rep.validity_per_winding.values())


def test_swap_band_fires_violations_localized():
    swapped = swap_band(family(), 11, 12, theta_band=BAND)
    rep = intrinsic_report(swapped)
    assert rep.n_violations > 0
    slack = 2 * np.pi / rep.theta_bins
    viol = [w for w in rep.worst if w["kind"] == "violation"]
    assert viol, "worst list must contain violations"
    for rec in viol:
        assert band_overlaps(rec, BAND, slack)
        # the swap breaks the pairs around windings 10/11/12
        assert rec["inner_winding"] in (10, 11)


def test_collapse_is_collapsed_not_violation():
    collapsed = collapse_gap(family(), 12, theta_band=(3.0, 4.0), factor=0.95)
    rep = intrinsic_report(collapsed)
    assert rep.n_violations == 0  # sheets touch but do not cross
    assert rep.n_collapsed > 0
    slack = 2 * np.pi / rep.theta_bins
    col = [w for w in rep.worst if w["kind"] == "collapsed"]
    assert col
    for rec in col:
        assert band_overlaps(rec, (3.0, 4.0), slack)
        assert rec["inner_winding"] == 11


def test_radial_drift_is_invisible_to_gaps():
    # The drift shifts every winding identically at a given theta, so the
    # inter-winding gaps are unchanged: intrinsic checks must stay silent
    # (catching this defect is the held-out distance metric's job).
    rep = intrinsic_report(radial_drift(family(), amplitude=2.0))
    assert rep.n_violations == 0
    assert rep.n_collapsed == 0
    assert abs(rep.median_pitch - PITCH) / PITCH < 0.02


def test_holes_reduce_validity_without_false_alarms():
    fam = family()
    rng = np.random.default_rng(3)
    fam[12] = punch_holes(fam[12], count=4, size=3, rng=rng)
    rep = intrinsic_report(fam)
    assert rep.n_violations == 0
    assert rep.validity_per_winding[12] < 1.0


def test_off_center_family_with_umbilicus_matches_centered():
    """The umbilicus must actually be subtracted before radii are computed: a
    family whose axis sits far from the origin, checked with its true axis,
    must report exactly what the centered family reports."""
    centered = intrinsic_report(family())
    off = make_family(
        num_windings=6, first_winding=10, pitch=PITCH, z_count=16,
        center_yx=(3000.0, 4000.0),
    )
    shifted = intrinsic_report(off, umbilicus=(3000.0, 4000.0))
    assert shifted.n_violations == 0
    assert shifted.n_collapsed == 0
    assert abs(shifted.median_pitch - centered.median_pitch) < 0.05
    # Sanity: with the wrong axis the same family looks broken, which is why
    # the CLI warns when no umbilicus is given.
    wrong = intrinsic_report(off, umbilicus=None)
    assert abs(wrong.median_pitch - PITCH) > 1.0 or wrong.n_violations > 0


def test_inflated_gap_fires():
    """A hole in the wrap (every winding from w outward pushed one extra pitch
    in a theta band) must be reported as inflated gaps, not violations."""
    fam = family()
    w0 = 13
    theta = np.linspace(0.0, 2 * np.pi, fam[w0].zyxs.shape[1], endpoint=False)
    cols = np.nonzero((theta >= 3.0) & (theta < 4.0))[0]
    for wid in fam:
        if wid < w0:
            continue
        zyxs = fam[wid].zyxs.copy().astype(np.float64)
        yx = zyxs[:, cols, 1:]
        r = np.linalg.norm(yx, axis=-1, keepdims=True)
        zyxs[:, cols, 1:] = yx / np.maximum(r, 1e-9) * (r + 2.0 * PITCH)
        fam[wid] = type(fam[wid])(zyxs.astype(np.float32), fam[wid].scale)
    rep = intrinsic_report(fam)
    assert rep.n_inflated > 0
    assert rep.n_violations == 0


def test_resolve_umbilicus_forms():
    z = np.array([0.0, 10.0, 20.0])
    np.testing.assert_allclose(resolve_umbilicus(None, z), 0.0)
    np.testing.assert_allclose(resolve_umbilicus((1.0, 2.0), z), [[1, 2]] * 3)
    poly = np.array([[0.0, 0.0, 0.0], [20.0, 4.0, 8.0]])
    np.testing.assert_allclose(
        resolve_umbilicus(poly, z), [[0, 0], [2, 4], [4, 8]], atol=1e-12
    )
    # villa's real umbilicus.json structure (dict with control_points)
    villa = {"control_points": [
        {"z": 0.0, "y": 1.0, "x": 2.0}, {"z": 20.0, "y": 5.0, "x": 10.0},
    ]}
    np.testing.assert_allclose(
        resolve_umbilicus(villa, z), [[1, 2], [3, 6], [5, 10]], atol=1e-12
    )
