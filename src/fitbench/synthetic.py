"""Synthetic scroll fixtures: an ideal archimedean winding family, patch
samplers, and defect injectors.

These are the ground truth for validating every fitbench metric: on the clean
fixture the held-out metrics must be exactly null and the intrinsic checks
silent; after a planted defect the corresponding metric must fire. The scroll
model matches the fit_spiral idealization: windings of an archimedean spiral
(radius = pitch * total_turns), extruded along z, axis at (y, x) = (cy, cx).

Coordinates are (z, y, x) everywhere, like tifxyz.
"""

from __future__ import annotations

import numpy as np

from .io_tifxyz import INVALID, QuadSurface


def _winding_grid(
    winding: int,
    pitch: float,
    z_values: np.ndarray,
    theta_values: np.ndarray,
    center_yx: tuple[float, float],
) -> np.ndarray:
    """Grid (len(z), len(theta), 3) of one winding's surface points."""
    cy, cx = center_yx
    total_theta = winding * 2 * np.pi + theta_values  # absolute angle
    radius = pitch * total_theta / (2 * np.pi)
    y = cy + np.sin(total_theta) * radius
    x = cx + np.cos(total_theta) * radius
    z = np.broadcast_to(z_values[:, None], (len(z_values), len(theta_values)))
    yx = np.broadcast_to(
        np.stack([y, x], axis=-1)[None, :, :], (len(z_values), len(theta_values), 2)
    )
    return np.concatenate([z[..., None], yx], axis=-1).astype(np.float32)


def make_family(
    num_windings: int = 8,
    first_winding: int = 10,
    pitch: float = 10.0,
    z_count: int = 20,
    z_step: float = 4.0,
    theta_count: int = 90,
    center_yx: tuple[float, float] = (0.0, 0.0),
    rng: np.random.Generator | None = None,
    noise: float = 0.0,
) -> dict[int, QuadSurface]:
    """An ideal (optionally noisy) winding family keyed by winding id."""
    z_values = np.arange(z_count, dtype=np.float64) * z_step
    theta_values = np.linspace(0.0, 2 * np.pi, theta_count, endpoint=False)
    family: dict[int, QuadSurface] = {}
    for w in range(first_winding, first_winding + num_windings):
        zyxs = _winding_grid(w, pitch, z_values, theta_values, center_yx)
        if noise > 0.0:
            if rng is None:
                rng = np.random.default_rng(0)
            zyxs = zyxs + rng.normal(0.0, noise, size=zyxs.shape).astype(np.float32)
        family[w] = QuadSurface(zyxs=zyxs, scale=np.array([1.0, 1.0], dtype=np.float32))
    return family


def sample_patch(
    winding: int,
    pitch: float,
    theta_range: tuple[float, float],
    z_range: tuple[float, float],
    rows: int = 8,
    cols: int = 12,
    center_yx: tuple[float, float] = (0.0, 0.0),
    normal_jitter: float = 0.0,
    rng: np.random.Generator | None = None,
) -> QuadSurface:
    """An analytic patch lying exactly on one winding of the ideal scroll.

    ``normal_jitter`` displaces each vertex radially (the surface normal of an
    ideal spiral is close to radial) by N(0, jitter), for realism tests.
    """
    z_values = np.linspace(z_range[0], z_range[1], rows)
    theta_values = np.linspace(theta_range[0], theta_range[1], cols)
    zyxs = _winding_grid(winding, pitch, z_values, theta_values, center_yx).astype(np.float64)
    if normal_jitter > 0.0:
        if rng is None:
            rng = np.random.default_rng(0)
        cy, cx = center_yx
        radial = zyxs[..., 1:] - np.array([cy, cx])
        norm = np.linalg.norm(radial, axis=-1, keepdims=True)
        radial = radial / np.maximum(norm, 1e-9)
        offsets = rng.normal(0.0, normal_jitter, size=zyxs.shape[:2])[..., None]
        zyxs[..., 1:] = zyxs[..., 1:] + radial * offsets
    return QuadSurface(zyxs=zyxs.astype(np.float32), scale=np.array([1.0, 1.0], dtype=np.float32))


def _theta_columns(surface: QuadSurface, theta_band: tuple[float, float]) -> np.ndarray:
    """Column indices whose theta (assumed uniform [0, 2pi)) is in the band."""
    w = surface.zyxs.shape[1]
    theta = np.linspace(0.0, 2 * np.pi, w, endpoint=False)
    t0, t1 = theta_band
    return np.nonzero((theta >= t0) & (theta < t1))[0]


def swap_band(
    family: dict[int, QuadSurface], w1: int, w2: int, theta_band: tuple[float, float]
) -> dict[int, QuadSurface]:
    """Exchange the geometry of two windings within a theta band (sheet swap)."""
    out = {w: QuadSurface(s.zyxs.copy(), s.scale) for w, s in family.items()}
    cols = _theta_columns(family[w1], theta_band)
    a, b = out[w1].zyxs, out[w2].zyxs
    a[:, cols], b[:, cols] = b[:, cols].copy(), a[:, cols].copy()
    return out


def collapse_gap(
    family: dict[int, QuadSurface],
    winding: int,
    theta_band: tuple[float, float],
    factor: float = 0.95,
    center_yx: tuple[float, float] = (0.0, 0.0),
) -> dict[int, QuadSurface]:
    """Pull one winding radially toward its inner neighbor inside a theta band.

    ``factor`` is the fraction of the local gap removed (0.95 leaves 5%).
    """
    if winding - 1 not in family:
        raise ValueError("collapse_gap needs the inner neighbor in the family")
    out = {w: QuadSurface(s.zyxs.copy(), s.scale) for w, s in family.items()}
    cols = _theta_columns(family[winding], theta_band)
    cy, cx = center_yx
    target = out[winding].zyxs
    inner = out[winding - 1].zyxs
    for j in cols:
        yx = target[:, j, 1:]
        yx_inner = inner[:, j, 1:]
        target[:, j, 1:] = yx_inner + (yx - yx_inner) * (1.0 - factor)
    return out


def radial_drift(
    family: dict[int, QuadSurface],
    amplitude: float,
    center_yx: tuple[float, float] = (0.0, 0.0),
) -> dict[int, QuadSurface]:
    """Smooth radial perturbation of all windings: r += amplitude * sin(theta).

    Preserves ordering for small amplitudes (< pitch/2), so monotonicity stays
    silent while held-out distances must grow to ~amplitude in the worst theta.
    """
    out = {}
    cy, cx = center_yx
    for w, s in family.items():
        zyxs = s.zyxs.copy().astype(np.float64)
        yx = zyxs[..., 1:] - np.array([cy, cx])
        r = np.linalg.norm(yx, axis=-1, keepdims=True)
        theta = np.arctan2(yx[..., 0:1], yx[..., 1:2])
        r_new = r + amplitude * np.sin(theta)
        zyxs[..., 1:] = yx / np.maximum(r, 1e-9) * r_new + np.array([cy, cx])
        out[w] = QuadSurface(zyxs.astype(np.float32), s.scale)
    return out


def punch_holes(
    surface: QuadSurface, count: int, size: int, rng: np.random.Generator
) -> QuadSurface:
    """Invalidate ``count`` random (size x size) blocks of vertices."""
    zyxs = surface.zyxs.copy()
    h, w, _ = zyxs.shape
    for _ in range(count):
        i = int(rng.integers(0, max(h - size, 1)))
        j = int(rng.integers(0, max(w - size, 1)))
        zyxs[i : i + size, j : j + size] = INVALID
    return QuadSurface(zyxs, surface.scale)
