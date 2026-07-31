"""Fixture sanity: the clean family is geometrically clean, defects are real."""

import numpy as np

from spiralcheck.geometry import TriangleSoup, surface_distance
from spiralcheck.io_tifxyz import INVALID
from spiralcheck.synthetic import (
    collapse_gap,
    make_family,
    punch_holes,
    radial_drift,
    sample_patch,
    swap_band,
)

PITCH = 10.0


def soup_of(surface):
    v, f = surface.triangles()
    return TriangleSoup(v, f)


def radii(surface, cols=None):
    yx = surface.zyxs[..., 1:]
    r = np.linalg.norm(yx, axis=-1)
    return r if cols is None else r[:, cols]


def test_family_shapes_and_radii():
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH)
    assert sorted(family) == [10, 11, 12, 13]
    # radius at theta=0 column equals winding * pitch
    for w, s in family.items():
        np.testing.assert_allclose(radii(s)[:, 0], w * PITCH, rtol=1e-6)


def test_patch_lies_on_its_winding():
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH)
    patch = sample_patch(11, PITCH, theta_range=(0.5, 2.0), z_range=(8.0, 40.0))
    soup = soup_of(family[11])
    result = surface_distance(patch.valid_zyxs.astype(np.float64), soup)
    # The analytic patch sits on the smooth spiral; the family is its chordal
    # triangulation (90 theta samples per turn), so the expected gap is the
    # chord sagitta: (2 pi r / n)^2 / (8 r). Assert within 1.5x of that bound.
    r_patch_max = np.linalg.norm(patch.valid_zyxs[:, 1:], axis=-1).max()
    theta_count = family[11].zyxs.shape[1]
    chord = 2 * np.pi * r_patch_max / theta_count
    sagitta = chord**2 / (8 * r_patch_max)
    assert result.dist.max() < 1.5 * sagitta
    # And it is far from the neighboring winding (about one pitch away).
    other = surface_distance(patch.valid_zyxs.astype(np.float64), soup_of(family[12]))
    assert other.dist.min() > PITCH * 0.5


def test_swap_band_moves_geometry():
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH)
    swapped = swap_band(family, 11, 12, theta_band=(1.0, 2.0))
    cols = np.nonzero(
        (np.linspace(0, 2 * np.pi, family[11].zyxs.shape[1], endpoint=False) >= 1.0)
        & (np.linspace(0, 2 * np.pi, family[11].zyxs.shape[1], endpoint=False) < 2.0)
    )[0]
    # Inside the band, winding 11 now carries winding 12's (larger) radius.
    assert (radii(swapped[11], cols) > radii(swapped[12], cols)).all()
    # Outside the band, order is unchanged.
    other_cols = [c for c in range(family[11].zyxs.shape[1]) if c not in set(cols.tolist())]
    assert (radii(swapped[11], other_cols) < radii(swapped[12], other_cols)).all()


def test_collapse_gap_shrinks_spacing():
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH)
    collapsed = collapse_gap(family, 12, theta_band=(3.0, 4.0), factor=0.95)
    cols = np.nonzero(
        (np.linspace(0, 2 * np.pi, family[12].zyxs.shape[1], endpoint=False) >= 3.0)
        & (np.linspace(0, 2 * np.pi, family[12].zyxs.shape[1], endpoint=False) < 4.0)
    )[0]
    gap_before = radii(family[12], cols) - radii(family[11], cols)
    gap_after = radii(collapsed[12], cols) - radii(collapsed[11], cols)
    assert (gap_after < gap_before * 0.1).all()


def test_radial_drift_bounded_and_order_preserving():
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH)
    drifted = radial_drift(family, amplitude=2.0)
    for w in family:
        delta = np.abs(radii(drifted[w]) - radii(family[w]))
        assert delta.max() <= 2.0 + 1e-3
    # Order preserved (amplitude < pitch / 2 and same shift per winding).
    for w in [11, 12, 13]:
        assert (radii(drifted[w]) > radii(drifted[w - 1])).all()


def test_punch_holes_invalidates():
    family = make_family(num_windings=2, first_winding=10, pitch=PITCH)
    rng = np.random.default_rng(7)
    holed = punch_holes(family[10], count=3, size=3, rng=rng)
    n_invalid = (~holed.valid_vertex_mask).sum()
    assert n_invalid >= 9  # at least one full block (blocks may overlap)
    assert (holed.zyxs[~holed.valid_vertex_mask] == INVALID).all()
