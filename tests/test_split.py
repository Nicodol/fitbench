"""Split protocol: family grouping, stratification, and audit robustness."""

import json

import pytest

from parrhesia.io_tifxyz import save_tifxyz
from parrhesia.split import (
    audit_fit_inputs,
    audit_scored_patches,
    family_key,
    split_patches,
)
from parrhesia.synthetic import sample_patch

PITCH = 10.0


def test_family_key_strips_derived_suffixes():
    assert family_key("auto_grown_20260521_sel_20260521_133956_2") == "auto_grown_20260521"
    assert family_key("auto_grown_20260526_flatboi_sel_20260526_113725_15") == "auto_grown_20260526"
    assert family_key("auto_grown_20260420_region_000") == "auto_grown_20260420"
    assert family_key("fill_0007_sel_20260512_111459_33") == "fill_0007"
    assert family_key("same_wrap000882_growpatch") == "same_wrap000882"
    assert family_key("same_wrap000882_lasagna") == "same_wrap000882"
    assert family_key("some_unrelated_patch") == "some_unrelated_patch"


def save_patch_set(src, specs):
    for name, (w, t0) in specs.items():
        save_tifxyz(
            sample_patch(w, PITCH, (t0, t0 + 1.0), (8.0, 52.0)), src / name, uuid=name
        )
    return src


def test_families_never_straddle_the_split(tmp_path):
    """Overlapping selections of one parent are near-duplicate geometry: the
    whole family must land on one side, for any seed."""
    specs = {
        "auto_grown_1_sel_a_1": (11, 0.4),
        "auto_grown_1_sel_a_2": (11, 0.5),
        "auto_grown_1_sel_b_7": (11, 0.6),
        "auto_grown_2": (12, 1.0),
        "auto_grown_3": (13, 2.0),
        "fill_0001": (14, 3.0),
        "fill_0002": (12, 4.0),
        "same_wrap000009_lasagna": (13, 5.0),
    }
    src = save_patch_set(tmp_path / "src", specs)
    for seed in (1, 7, 20260731):
        manifest = split_patches(src, tmp_path / f"split{seed}", heldout_frac=0.34, seed=seed)
        sides = {
            manifest["assignments"][n]
            for n in specs
            if n.startswith("auto_grown_1_sel_")
        }
        assert len(sides) == 1, f"family split across sides with seed {seed}"
        assert manifest["grouping"] == "family"
        assert manifest["family_of"]["auto_grown_1_sel_a_1"] == "auto_grown_1"
        assert manifest["n_families"] == 6


def test_split_is_z_stratified(tmp_path):
    """With frac 0.25, every consecutive-z window of 4 families holds out
    exactly one (the documented stratification, asserted for once)."""
    specs = {}
    z_of = {}
    for i in range(16):
        name = f"p{i:02d}"
        specs[name] = (11 + (i % 4), 0.3 + 0.1 * i)
        z_of[name] = None
    src = tmp_path / "src"
    for i, (name, (w, t0)) in enumerate(specs.items()):
        z0 = 8.0 + 60.0 * i  # well-separated z bands in family order
        save_tifxyz(
            sample_patch(w, PITCH, (t0, t0 + 1.0), (z0, z0 + 40.0)), src / name, uuid=name
        )
        z_of[name] = z0
    manifest = split_patches(src, tmp_path / "split", heldout_frac=0.25, seed=5)
    by_z = sorted(specs, key=lambda n: z_of[n])
    for start in range(0, 16, 4):
        window = by_z[start : start + 4]
        held = [n for n in window if manifest["assignments"][n] == "heldout"]
        assert len(held) == 1, f"window {window} holds out {held}"


def test_heldout_frac_majority_is_rejected(tmp_path):
    src = save_patch_set(tmp_path / "src", {"a": (11, 0.4), "b": (12, 1.0), "c": (13, 2.0)})
    with pytest.raises(ValueError, match="heldout_frac"):
        split_patches(src, tmp_path / "split", heldout_frac=0.7)


def test_audit_catches_renamed_nested_and_metadata_edited_copies(tmp_path):
    specs = {f"p{i}": (11 + i % 4, 0.3 + 0.5 * i) for i in range(6)}
    src = save_patch_set(tmp_path / "src", specs)
    manifest = split_patches(src, tmp_path / "split", heldout_frac=0.34, seed=2)
    manifest_path = tmp_path / "split" / "split_manifest.json"
    held = [n for n, s in manifest["assignments"].items() if s == "heldout"]

    import shutil

    fit_inputs = tmp_path / "fit_inputs"
    shutil.copytree(tmp_path / "split" / "fit", fit_inputs)
    assert audit_fit_inputs(manifest_path, fit_inputs) == []

    # renamed copy, one level deeper, with meta.json rewritten: still caught,
    # because the audit hashes geometry files only and scans recursively.
    sneaky = fit_inputs / "extra" / "totally_new_name"
    shutil.copytree(tmp_path / "split" / "heldout" / held[0], sneaky)
    meta = json.loads((sneaky / "meta.json").read_text())
    meta["uuid"] = "rewritten"
    (sneaky / "meta.json").write_text(json.dumps(meta))
    offenders = audit_fit_inputs(manifest_path, fit_inputs)
    assert len(offenders) == 1 and held[0] in offenders[0]

    # v1 manifests (no geometry hashes) still catch byte-identical copies.
    v1 = json.loads(manifest_path.read_text())
    del v1["geometry_sha256"]
    v1_path = tmp_path / "v1_manifest.json"
    v1_path.write_text(json.dumps(v1))
    exact = fit_inputs / "exact_copy"
    shutil.rmtree(sneaky)
    shutil.copytree(tmp_path / "split" / "heldout" / held[0], exact)
    offenders = audit_fit_inputs(v1_path, fit_inputs)
    assert len(offenders) == 1 and held[0] in offenders[0]


def test_audit_scored_patches_flags_non_heldout(tmp_path):
    specs = {f"p{i}": (11 + i % 4, 0.3 + 0.5 * i) for i in range(6)}
    src = save_patch_set(tmp_path / "src", specs)
    split_patches(src, tmp_path / "split", heldout_frac=0.34, seed=2)
    manifest_path = tmp_path / "split" / "split_manifest.json"

    unlisted, listed = audit_scored_patches(manifest_path, tmp_path / "split" / "heldout")
    assert unlisted == [] and listed >= 2
    unlisted, listed = audit_scored_patches(manifest_path, tmp_path / "split" / "fit")
    assert len(unlisted) >= 2 and listed == 0


def test_split_determinism_with_families(tmp_path):
    specs = {
        "auto_grown_1_sel_a_1": (11, 0.4),
        "auto_grown_1_sel_a_2": (11, 0.5),
        "auto_grown_2": (12, 1.0),
        "fill_0001": (14, 3.0),
        "fill_0002": (12, 4.0),
        "loose": (13, 5.0),
    }
    src = save_patch_set(tmp_path / "src", specs)
    m1 = split_patches(src, tmp_path / "s1", heldout_frac=0.34)
    m2 = split_patches(src, tmp_path / "s2", heldout_frac=0.34)
    assert m1["assignments"] == m2["assignments"]
    assert m1["geometry_sha256"] == m2["geometry_sha256"]
    # geometry hash must ignore meta.json rewrites
    target = next(iter(specs))
    meta_path = tmp_path / "src" / target / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["uuid"] = "rewritten"
    meta_path.write_text(json.dumps(meta))
    m3 = split_patches(src, tmp_path / "s3", heldout_frac=0.34)
    assert m3["geometry_sha256"][target] == m1["geometry_sha256"][target]
    assert m3["content_sha256"][target] != m1["content_sha256"][target]
