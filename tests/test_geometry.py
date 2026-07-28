"""Geometry tests: analytic cases plus brute-force cross-checks."""

import numpy as np
import pytest

from parrhesia.geometry import TriangleSoup, closest_point_on_triangles, surface_distance


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


def _sampled_reference(points, a, b, c, n=80):
    """Independent reference: dense barycentric sampling of each triangle.

    Never calls the production primitive. The sampled minimum overestimates the
    true distance by at most the sampling resolution (cell diameter <=
    max_edge / n), giving a two-sided bracket for the exact result.
    """
    s = np.linspace(0.0, 1.0, n)
    u, v = np.meshgrid(s, s)
    keep = (u + v) <= 1.0
    u, v = u[keep], v[keep]
    out = np.empty(len(points))
    for i in range(len(points)):
        samples = a[i] + u[:, None] * (b[i] - a[i]) + v[:, None] * (c[i] - a[i])
        out[i] = np.linalg.norm(samples - points[i], axis=-1).min()
    return out


def test_primitive_against_independent_sampling():
    """The Voronoi-region primitive vs a reference that shares no code with it:
    exact <= sampled <= exact + resolution, on random triangles."""
    rng = np.random.default_rng(7)
    n = 40
    a = rng.normal(0, 3, (n, 3))
    b = a + rng.normal(0, 2, (n, 3))
    c = a + rng.normal(0, 2, (n, 3))
    p = rng.normal(0, 4, (n, 3))
    closest = closest_point_on_triangles(p, a, b, c)
    exact = np.linalg.norm(closest - p, axis=-1)
    sampled = _sampled_reference(p, a, b, c, n=80)
    max_edge = np.max(
        [np.linalg.norm(b - a, axis=-1), np.linalg.norm(c - a, axis=-1),
         np.linalg.norm(c - b, axis=-1)],
        axis=0,
    )
    resolution = max_edge / 80 + 1e-9
    assert (sampled >= exact - 1e-9).all()  # exact can never beat the true minimum
    assert (sampled - exact <= resolution).all()  # and must be within sampling reach


def test_degenerate_and_needle_triangles():
    """Needle, collinear, and point-collapsed triangles must still give the
    analytically correct distance (this is where oversized epsilon guards or
    sloppy region logic break)."""
    # Thin but valid right triangle with 0.01 edges; point above its interior.
    a = np.array([[0.0, 0.0, 0.0]])
    b = np.array([[0.01, 0.0, 0.0]])
    c = np.array([[0.0, 0.01, 0.0]])
    p = np.array([[0.002, 0.002, 1.0]])
    closest = closest_point_on_triangles(p, a, b, c)
    np.testing.assert_allclose(
        np.linalg.norm(closest - p, axis=-1), [1.0], rtol=0, atol=1e-9
    )

    # Collinear needle: the triangle degenerates to the segment a-c.
    a = np.array([[0.0, 0.0, 0.0]])
    b = np.array([[1e-9, 0.0, 0.0]])
    c = np.array([[2.0, 0.0, 0.0]])
    p = np.array([[1.0, 1.0, 0.0]])
    closest = closest_point_on_triangles(p, a, b, c)
    np.testing.assert_allclose(
        np.linalg.norm(closest - p, axis=-1), [1.0], rtol=0, atol=1e-9
    )

    # Fully collapsed to a point.
    a = b = c = np.array([[1.0, 2.0, 3.0]])
    p = np.array([[1.0, 2.0, 5.0]])
    closest = closest_point_on_triangles(p, a, b, c)
    np.testing.assert_allclose(
        np.linalg.norm(closest - p, axis=-1), [2.0], rtol=0, atol=1e-9
    )


def test_chunked_query_matches_single_shot():
    """The chunked path of surface_distance is the one large real runs take;
    it must be bit-identical to the one-shot path."""
    rng = np.random.default_rng(11)
    verts = rng.normal(0, 5, (60, 3))
    faces = rng.integers(0, 60, (40, 3))
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    soup = TriangleSoup(verts, faces[ok])
    points = rng.normal(0, 6, (211, 3))
    one = surface_distance(points, soup)
    chunked = surface_distance(points, soup, chunk=17)
    np.testing.assert_array_equal(one.dist, chunked.dist)
    np.testing.assert_array_equal(one.face_idx, chunked.face_idx)
    np.testing.assert_array_equal(one.closest, chunked.closest)
