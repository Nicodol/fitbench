"""Geometry tests: analytic cases plus brute-force cross-checks."""

import numpy as np
import pytest

from fitbench.geometry import TriangleSoup, closest_point_on_triangles, surface_distance


def brute_force_distance(points, soup):
    """Reference implementation: exact distance over every triangle."""
    n = len(points)
    best = np.full(n, np.inf)
    best_face = np.full(n, -1, dtype=np.int64)
    for f in range(len(soup.faces)):
        a = np.repeat(soup.a[f : f + 1], n, axis=0)
        b = np.repeat(soup.b[f : f + 1], n, axis=0)
        c = np.repeat(soup.c[f : f + 1], n, axis=0)
        closest = closest_point_on_triangles(points, a, b, c)
        d = np.linalg.norm(closest - points, axis=-1)
        better = d < best
        best[better] = d[better]
        best_face[better] = f
    return best, best_face


@pytest.fixture
def unit_triangle():
    a = np.array([[0.0, 0.0, 0.0]])
    b = np.array([[1.0, 0.0, 0.0]])
    c = np.array([[0.0, 1.0, 0.0]])
    return a, b, c


def test_face_region(unit_triangle):
    a, b, c = unit_triangle
    p = np.array([[0.2, 0.2, 5.0]])  # above the interior
    closest = closest_point_on_triangles(p, a, b, c)
    np.testing.assert_allclose(closest, [[0.2, 0.2, 0.0]], atol=1e-12)


def test_vertex_regions(unit_triangle):
    a, b, c = unit_triangle
    p = np.array([[-1.0, -1.0, 0.0], [3.0, -0.5, 0.0], [-0.5, 3.0, 1.0]])
    closest = closest_point_on_triangles(
        np.asarray(p), np.repeat(a, 3, 0), np.repeat(b, 3, 0), np.repeat(c, 3, 0)
    )
    np.testing.assert_allclose(closest[0], [0, 0, 0], atol=1e-12)
    np.testing.assert_allclose(closest[1], [1, 0, 0], atol=1e-12)
    np.testing.assert_allclose(closest[2], [0, 1, 0], atol=1e-12)


def test_edge_regions(unit_triangle):
    a, b, c = unit_triangle
    p = np.array([[0.5, -2.0, 0.0], [-3.0, 0.5, 0.0], [1.0, 1.0, 0.0]])
    closest = closest_point_on_triangles(
        np.asarray(p), np.repeat(a, 3, 0), np.repeat(b, 3, 0), np.repeat(c, 3, 0)
    )
    np.testing.assert_allclose(closest[0], [0.5, 0.0, 0.0], atol=1e-12)  # edge AB
    np.testing.assert_allclose(closest[1], [0.0, 0.5, 0.0], atol=1e-12)  # edge AC
    np.testing.assert_allclose(closest[2], [0.5, 0.5, 0.0], atol=1e-12)  # edge BC


def wavy_soup(h=12, w=16):
    """A mildly wavy open surface triangulated like a tifxyz grid."""
    i, j = np.meshgrid(np.arange(h, dtype=float), np.arange(w, dtype=float), indexing="ij")
    z = i
    y = j
    x = np.sin(i * 0.7) * 0.8 + np.cos(j * 0.5) * 0.6
    vertices = np.stack([z, y, x], axis=-1).reshape(-1, 3)
    idx = np.arange(h * w).reshape(h, w)
    tl = idx[:-1, :-1].ravel()
    tr = idx[:-1, 1:].ravel()
    bl = idx[1:, :-1].ravel()
    br = idx[1:, 1:].ravel()
    faces = np.concatenate(
        [np.stack([bl, tl, tr], axis=1), np.stack([bl, tr, br], axis=1)], axis=0
    )
    return TriangleSoup(vertices, faces)


def test_surface_distance_matches_brute_force():
    soup = wavy_soup()
    rng = np.random.default_rng(42)
    lo = soup.vertices.min(axis=0) - 2.0
    hi = soup.vertices.max(axis=0) + 2.0
    points = rng.uniform(lo, hi, size=(300, 3))

    result = surface_distance(points, soup, k_seed=4)
    ref_dist, _ = brute_force_distance(points, soup)
    np.testing.assert_allclose(result.dist, ref_dist, atol=1e-9)
    # closest points must be consistent with reported distances
    np.testing.assert_allclose(
        np.linalg.norm(result.closest - points, axis=-1), result.dist, atol=1e-9
    )


def test_kd_candidate_bound_is_required():
    """Adversarial case where the nearest CENTROID is the wrong answer.

    A huge triangle whose surface passes at distance 1 from the query point,
    but whose centroid is ~33 away, hides behind a decoy cluster of tiny
    triangles with centroids at ~5. With k_seed=1 the seed stage picks the
    decoy; only the r_max-bounded radius search can find the true face. This
    is the test that fails if the exactness bound is broken."""
    tris = []
    for k in range(6):
        base = np.array([5.0 + 0.01 * k, 0.0, 0.0])
        tris.append([base, base + [0, 0.1, 0], base + [0, 0, 0.1]])
    tris.append([
        np.array([100.0, -100.0, 1.0]),
        np.array([100.0, 100.0, 1.0]),
        np.array([-100.0, 0.0, 1.0]),
    ])
    vertices = np.concatenate([np.asarray(t) for t in tris])
    faces = np.arange(len(vertices)).reshape(-1, 3)
    soup = TriangleSoup(vertices, faces)

    p = np.array([[0.0, 0.0, 0.0]])
    result = surface_distance(p, soup, k_seed=1)
    ref, _ = brute_force_distance(p, soup)
    np.testing.assert_allclose(result.dist, ref, atol=1e-12)
    assert abs(result.dist[0] - 1.0) < 1e-9


def test_surface_distance_zero_on_surface():
    soup = wavy_soup()
    # Vertices themselves are on the surface: distance must be ~0.
    sample = soup.vertices[:: 7]
    result = surface_distance(sample, soup)
    np.testing.assert_allclose(result.dist, 0.0, atol=1e-9)


def test_offset_plane_distance():
    # A flat grid; points offset by a known amount along x must report it.
    soup = wavy_soup()
    flat_vertices = soup.vertices.copy()
    flat_vertices[:, 2] = 0.0
    flat = TriangleSoup(flat_vertices, soup.faces)
    rng = np.random.default_rng(1)
    base = flat.vertices[rng.integers(0, len(flat.vertices), 50)]
    inside = base[(base[:, 0] > 1) & (base[:, 0] < 10) & (base[:, 1] > 1) & (base[:, 1] < 14)]
    offs = inside.copy()
    offs[:, 2] = 1.7
    result = surface_distance(offs, flat)
    np.testing.assert_allclose(result.dist, 1.7, atol=1e-9)


def test_face_normals_unit():
    soup = wavy_soup()
    n = soup.face_normals()
    np.testing.assert_allclose(np.linalg.norm(n, axis=-1), 1.0, atol=1e-9)
