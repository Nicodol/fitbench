"""End to end: save a synthetic run + patches to disk, drive the real CLI."""

import json

from fitbench.cli import main
from fitbench.io_tifxyz import save_tifxyz
from fitbench.metrics import score_patches
from fitbench.split import audit_fit_inputs, split_patches
from fitbench.synthetic import make_family, radial_drift, sample_patch

PITCH = 10.0


def save_run(family, run_dir):
    meshes = run_dir / "meshes" / "mesh"
    for wid, s in family.items():
        save_tifxyz(s, meshes / f"w{wid:03d}", uuid=f"w{wid:03d}")
    return meshes


def save_patches(patches, src_dir):
    for pid, p in patches.items():
        save_tifxyz(p, src_dir / pid, uuid=pid)
    return src_dir


def make_all(tmp_path, family):
    run = save_run(family, tmp_path / "run")
    patches = {
        f"p{i}": sample_patch(w, PITCH, (t0, t0 + 1.0), (8.0, 52.0))
        for i, (w, t0) in enumerate([(11, 0.4), (12, 2.0), (13, 4.0), (14, 0.2), (12, 5.0), (13, 1.2)])
    }
    src = save_patches(patches, tmp_path / "all_patches")
    return run, src, patches


def test_split_then_score_end_to_end(tmp_path, capsys):
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)

    # split: deterministic, complete, disjoint
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    manifest = json.loads((tmp_path / "split" / "split_manifest.json").read_text())
    sides = list(manifest["assignments"].values())
    assert sides.count("heldout") == manifest["n_heldout"] >= 2
    assert set(manifest["assignments"]) == {f"p{i}" for i in range(6)}
    manifest2 = split_patches(src, tmp_path / "split2", heldout_frac=0.34)
    assert manifest2["assignments"] == manifest["assignments"]  # same seed, same split

    # audit: the fit/ side is clean, the full source dir is not
    assert audit_fit_inputs(tmp_path / "split" / "split_manifest.json", tmp_path / "split" / "fit") == []
    offenders = audit_fit_inputs(tmp_path / "split" / "split_manifest.json", src)
    assert len(offenders) == manifest["n_heldout"]

    # score the clean family against the held-out side
    out = tmp_path / "report_clean"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(out), "--variant", "plain", "--overlays", "1",
    ])
    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    agg = report["heldout_aggregate"]
    assert agg["frac_within_tau"] == 1.0
    assert agg["min_single_winding_consistency"] == 1.0
    assert report["intrinsic"]["n_violations"] == 0
    assert (out / "report.md").exists()
    assert list(out.glob("overlay_z*.png"))

    # refuse to score when the fit inputs contain held-out patches
    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(tmp_path / "nope"), "--variant", "plain",
        "--manifest", str(tmp_path / "split" / "split_manifest.json"),
        "--fit-inputs", str(src),
    ])
    assert rc == 3


def test_compare_discriminates(tmp_path):
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run_a, src, patches = make_all(tmp_path, family)
    run_b = save_run(radial_drift(family, amplitude=3.0), tmp_path / "run_drift")

    for name, run in [("A", run_a), ("B", run_b)]:
        rc = main([
            "score", "--meshes", str(run), "--patches", str(src),
            "--out", str(tmp_path / f"rep{name}"), "--variant", "plain", "--overlays", "0",
        ])
        assert rc == 0

    rc = main([
        "compare", str(tmp_path / "repA" / "report.json"), str(tmp_path / "repB" / "report.json"),
        "--out", str(tmp_path / "cmp.md"),
    ])
    assert rc == 0
    text = (tmp_path / "cmp.md").read_text()
    assert "dist_p99" in text

    # sanity: the drifted run really is worse on distance
    _, agg_a = score_patches(patches, family)
    _, agg_b = score_patches(patches, radial_drift(family, amplitude=3.0))
    assert agg_b["dist_p99"] > agg_a["dist_p99"] + 1.0


def test_intrinsic_command(tmp_path):
    family = make_family(num_windings=5, first_winding=10, pitch=PITCH)
    run = save_run(family, tmp_path / "run")
    rc = main(["intrinsic", "--meshes", str(run), "--out", str(tmp_path / "rep"), "--variant", "plain"])
    assert rc == 0
    report = json.loads((tmp_path / "rep" / "report.json").read_text())
    assert report["intrinsic"]["n_violations"] == 0
    assert abs(report["intrinsic"]["median_pitch"] - PITCH) < 0.5
