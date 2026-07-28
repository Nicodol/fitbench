"""Torch-free reader for the community ``tifxyz`` quad-surface format.

Format reference: villa ``volume-cartographer/scripts/spiral/tifxyz.py``
(``load_tifxyz`` / ``save_tifxyz`` / ``save_combined_tifxyz``). A tifxyz
directory holds:

- ``x.tif``, ``y.tif``, ``z.tif``: float32 grids of scan-space coordinates
- ``meta.json``: at least ``scale`` ([1/step, 1/step]); combined surfaces add
  ``winding_column_ranges`` (half-open column bounds) and
  ``component_winding_ids``
- ``mask.tif`` (optional): 0 marks vertices that carry real coordinates but
  must be treated as invalid
- ``winding.tif`` (optional): per-vertex relative winding values (float32);
  all-zero/NaN means "single winding"

Invalid vertices are the sentinel -1 on all three coordinate grids.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import tifffile

INVALID = -1.0

# wNNN, wNNN_spliced, and the run-tagged forms villa writes when
# FIT_SPIRAL_RUN_TAG is set: wNNN_<tag>, wNNN_spliced_<tag>.
_WINDING_DIR_RE = re.compile(r"^w(\d+)(_spliced)?(?:_.+)?$")


@dataclass
class QuadSurface:
    """A tifxyz grid of scan-space points with validity semantics.

    ``zyxs`` has shape (H, W, 3) in (z, y, x) order, float32, with -1 on all
    three components marking invalid vertices (matching villa's convention).
    """

    zyxs: np.ndarray
    scale: np.ndarray
    path: Path | None = None
    uuid: str | None = None
    winding: np.ndarray | str | None = None  # float32 grid, or "single", or None
    winding_column_ranges: list[list[int]] | None = None
    component_winding_ids: list[int] | None = None
    _valid_vertex_mask: np.ndarray | None = field(default=None, repr=False)

    @property
    def valid_vertex_mask(self) -> np.ndarray:
        if self._valid_vertex_mask is None:
            self._valid_vertex_mask = np.any(self.zyxs != INVALID, axis=-1)
        return self._valid_vertex_mask

    @property
    def valid_quad_mask(self) -> np.ndarray:
        v = self.valid_vertex_mask
        return v[:-1, :-1] & v[1:, :-1] & v[:-1, 1:] & v[1:, 1:]

    @property
    def valid_zyxs(self) -> np.ndarray:
        return self.zyxs[self.valid_vertex_mask]

    def quad_centers(self) -> tuple[np.ndarray, np.ndarray]:
        """Centers of valid quads: returns (centers (N, 3), quad index (N, 2))."""
        z = self.zyxs
        centers = (z[:-1, :-1] + z[1:, :-1] + z[:-1, 1:] + z[1:, 1:]) / 4.0
        mask = self.valid_quad_mask
        return centers[mask], np.stack(np.nonzero(mask), axis=-1)

    def triangles(self) -> tuple[np.ndarray, np.ndarray]:
        """Triangulated valid quads: (vertices (H*W, 3), faces (M, 3) int64).

        Triangulation matches villa's ``Patch._get_face_indices``: each quad
        (i, j) yields (bl, tl, tr) and (bl, tr, br).
        """
        h, w, _ = self.zyxs.shape
        idx = np.arange(h * w).reshape(h, w)
        tl = idx[:-1, :-1].ravel()
        tr = idx[:-1, 1:].ravel()
        bl = idx[1:, :-1].ravel()
        br = idx[1:, 1:].ravel()
        quad_ok = self.valid_quad_mask.ravel()
        faces = np.concatenate(
            [
                np.stack([bl, tl, tr], axis=1)[quad_ok],
                np.stack([bl, tr, br], axis=1)[quad_ok],
            ],
            axis=0,
        )
        return self.zyxs.reshape(-1, 3), faces


def load_tifxyz(path: str | Path) -> QuadSurface:
    """Load one tifxyz directory, mirroring villa's ``load_tifxyz`` semantics."""
    path = Path(path)
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    scale = np.asarray(meta["scale"], dtype=np.float32)

    grids = [tifffile.imread(path / f"{coord}.tif") for coord in "zyx"]
    zyxs = np.stack(grids, axis=-1).astype(np.float32, copy=False)

    mask_path = path / "mask.tif"
    if mask_path.exists():
        mask = tifffile.imread(mask_path)
        if mask.ndim == 3:
            mask = mask[..., 0]
        zyxs = zyxs.copy()
        zyxs[mask == 0] = INVALID

    winding: np.ndarray | str | None = None
    winding_path = path / "winding.tif"
    if winding_path.exists():
        wt = tifffile.imread(winding_path).astype(np.float32, copy=False)
        if wt.shape[:2] != zyxs.shape[:2] or wt.ndim != 2:
            raise ValueError(f"winding.tif shape {wt.shape} does not match grid {zyxs.shape[:2]}")
        winding = "single" if bool(np.all(np.isnan(wt) | (wt == 0.0))) else wt

    surface = QuadSurface(
        zyxs=zyxs,
        scale=scale,
        path=path,
        uuid=meta.get("uuid"),
        winding=winding,
        winding_column_ranges=meta.get("winding_column_ranges"),
        component_winding_ids=meta.get("component_winding_ids"),
    )
    if not surface.valid_quad_mask.any():
        raise ValueError(f"{path}: no valid quad in surface")
    return surface


def face_boundary_mask(surface: QuadSurface) -> np.ndarray:
    """Per-face flag aligned with ``triangles()``: does the face belong to a
    boundary quad (a valid quad with at least one invalid or out-of-bounds
    4-neighbor)? Useful to decide whether a closest point lies in a surface's
    interior or merely on its rim."""
    valid = surface.valid_quad_mask
    padded = np.pad(valid, 1, constant_values=False)
    all_neighbors = (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    boundary = valid & ~all_neighbors
    per_quad = boundary.ravel()[valid.ravel().nonzero()[0]]
    return np.concatenate([per_quad, per_quad])


def save_tifxyz(surface: QuadSurface, path: str | Path, uuid: str | None = None) -> Path:
    """Write a QuadSurface as a tifxyz directory (x/y/z.tif + meta.json).

    Mirrors villa's ``save_tifxyz`` metadata (scale, bbox, format, uuid) and
    writes ``winding.tif`` when the surface carries a winding grid.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    zyxs = surface.zyxs
    tifffile.imwrite(path / "x.tif", zyxs[..., 2].astype(np.float32))
    tifffile.imwrite(path / "y.tif", zyxs[..., 1].astype(np.float32))
    tifffile.imwrite(path / "z.tif", zyxs[..., 0].astype(np.float32))
    valid = surface.valid_vertex_mask
    bbox = (
        [surface.valid_zyxs.min(axis=0)[::-1].tolist(), surface.valid_zyxs.max(axis=0)[::-1].tolist()]
        if valid.any()
        else [[-1.0] * 3, [-1.0] * 3]
    )
    meta = {
        "scale": np.asarray(surface.scale, dtype=float).tolist(),
        "bbox": bbox,
        "format": "tifxyz",
        "type": "seg",
        "uuid": uuid or surface.uuid or path.name,
    }
    if surface.winding_column_ranges is not None:
        meta["winding_column_ranges"] = surface.winding_column_ranges
        meta["component_winding_ids"] = surface.component_winding_ids
    (path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if isinstance(surface.winding, np.ndarray):
        tifffile.imwrite(path / "winding.tif", surface.winding.astype(np.float32))
    return path


def split_combined(surface: QuadSurface) -> dict[int, QuadSurface]:
    """Split a combined QuadSurface into per-winding surfaces.

    Uses ``winding_column_ranges`` + ``component_winding_ids`` written by
    villa's ``save_combined_tifxyz``. Column ranges are half-open.
    """
    if not surface.winding_column_ranges or not surface.component_winding_ids:
        raise ValueError("surface has no winding_column_ranges metadata")
    if len(surface.winding_column_ranges) != len(surface.component_winding_ids):
        raise ValueError("winding_column_ranges and component_winding_ids length mismatch")
    out: dict[int, QuadSurface] = {}
    for winding_id, (j0, j1) in zip(
        surface.component_winding_ids, surface.winding_column_ranges, strict=True
    ):
        block = surface.zyxs[:, j0:j1]
        out[int(winding_id)] = QuadSurface(zyxs=block, scale=surface.scale, path=surface.path)
    return out


def load_run_windings(
    meshes_dir: str | Path, variant: str = "spliced"
) -> dict[int, QuadSurface]:
    """Load a fit run's winding surfaces from a ``meshes/mesh``-style directory.

    ``variant`` is ``"spliced"`` (prefer ``wNNN_spliced``), ``"plain"`` (only
    ``wNNN``), or ``"any"``. Also accepts a directory containing one combined
    QuadSurface (detected via its metadata).
    """
    if variant not in ("spliced", "plain", "any"):
        raise ValueError(f"unknown variant {variant!r}")
    meshes_dir = Path(meshes_dir)
    if not meshes_dir.is_dir():
        raise FileNotFoundError(meshes_dir)

    candidates: dict[int, dict[bool, Path]] = {}
    combined: list[Path] = []
    for child in sorted(meshes_dir.iterdir()):
        if not child.is_dir() or not (child / "meta.json").exists():
            continue
        m = _WINDING_DIR_RE.match(child.name)
        if m:
            wid = int(m.group(1))
            candidates.setdefault(wid, {})[bool(m.group(2))] = child
        else:
            meta = json.loads((child / "meta.json").read_text(encoding="utf-8"))
            if meta.get("winding_column_ranges"):
                combined.append(child)

    if candidates:
        out: dict[int, QuadSurface] = {}
        for wid, by_spliced in sorted(candidates.items()):
            if variant == "spliced":
                path = by_spliced.get(True) or by_spliced.get(False)
            elif variant == "plain":
                path = by_spliced.get(False)
            else:
                path = by_spliced.get(True) or by_spliced.get(False)
            if path is not None:
                out[wid] = load_tifxyz(path)
        if out:
            return out
    if combined:
        if len(combined) > 1:
            raise ValueError(f"multiple combined surfaces in {meshes_dir}: {combined}")
        return split_combined(load_tifxyz(combined[0]))
    raise FileNotFoundError(f"no wNNN/wNNN_spliced directories or combined surface in {meshes_dir}")
