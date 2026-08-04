"""The winding labels VALIDATION section 9 manufactures must be checkable.

Section 9 scores a real fit against labels built from that fit's own
assignment, and its null control reads winding agreement 1.0. That control
cannot police the label builder: ``score_patch`` rounds the labels before
comparing them, so labels invented at a boundary round straight back onto the
assignment they were derived from. Deleting the unambiguity rule from
``winding_label_grid`` leaves the null reading exactly 1.0 while quads whose
corners disagree quietly enter the labelled count the section publishes as
31,080 of 49,458 (ten of them, on the demo fixture this was measured on).

So the invariant is pinned here instead, against an independently written
oracle: a quad carries a label exactly when every quad in its clipped 3x3
neighbourhood was scored and they all agree, and the label is then that
common value. Soundness, completeness and the count, in one assertion.

The three riders below cover the other numbers of that section whose producers
nothing else reaches: the band-edge margin, the percentile helper behind every
"x -> y" distance pair, and the degenerate-face detector, which only ever
publishes zero and would publish the same zero if it were dead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from planted_defects_real import (
    _quantiles,
    degenerate_face_counts,
    grid_row_spacing,
    winding_label_grid,
)

from spiralcheck.geometry import TriangleSoup
from spiralcheck.io_tifxyz import QuadSurface
from spiralcheck.synthetic import make_family


def _oracle(scored: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Per-quad label, written from the rule rather than from the code: the
    common winding of the clipped 3x3 neighbourhood, when every quad in it was
    scored and they all agree; NaN otherwise."""
    rows, cols = scored.shape
    out = np.full((rows, cols), np.nan)
    for r in range(rows):
        for c in range(cols):
            block = [
                (i, j)
                for i in range(max(r - 1, 0), min(r + 2, rows))
                for j in range(max(c - 1, 0), min(c + 2, cols))
            ]
            if all(scored[i, j] for i, j in block):
                vals = {value[i, j] for i, j in block}
                if len(vals) == 1:
                    out[r, c] = vals.pop()
    return out


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_winding_labels_are_sound_complete_and_counted(seed):
    """Random grids with holes and several windings, both directions checked."""
    rng = np.random.default_rng(seed)
    h, w = int(rng.integers(8, 15)), int(rng.integers(8, 15))
    # A winding field that steps along the columns like a real patch's does at
    # the theta seam, plus unscored quads standing in for the z window and for
    # invalid corners. The last assertion checks these leave both outcomes on
    # the table.
    value = np.repeat(np.arange(w - 1) // 4, h - 1).reshape(w - 1, h - 1).T + 40
    scored = rng.random((h - 1, w - 1)) > 0.12
    quad_idx = np.stack(np.nonzero(scored), axis=-1)
    patch = QuadSurface(
        zyxs=np.zeros((h, w, 3), dtype=np.float32),
        scale=np.array([1.0, 1.0], dtype=np.float32),
    )

    grid, n_labelled = winding_label_grid(
        patch, quad_idx, value[quad_idx[:, 0], quad_idx[:, 1]].astype(float)
    )
    quad_mean = (grid[:-1, :-1] + grid[1:, :-1] + grid[:-1, 1:] + grid[1:, 1:]) / 4.0
    expected = _oracle(scored, value)

    # Soundness and completeness in one: the labelled set and its values are
    # exactly the oracle's, NaN for NaN.
    assert np.array_equal(quad_mean, expected, equal_nan=True)
    # ... and the published count is that set's size, not something looser.
    assert n_labelled == int(np.isfinite(expected).sum())
    # The fixture must actually exercise both outcomes, or the assertions above
    # are satisfied by a grid that is entirely labelled or entirely not.
    assert 0 < np.isfinite(expected).sum() < expected.size


def test_grid_row_spacing_recovers_the_fixture_z_step():
    """The band-edge margin section 9 stands its exactness claim clear of."""
    family = make_family(num_windings=3, pitch=10.0, z_count=8, z_step=7.0)
    assert grid_row_spacing(family) == pytest.approx(7.0)


def test_quantiles_reports_a_median_not_a_mean():
    """Every 'x -> y' distance pair in section 9 comes through here, on
    distributions with heavy tails where the two differ a lot."""
    q = _quantiles(np.array([0.0, 0.0, 0.0, 0.0, 10.0]))
    assert q["p50"] == 0.0
    assert q["max"] == 10.0
    assert q["n"] == 5


def test_degenerate_face_detector_can_report_something_other_than_zero():
    """Section 9 publishes 'zero faces with a duplicated vertex pair' on every
    mutated family. A detector wired to zero would publish the same thing, so
    show it firing on a deliberately pinched quad."""
    zyxs = np.zeros((2, 2, 3), dtype=np.float32)
    zyxs[0, 0] = [0.0, 0.0, 0.0]
    zyxs[1, 0] = [0.0, 0.0, 0.0]  # pinch: the quad's bl and tl coincide
    zyxs[0, 1] = [0.0, 1.0, 0.0]
    zyxs[1, 1] = [1.0, 1.0, 0.0]
    surface = QuadSurface(zyxs=zyxs, scale=np.array([1.0, 1.0], dtype=np.float32))
    vertices, faces = surface.triangles()
    counts = degenerate_face_counts(TriangleSoup(vertices, faces))
    assert counts["first_two_vertices_equal"] == 1
