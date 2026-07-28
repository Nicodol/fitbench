"""The frozen contract of sheet consistency.

This metric was rewritten three times (fixed-width window, median merge,
drift-aware merge), each time because a new counter-example appeared after
the implementation existed. The cure is a specification that comes first: a
table of cases whose right answer is fixed by what the metric *means*, not by
what the current code returns.

Any future implementation must satisfy this table. If a case here is wrong,
the argument is about the case, in this file, before any code changes; and a
case may only be relaxed with a written reason. The tolerances are wide on
purpose: the contract pins behaviour, not digits.

Meaning being pinned: a patch is one piece of papyrus. The score is the
fraction of it that the fit placed on a single continuous sheet. Continuity
follows the patch's own grid, so a patch may run along the spiral for any
number of turns, may cross the theta seam, and may have holes, without being
inconsistent. What is inconsistent is a jump between sheets, whatever the
patch's shape.
"""

from __future__ import annotations

import numpy as np
import pytest

from parrhesia.metrics import largest_sheet_fraction, sheet_components

TURN = 1.0  # u is measured in turns by construction


def grid(rows, cols, u_fn, drop=None):
    ri, ci = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    quad_idx = np.stack([ri.ravel(), ci.ravel()], axis=-1)
    u = u_fn(ri.ravel().astype(float), ci.ravel().astype(float))
    if drop is not None:
        keep = ~drop(ri.ravel(), ci.ravel())
        u, quad_idx = u[keep], quad_idx[keep]
    return u, quad_idx


# name, builder, required value, tolerance, why the value is what it is
CONTRACT = [
    (
        "compact patch on one sheet",
        lambda: grid(8, 20, lambda r, c: 11.0 + 0.2 * c / 20),
        1.0, 0.0,
        "nothing to split",
    ),
    (
        "band along the spiral, two turns",
        lambda: grid(6, 200, lambda r, c: 10.0 + 2.0 * c / 200),
        1.0, 0.0,
        "one sheet is one sheet however long it is; real bands run to 26 turns",
    ),
    (
        "band along the spiral, with a hole",
        lambda: grid(6, 200, lambda r, c: 10.0 + 2.0 * c / 200,
                     drop=lambda r, c: (c > 60) & (c < 140)),
        1.0, 0.0,
        "a hole is missing evidence, not a sheet switch",
    ),
    (
        "band drifting along rows instead of columns",
        lambda: grid(200, 6, lambda r, c: 10.0 + 2.0 * r / 200,
                     drop=lambda r, c: (r > 60) & (r < 140)),
        1.0, 0.0,
        "the grid has two directions and neither is privileged",
    ),
    (
        "patch crossing the theta seam",
        lambda: grid(8, 30, lambda r, c: 12.98 + 0.04 * c / 30),
        1.0, 0.0,
        "u is continuous across the seam; spanning ids 12 and 13 there is correct",
    ),
    (
        "half the patch one turn away",
        lambda: grid(8, 20, lambda r, c: np.where(c < 10, 11.2, 12.2)),
        0.5, 0.02,
        "the defining failure: half the evidence on the wrong sheet",
    ),
    (
        "switch in the middle of a drifting band",
        lambda: grid(6, 120, lambda r, c: 10.0 + 1.5 * c / 120 + (c >= 60)),
        0.5, 0.02,
        "drift is not an excuse for a full-turn step",
    ),
    (
        "a quarter of the patch one turn away",
        lambda: grid(8, 20, lambda r, c: np.where(c < 15, 11.2, 12.2)),
        0.75, 0.02,
        "the score is a fraction, so it must follow the size of the misplaced part",
    ),
    (
        "hole, then a switch after it",
        lambda: grid(6, 120, lambda r, c: 10.0 + 2.0 * c / 120 + (c >= 80),
                     drop=lambda r, c: (c > 40) & (c < 80)),
        0.5, 0.06,
        "bridging a hole must not bridge the switch that follows it",
    ),
    (
        "single scored quad",
        lambda: (np.array([11.3]), np.array([[0, 0]])),
        1.0, 0.0,
        "one point cannot be inconsistent with itself",
    ),
    (
        "every quad on the same u",
        lambda: grid(4, 4, lambda r, c: np.full(len(c), 11.5)),
        1.0, 0.0,
        "degenerate but well defined",
    ),
]


@pytest.mark.parametrize("name,build,want,tol,why", CONTRACT,
                         ids=[c[0].replace(" ", "_") for c in CONTRACT])
def test_sheet_consistency_contract(name, build, want, tol, why):
    u, quad_idx = build()
    got = largest_sheet_fraction(sheet_components(u, quad_idx))
    assert abs(got - want) <= tol, f"{name}: got {got:.3f}, contract says {want} ({why})"


def test_contract_is_discriminating():
    """A contract every implementation passes is not a contract. Two rules
    that were shipped and withdrawn must each fail at least one case above,
    so the table demonstrably has teeth."""
    def window_rule(u, quad_idx, turns=0.9):
        s = np.sort(u)
        right = np.searchsorted(s, s + turns, side="right")
        return float((right - np.arange(len(s))).max() / len(s))

    def median_merge_rule(u, quad_idx, max_jump=0.5):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components

        n = len(u)
        rows, cols = quad_idx[:, 0], quad_idx[:, 1]
        g = np.full((rows.max() + 2, cols.max() + 2), -1, dtype=np.int64)
        g[rows, cols] = np.arange(n)
        ea, eb = [], []
        for da, db in ((1, 0), (0, 1)):
            a, b = g[: g.shape[0] - da, : g.shape[1] - db], g[da:, db:]
            ok = (a >= 0) & (b >= 0)
            ia, ib = a[ok], b[ok]
            keep = np.abs(u[ia] - u[ib]) <= max_jump
            ea.append(ia[keep])
            eb.append(ib[keep])
        ea, eb = np.concatenate(ea), np.concatenate(eb)
        _, lab = connected_components(
            coo_matrix((np.ones(len(ea)), (ea, eb)), shape=(n, n)), directed=False
        )
        med = np.array([np.median(u[lab == c]) for c in range(lab.max() + 1)])
        order = np.argsort(med)
        grp = np.empty_like(order)
        k = 0
        for i, c in enumerate(order):
            if i and med[c] - med[order[i - 1]] > max_jump:
                k += 1
            grp[c] = k
        return largest_sheet_fraction(grp[lab])

    for rule_name, rule in (("fixed window", window_rule),
                            ("median merge", median_merge_rule)):
        failures = 0
        for name, build, want, tol, _why in CONTRACT:
            u, quad_idx = build()
            if len(u) < 2:
                continue
            if abs(rule(u, quad_idx) - want) > max(tol, 1e-9):
                failures += 1
        assert failures > 0, f"{rule_name} passes the whole contract: the table is too weak"
