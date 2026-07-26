"""Reproducible held-out split of a verified-patch directory.

The split is deterministic given (directory contents, seed): patches are
ordered by their bbox z-center, grouped into consecutive windows of size
``round(1 / heldout_frac)``, and one seeded pick per window goes to the
held-out side (z-stratification). ``split_manifest.json`` records the seed,
every assignment, and a content hash per patch, so any reported number can be
traced to exact bytes, and a fit input directory can be audited against it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

_HASHED_FILES = ("meta.json", "x.tif", "y.tif", "z.tif", "mask.tif", "winding.tif")


def patch_content_hash(patch_dir: Path) -> str:
    h = hashlib.sha256()
    for name in _HASHED_FILES:
        f = patch_dir / name
        if f.exists():
            h.update(name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _z_center(patch_dir: Path) -> float:
    meta = json.loads((patch_dir / "meta.json").read_text(encoding="utf-8"))
    bbox = meta.get("bbox")
    if bbox and bbox[0][2] != -1.0:
        return (bbox[0][2] + bbox[1][2]) / 2.0  # bbox rows are xyz; z is index 2
    import tifffile

    z = tifffile.imread(patch_dir / "z.tif")
    valid = z != -1.0
    return float(z[valid].mean()) if valid.any() else 0.0


def split_patches(
    src_dir: str | Path,
    out_dir: str | Path,
    heldout_frac: float = 0.2,
    seed: int = 20260731,
) -> dict:
    """Copy patches into ``out_dir/fit`` and ``out_dir/heldout``; write manifest."""
    src_dir, out_dir = Path(src_dir), Path(out_dir)
    patch_dirs = sorted(
        [d for d in src_dir.iterdir() if d.is_dir() and (d / "meta.json").exists()],
        key=lambda d: d.name,
    )
    if len(patch_dirs) < 2:
        raise ValueError(f"{src_dir}: need at least 2 patches, found {len(patch_dirs)}")
    if not 0.0 < heldout_frac < 1.0:
        raise ValueError("heldout_frac must be in (0, 1)")

    order = sorted(range(len(patch_dirs)), key=lambda i: (_z_center(patch_dirs[i]), i))
    window = max(2, round(1.0 / heldout_frac))
    rng = np.random.default_rng(seed)
    heldout_idx: set[int] = set()
    for start in range(0, len(order), window):
        block = order[start : start + window]
        heldout_idx.add(block[int(rng.integers(0, len(block)))])

    assignments, hashes = {}, {}
    for side in ("fit", "heldout"):
        (out_dir / side).mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(patch_dirs):
        side = "heldout" if i in heldout_idx else "fit"
        assignments[d.name] = side
        hashes[d.name] = patch_content_hash(d)
        dest = out_dir / side / d.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(d, dest)

    manifest = {
        "source": str(src_dir),
        "seed": seed,
        "heldout_frac": heldout_frac,
        "n_patches": len(patch_dirs),
        "n_heldout": len(heldout_idx),
        "assignments": assignments,
        "content_sha256": hashes,
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def audit_fit_inputs(manifest_path: str | Path, fit_inputs_dir: str | Path) -> list[str]:
    """Return the held-out patch names present in a fit input directory.

    An empty list means the fit is clean: it saw no held-out patch. Content
    hashes are checked too, so a renamed held-out patch is still caught.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    heldout_hashes = {
        manifest["content_sha256"][name]: name
        for name, side in manifest["assignments"].items()
        if side == "heldout"
    }
    offenders = []
    fit_inputs_dir = Path(fit_inputs_dir)
    for d in sorted(fit_inputs_dir.iterdir()):
        if d.is_dir() and (d / "meta.json").exists():
            h = patch_content_hash(d)
            if h in heldout_hashes:
                offenders.append(f"{d.name} (held-out as {heldout_hashes[h]})")
    return offenders
