"""End to end: save a synthetic run + patches to disk, drive the real CLI."""

import json

import pytest

from spiralcheck.cli import main
from spiralcheck.io_tifxyz import save_tifxyz
from spiralcheck.metrics import score_patches
from spiralcheck.split import audit_fit_inputs, split_patches
from spiralcheck.synthetic import make_family, radial_drift, sample_patch

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


def test_score_flags_z_range_tau_umbilicus(tmp_path):
    """The CLI glue for --z-range/--tau/--umbilicus is the path every real
    report went through: exercise it end to end, not only the library."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run = save_run(family, tmp_path / "run")
    patches = {
        "inside": sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0)),
        "outside": sample_patch(12, PITCH, (2.0, 3.0), (400.0, 460.0)),
    }
    src = save_patches(patches, tmp_path / "patches")
    out = tmp_path / "rep"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(src), "--out", str(out),
        "--variant", "plain", "--overlays", "0",
        "--z-range", "8,52", "--tau", "2.0", "--umbilicus", "0,0",
    ])
    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    agg = report["heldout_aggregate"]
    assert agg["z_range"] == [8.0, 52.0]
    assert agg["tau"] == 2.0
    assert agg["n_patches"] == 1 and agg["n_patches_skipped"] == 1
    assert report["meta"]["umbilicus"] == "0,0"
    assert report["meta"]["tau"] == 2.0


def test_score_refuses_non_heldout_patches(tmp_path):
    """Scoring the fit's own inputs under a --manifest is the classic mistake;
    the CLI must refuse (exit 4) unless explicitly overridden."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    manifest = str(tmp_path / "split" / "split_manifest.json")

    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "fit"),
        "--out", str(tmp_path / "rep_bad"), "--variant", "plain", "--overlays", "0",
        "--manifest", manifest,
    ])
    assert rc == 4
    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "fit"),
        "--out", str(tmp_path / "rep_forced"), "--variant", "plain", "--overlays", "0",
        "--manifest", manifest, "--allow-unlisted-patches",
    ])
    assert rc == 0


def test_score_with_fit_inputs_reports_leakage(tmp_path):
    """--fit-inputs drives both the hash audit and the geometric leakage
    measurement; the report must carry the leakage profile and the unseen
    aggregate."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    out = tmp_path / "rep_leak"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(out), "--variant", "plain", "--overlays", "0",
        "--manifest", str(tmp_path / "split" / "split_manifest.json"),
        "--fit-inputs", str(tmp_path / "split" / "fit"),
    ])
    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    agg = report["heldout_aggregate"]
    assert "evidence_leakage" in agg and "unseen" in agg
    assert report["meta"]["fit_inputs_hash_audit"] == "clean"
    assert "Evidence leakage" in (out / "report.md").read_text()


def test_cli_umbilicus_is_plumbed(tmp_path):
    """The CLI must actually pass --umbilicus into the intrinsic checks: an
    off-center family reports a sane pitch only with the true axis."""
    center = (500.0, 700.0)
    family = make_family(
        num_windings=6, first_winding=10, pitch=PITCH, z_count=16, center_yx=center
    )
    run = save_run(family, tmp_path / "run")
    patches = {
        "p0": sample_patch(11, PITCH, (0.4, 1.6), (8.0, 52.0), center_yx=center)
    }
    src = save_patches(patches, tmp_path / "patches")

    out_good = tmp_path / "rep_good"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(src), "--out", str(out_good),
        "--variant", "plain", "--overlays", "0", "--umbilicus", "500,700",
    ])
    assert rc == 0
    rep = json.loads((out_good / "report.json").read_text())
    assert rep["intrinsic"]["n_violations"] == 0
    assert abs(rep["intrinsic"]["median_pitch"] - PITCH) < 0.5

    out_bad = tmp_path / "rep_bad"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(src), "--out", str(out_bad),
        "--variant", "plain", "--overlays", "0",
    ])
    assert rc == 0
    rep = json.loads((out_bad / "report.json").read_text())
    wrong = rep["intrinsic"]
    assert wrong["n_violations"] > 0 or abs(wrong["median_pitch"] - PITCH) > 1.0


def test_cli_unseen_min_dist_is_plumbed(tmp_path):
    """--unseen-min-dist must reach the aggregate, not just the meta echo."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    out = tmp_path / "rep"
    rc = main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(out), "--variant", "plain", "--overlays", "0",
        "--fit-inputs", str(tmp_path / "split" / "fit"),
        "--unseen-min-dist", "0.75",
    ])
    assert rc == 0
    rep = json.loads((out / "report.json").read_text())
    assert rep["heldout_aggregate"]["unseen"]["unseen_min_dist"] == 0.75
    assert rep["meta"]["unseen_min_dist"] == 0.75


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_cli_refuses_non_positive_unseen_min_dist(tmp_path, bad):
    """A non-positive threshold makes every scored point 'unseen', including
    points sitting on a fit input. That would not fail loudly, it would publish
    a leakage-free-looking report, so it has to be refused."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    assert main(["split", "--src", str(src), "--out", str(tmp_path / "split"),
                 "--frac", "0.34"]) == 0
    args = [
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
        "--fit-inputs", str(tmp_path / "split" / "fit"),
        "--unseen-min-dist", bad,
    ]
    with pytest.raises(SystemExit):
        main(args)
    # and the positive case still works, so the guard is not just always-raise
    assert main(args[:-1] + ["0.75"]) == 0


def test_cli_refuses_unloadable_fit_inputs(tmp_path):
    """A fit-input patch that cannot be loaded silently weakens the leakage
    guarantee in the flattering direction: hard refusal unless overridden."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    fit_dir = tmp_path / "split" / "fit"
    victim = next(d for d in sorted(fit_dir.iterdir()) if d.is_dir())
    (victim / "z.tif").write_bytes(b"not a tiff")

    args = [
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
        "--fit-inputs", str(fit_dir),
    ]
    assert main(args) == 5
    rc = main(args + ["--allow-input-load-errors"])
    assert rc == 0
    rep = json.loads((tmp_path / "rep" / "report.json").read_text())
    assert rep["meta"]["fit_inputs_load_errors"] == 1


def test_cli_counts_every_unloadable_input(tmp_path):
    """Two broken inputs must be reported as two, not as one: 'one equals
    many' fixtures are how this class of bug survives."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    fit_dir = tmp_path / "split" / "fit"
    victims = [d for d in sorted(fit_dir.iterdir()) if d.is_dir()][:2]
    assert len(victims) == 2
    for v in victims:
        (v / "z.tif").write_bytes(b"not a tiff")
    args = [
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
        "--fit-inputs", str(fit_dir), "--allow-input-load-errors",
    ]
    assert main(args) == 0
    rep = json.loads((tmp_path / "rep" / "report.json").read_text())
    assert rep["meta"]["fit_inputs_load_errors"] == 2


def test_cli_records_the_real_manifest_counts(tmp_path):
    """The report's audit counts are what a reader uses to tell a legitimate
    z-window restriction from a cherry-pick, so they must be the real ones."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    assert main(["split", "--src", str(src), "--out", str(tmp_path / "split"),
                 "--frac", "0.34"]) == 0
    manifest_path = tmp_path / "split" / "split_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    out = tmp_path / "rep"
    assert main([
        "score", "--meshes", str(run), "--patches", str(tmp_path / "split" / "heldout"),
        "--out", str(out), "--variant", "plain", "--overlays", "0",
        "--manifest", str(manifest_path),
    ]) == 0
    meta = json.loads((out / "report.json").read_text())["meta"]
    assert meta["manifest_n_heldout"] == manifest["n_heldout"] >= 2
    assert meta["patches_dir_listed_in_manifest"] == manifest["n_heldout"]


def test_cli_rejects_a_patches_path_that_is_not_a_directory(tmp_path):
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    rc = main(["split", "--src", str(src), "--out", str(tmp_path / "split"), "--frac", "0.34"])
    assert rc == 0
    with pytest.raises(SystemExit):
        main([
            "score", "--meshes", str(run), "--patches", str(tmp_path / "nope"),
            "--out", str(tmp_path / "rep2"), "--variant", "plain", "--overlays", "0",
            "--manifest", str(tmp_path / "split" / "split_manifest.json"),
        ])


def test_stale_overlays_are_purged_even_without_new_ones(tmp_path):
    """A rescoring of a different window with --overlays 0 must not leave the
    previous window's images beside a report that describes another one."""
    family = make_family(num_windings=6, first_winding=10, pitch=PITCH, z_count=16)
    run, src, _ = make_all(tmp_path, family)
    out = tmp_path / "rep"
    assert main([
        "score", "--meshes", str(run), "--patches", str(src), "--out", str(out),
        "--variant", "plain", "--overlays", "2",
    ]) == 0
    assert list(out.glob("overlay_z*.png"))
    assert main([
        "score", "--meshes", str(run), "--patches", str(src), "--out", str(out),
        "--variant", "plain", "--overlays", "0",
    ]) == 0
    assert not list(out.glob("overlay_z*.png"))


def test_intrinsic_command(tmp_path):
    family = make_family(num_windings=5, first_winding=10, pitch=PITCH)
    run = save_run(family, tmp_path / "run")
    rc = main(["intrinsic", "--meshes", str(run), "--out", str(tmp_path / "rep"), "--variant", "plain"])
    assert rc == 0
    report = json.loads((tmp_path / "rep" / "report.json").read_text())
    assert report["intrinsic"]["n_violations"] == 0
    assert abs(report["intrinsic"]["median_pitch"] - PITCH) < 0.5
