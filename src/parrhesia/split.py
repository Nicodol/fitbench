"""Reproducible held-out split of a verified-patch directory.

The split is deterministic given (directory contents, seed). Patches are first
grouped into *families*: overlapping selections of one parent patch (villa's
``*_sel_*`` exports, ``_region_NNN`` crops, ``_flatboi`` variants, and the
``same_wrapNNNNNN_*`` producers) are near-duplicate geometry, so letting them
straddle the split boundary would leak held-out geometry into the fit side
under a different directory name. Families are ordered by z-center, grouped
into consecutive windows of size ``round(1 / heldout_frac)``, and one seeded
pick per window sends the whole family to the held-out side (z-stratified).

``split_manifest.json`` records the seed, every assignment, the family
grouping, and two content hashes per patch: ``content_sha256`` over all files
and ``geometry_sha256`` over the geometry files only (no ``meta.json``, whose
free-text fields can be rewritten without changing any geometry). Audits match
on the geometry hash, so a renamed copy or a metadata-edited copy of a
held-out patch is still caught.

Name-level splits cannot see geometric overlap between *different* patches;
the complementary guarantee is the evidence-leakage measurement in
``metrics.score_patches`` (distance of every scored point to the fit's actual
input surfaces), which holds whatever the split did.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np

_HASHED_FILES = ("meta.json", "x.tif", "y.tif", "z.tif", "mask.tif", "winding.tif")
_GEOMETRY_FILES = ("x.tif", "y.tif", "z.tif", "mask.tif", "winding.tif")

# Family key: strip the suffixes villa's tooling appends to derived exports of
# the same parent patch, repeatedly until stable (suffixes stack in any
# order: a_flatboi_region_2, a_region_2_flatboi). Unknown naming schemes fall
# through unchanged (each patch is then its own family). Name-level grouping
# is a heuristic; the geometry-hash merge in ``split_patches`` is the
# guarantee for byte-identical twins the names miss.
_FAMILY_CUTS = (
    re.compile(r"_sel_.*$"),
    re.compile(r"_region_\d+$"),
    re.compile(r"_v\d+(\.tifxyz)?$"),
    re.compile(r"_(flatboi|copy|front|back|new|lasagna|growpatch)$"),
)


def family_key(name: str) -> str:
    """Strip derived-export suffixes until the name stops changing.

    A name made only of suffixes would reduce to the empty string, which
    would put every such patch in one bogus family; those keep the last
    non-empty form instead. Real corpora contain no such name (checked on
    all 4,922 PHerc. Paris 4 patches), so this is a guard, not a policy.
    """
    while True:
        before = name
        for rx in _FAMILY_CUTS:
            stripped = rx.sub("", name)
            if stripped:  # never let a cut empty the name
                name = stripped
        if name == before:
            return name


def _hash_files(patch_dir: Path, names: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for name in names:
        f = patch_dir / name
        if f.exists():
            h.update(name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def patch_content_hash(patch_dir: Path) -> str:
    return _hash_files(patch_dir, _HASHED_FILES)


def patch_geometry_hash(patch_dir: Path) -> str:
    return _hash_files(patch_dir, _GEOMETRY_FILES)


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
    if not 0.0 < heldout_frac <= 0.5:
        raise ValueError(
            f"heldout_frac must be in (0, 0.5], got {heldout_frac} "
            "(the windowed stratification cannot hold out a majority)"
        )

    content_hashes = {d.name: patch_content_hash(d) for d in patch_dirs}
    geometry_hashes = {d.name: patch_geometry_hash(d) for d in patch_dirs}

    # Name-level families first, then merge families that share a geometry
    # hash: byte-identical twins under unrelated names must never straddle the
    # split (they would poison the fit side and deadlock the audit).
    key_of = {d.name: family_key(d.name) for d in patch_dirs}
    merged_key: dict[str, str] = {}

    def resolve(k: str) -> str:
        while merged_key.get(k, k) != k:
            k = merged_key[k]
        return k

    by_geometry: dict[str, str] = {}
    for d in patch_dirs:
        k = resolve(key_of[d.name])
        h = geometry_hashes[d.name]
        other = by_geometry.get(h)
        if other is None:
            by_geometry[h] = k
        else:
            other = resolve(other)
            if other != k:
                merged_key[k] = other
    families: dict[str, list[int]] = {}
    for i, d in enumerate(patch_dirs):
        families.setdefault(resolve(key_of[d.name]), []).append(i)

    fam_keys = list(families)
    z_centers = [_z_center(d) for d in patch_dirs]
    fam_z = {k: float(np.mean([z_centers[i] for i in families[k]])) for k in fam_keys}

    order = sorted(range(len(fam_keys)), key=lambda i: (fam_z[fam_keys[i]], fam_keys[i]))
    # Cut the z-ordered families into as many near-equal blocks as there are
    # families to hold out, and draw one family per block. Fixed-width blocks
    # leave a short tail whose single family is held out at every seed and
    # whose z extreme is over-represented; equal blocks hit the requested
    # family fraction by construction, at every corpus size.
    n_blocks = max(1, round(len(order) * heldout_frac))
    bounds = np.linspace(0, len(order), n_blocks + 1).round().astype(int)
    blocks = [order[bounds[i] : bounds[i + 1]] for i in range(n_blocks)]
    rng = np.random.default_rng(seed)
    heldout_idx: set[int] = set()
    for block in blocks:
        picked = fam_keys[block[int(rng.integers(0, len(block)))]]
        heldout_idx.update(families[picked])

    # Self-check BEFORE anything is written: the guarantee the manifest sells
    # is that no held-out geometry exists on the fit side. The hash merge
    # above makes this unreachable by construction, which is the point: it is
    # a tripwire on that construction, not a recoverable case. Running it
    # first means a failure leaves no split on disk at all.
    heldout_geo = {geometry_hashes[d.name] for i, d in enumerate(patch_dirs) if i in heldout_idx}
    fit_geo = {geometry_hashes[d.name] for i, d in enumerate(patch_dirs) if i not in heldout_idx}
    poisoned = heldout_geo & fit_geo
    if poisoned:
        raise RuntimeError(
            f"split self-check failed: {len(poisoned)} geometry hash(es) present "
            "on both sides; family grouping missed a duplicate"
        )

    assignments, family_of = {}, {}
    for side in ("fit", "heldout"):
        (out_dir / side).mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(patch_dirs):
        side = "heldout" if i in heldout_idx else "fit"
        assignments[d.name] = side
        key = resolve(key_of[d.name])
        if key != d.name:
            family_of[d.name] = key
        dest = out_dir / side / d.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(d, dest)

    manifest = {
        "source": str(src_dir),
        "seed": seed,
        # heldout_frac is a target on FAMILIES; families differ in size, so
        # the patch-level fraction that comes out is close but not equal.
        "heldout_frac": heldout_frac,
        "heldout_family_frac": len(blocks) / len(fam_keys),
        "grouping": "family",
        "n_patches": len(patch_dirs),
        "n_families": len(fam_keys),
        "n_heldout": len(heldout_idx),
        "assignments": assignments,
        "family_of": family_of,
        "content_sha256": content_hashes,
        "geometry_sha256": geometry_hashes,
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _heldout_hash_index(manifest: dict) -> dict[str, str]:
    """hash -> held-out patch name, preferring geometry hashes (v2 manifests)
    and falling back to full-content hashes (v1)."""
    key = "geometry_sha256" if "geometry_sha256" in manifest else "content_sha256"
    return {
        manifest[key][name]: name
        for name, side in manifest["assignments"].items()
        if side == "heldout"
    }


def _iter_patch_dirs(root: Path):
    """Every directory under ``root`` (recursively) that looks like a tifxyz
    patch. Non-recursive scans miss nested layouts."""
    seen = set()
    for meta in sorted(root.rglob("meta.json")):
        d = meta.parent
        if d not in seen:
            seen.add(d)
            yield d


def audit_fit_inputs(manifest_path: str | Path, fit_inputs_dir: str | Path) -> list[str]:
    """Return the held-out patch names present in a fit input directory.

    An empty list means the fit is clean: it saw no held-out patch (matched by
    geometry hash, recursively, so a renamed, nested, or metadata-edited copy
    is still caught; a copy with modified geometry bytes is out of scope here
    and is what the evidence-leakage measurement exists for).
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    heldout = _heldout_hash_index(manifest)
    use_geometry = "geometry_sha256" in manifest
    offenders = []
    for d in _iter_patch_dirs(Path(fit_inputs_dir)):
        h = patch_geometry_hash(d) if use_geometry else patch_content_hash(d)
        if h in heldout:
            offenders.append(f"{d.name} (held-out as {heldout[h]})")
    return offenders


def audit_scored_patches(
    manifest_path: str | Path, patches_dir: str | Path
) -> tuple[list[str], int, int]:
    """Check that the patches about to be scored are the manifest's held-out
    side. Returns (unlisted patch names, number of listed patches, total
    held-out patches in the manifest). Scoring the fit's own inputs under a
    held-out label is the mistake this catches. The scan is flat (immediate
    children), matching exactly what the scorer will load; nested directories
    the scorer would never read must not influence this audit.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    heldout = _heldout_hash_index(manifest)
    use_geometry = "geometry_sha256" in manifest
    unlisted, listed = [], 0
    root = Path(patches_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"--patches is not a directory: {root}")
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "meta.json").exists():
            continue
        h = patch_geometry_hash(d) if use_geometry else patch_content_hash(d)
        if h in heldout:
            listed += 1
        else:
            unlisted.append(d.name)
    return unlisted, listed, len(heldout)
