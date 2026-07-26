"""Round-trip tests for the tifxyz reader, on synthetic data only (no download)."""

import json

import numpy as np
import pytest
import tifffile

from fitbench.io_tifxyz import INVALID, load_run_windings, load_tifxyz, split_combined


def write_tifxyz(path, zyxs, scale=(0.05, 0.05), extra_meta=None, mask=None, winding=None):
    path.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path / "x.tif", zyxs[..., 2].astype(np.float32))
    tifffile.imwrite(path / "y.tif", zyxs[..., 1].astype(np.float32))
    tifffile.imwrite(path / "z.tif", zyxs[..., 0].astype(np.float32))
    meta = {"scale": list(scale), "format": "tifxyz", "uuid": path.name}
    if extra_meta:
        meta.update(extra_meta)
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if mask is not None:
        tifffile.imwrite(path / "mask.tif", mask.astype(np.uint8))
    if winding is not None:
        tifffile.imwrite(path / "winding.tif", winding.astype(np.float32))


def grid(h=6, w=8, z0=100.0):
    """A well-behaved synthetic grid with distinct z/y/x values."""
    i, j = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    zyxs = np.stack([z0 + 0 * i, 10.0 + 2.0 * i, 5.0 + 3.0 * j], axis=-1)
    return zyxs.astype(np.float32)


def test_load_roundtrip(tmp_path):
    zyxs = grid()
    zyxs[0, 0] = INVALID  # sentinel-invalid vertex
    write_tifxyz(tmp_path / "p1", zyxs)
    surf = load_tifxyz(tmp_path / "p1")
    assert surf.zyxs.shape == zyxs.shape
    np.testing.assert_allclose(surf.zyxs, zyxs)
    assert not surf.valid_vertex_mask[0, 0]
    assert surf.valid_vertex_mask.sum() == zyxs.shape[0] * zyxs.shape[1] - 1
    # quads adjacent to the invalid corner are invalid, the rest are valid
    assert not surf.valid_quad_mask[0, 0]
    assert surf.valid_quad_mask.sum() == (zyxs.shape[0] - 1) * (zyxs.shape[1] - 1) - 1


def test_mask_forces_invalid(tmp_path):
    zyxs = grid()
    mask = np.ones(zyxs.shape[:2], dtype=np.uint8)
    mask[2, 3] = 0  # real coordinates, but masked out
    write_tifxyz(tmp_path / "p2", zyxs, mask=mask)
    surf = load_tifxyz(tmp_path / "p2")
    assert not surf.valid_vertex_mask[2, 3]
    np.testing.assert_allclose(surf.zyxs[2, 3], [INVALID] * 3)


def test_winding_single_and_grid(tmp_path):
    zyxs = grid()
    write_tifxyz(tmp_path / "w_single", zyxs, winding=np.zeros(zyxs.shape[:2]))
    assert load_tifxyz(tmp_path / "w_single").winding == "single"

    winding = np.full(zyxs.shape[:2], 2.0, dtype=np.float32)
    write_tifxyz(tmp_path / "w_grid", zyxs, winding=winding)
    surf = load_tifxyz(tmp_path / "w_grid")
    assert isinstance(surf.winding, np.ndarray)
    np.testing.assert_allclose(surf.winding, winding)


def test_triangles_match_valid_quads(tmp_path):
    zyxs = grid()
    zyxs[0, 0] = INVALID
    write_tifxyz(tmp_path / "p3", zyxs)
    surf = load_tifxyz(tmp_path / "p3")
    vertices, faces = surf.triangles()
    assert vertices.shape == (zyxs.shape[0] * zyxs.shape[1], 3)
    assert faces.shape[0] == 2 * surf.valid_quad_mask.sum()
    # no face may reference the invalid vertex (flat index 0)
    assert (faces != 0).all()


def test_split_combined(tmp_path):
    h = 5
    blocks = {10: grid(h, 4), 11: grid(h, 3, z0=200.0), 12: grid(h, 6, z0=300.0)}
    combined = np.concatenate(list(blocks.values()), axis=1)
    ranges, cursor = [], 0
    for b in blocks.values():
        ranges.append([cursor, cursor + b.shape[1]])
        cursor += b.shape[1]
    write_tifxyz(
        tmp_path / "combined",
        combined,
        extra_meta={"winding_column_ranges": ranges, "component_winding_ids": list(blocks)},
    )
    parts = split_combined(load_tifxyz(tmp_path / "combined"))
    assert sorted(parts) == [10, 11, 12]
    for wid, block in blocks.items():
        np.testing.assert_allclose(parts[wid].zyxs, block)


def test_load_run_windings_prefers_spliced(tmp_path):
    meshes = tmp_path / "meshes" / "mesh"
    write_tifxyz(meshes / "w010", grid(z0=1.0))
    write_tifxyz(meshes / "w010_spliced", grid(z0=2.0))
    write_tifxyz(meshes / "w011", grid(z0=3.0))

    spliced = load_run_windings(meshes, variant="spliced")
    assert sorted(spliced) == [10, 11]
    assert spliced[10].zyxs[0, 0, 0] == 2.0  # spliced variant preferred
    assert spliced[11].zyxs[0, 0, 0] == 3.0  # plain fallback when no spliced

    plain = load_run_windings(meshes, variant="plain")
    assert plain[10].zyxs[0, 0, 0] == 1.0

    with pytest.raises(FileNotFoundError):
        load_run_windings(tmp_path / "empty_dir_missing")
