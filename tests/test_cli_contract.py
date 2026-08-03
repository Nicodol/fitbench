"""The CLI contract a stranger meets first: predictable mistakes get one
explanatory line and exit 2 (never a traceback), options are validated before
any heavy loading, dangerous defaults warn, and compare refuses to bless two
files that share nothing."""

import json

import pytest

from spiralcheck.cli import main
from spiralcheck.io_tifxyz import save_tifxyz
from spiralcheck.synthetic import make_family, sample_patch

PITCH = 10.0


def _exit_code(argv) -> int:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    return excinfo.value.code


def _tiny_run(tmp_path, spliced: bool):
    family = make_family(num_windings=4, first_winding=10, pitch=PITCH, z_count=12)
    meshes = tmp_path / "run"
    for wid, s in family.items():
        suffix = "_spliced" if spliced else ""
        save_tifxyz(s, meshes / f"w{wid:03d}{suffix}", uuid=f"w{wid:03d}")
    patches = tmp_path / "patches"
    save_tifxyz(sample_patch(11, PITCH, (0.4, 1.6), (8.0, 40.0)), patches / "p0", uuid="p0")
    return meshes, patches


def test_score_bad_path_is_one_line_exit_2(tmp_path, capsys):
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err and "nope" in err
    assert "Traceback" not in err


def test_score_validates_options_before_loading_anything(tmp_path, capsys):
    # The meshes path is also broken, but the z-range typo must be reported
    # first: errors are discovered per invocation, not one load at a time.
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--z-range", "banana",
    ])
    assert code == 2
    assert "--z-range" in capsys.readouterr().err


@pytest.mark.parametrize("spec", ["banana", "1,2,3"])
def test_score_rejects_umbilicus_gibberish_early(tmp_path, spec, capsys):
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--umbilicus", spec,
    ])
    assert code == 2
    assert "umbilicus" in capsys.readouterr().err


def test_score_rejects_invalid_umbilicus_json_file(tmp_path, capsys):
    bad = tmp_path / "umb.json"
    bad.write_text("{not json", encoding="utf-8")
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--umbilicus", str(bad),
    ])
    assert code == 2
    assert "JSON" in capsys.readouterr().err


def test_split_bad_src_is_one_line_exit_2(tmp_path, capsys):
    code = _exit_code([
        "split", "--src", str(tmp_path / "nope"), "--out", str(tmp_path / "out"),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
    assert "Traceback" not in err


@pytest.mark.parametrize("frac", ["0", "1", "1.5", "-0.2"])
def test_split_rejects_out_of_range_frac(tmp_path, frac, capsys):
    src = tmp_path / "src"
    src.mkdir()
    code = _exit_code(["split", "--src", str(src), "--out", str(tmp_path / "o"),
                       "--frac", frac])
    assert code == 2
    assert "--frac" in capsys.readouterr().err


def test_compare_refuses_files_with_no_common_metric(tmp_path, capsys):
    # Sam's reproduction: feeding compare a split manifest used to produce an
    # empty delta table with a success message.
    not_a_report = tmp_path / "manifest.json"
    not_a_report.write_text(json.dumps({"assignments": {"a": "fit"}}), encoding="utf-8")
    code = _exit_code([
        "compare", str(not_a_report), str(not_a_report), "--out", str(tmp_path / "cmp.md"),
    ])
    assert code == 2
    assert "no numeric report metric" in capsys.readouterr().err


def test_compare_records_provenance_and_sorts_windings_numerically(tmp_path):
    def fake_report(path, offset: float):
        payload = {
            "meta": {},
            "heldout_aggregate": {"dist_p50": 1.0 + offset},
            "intrinsic": {
                "validity_per_winding": {str(k): 0.5 + offset for k in (2, 10, 11, 100)}
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    fake_report(a, 0.0)
    fake_report(b, 0.25)
    out = tmp_path / "cmp.md"
    assert main(["compare", str(a), str(b), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert f"- A: {a}" in text and f"- B: {b}" in text
    positions = [text.index(f"validity_per_winding.{k} ") for k in (2, 10, 11, 100)]
    assert positions == sorted(positions)


def test_spliced_variant_without_fit_inputs_warns(tmp_path, capsys):
    meshes, patches = _tiny_run(tmp_path, spliced=True)
    assert main([
        "score", "--meshes", str(meshes), "--patches", str(patches),
        "--out", str(tmp_path / "rep"), "--overlays", "0",
    ]) == 0
    assert "_spliced" in capsys.readouterr().err


def test_plain_variant_does_not_warn(tmp_path, capsys):
    meshes, patches = _tiny_run(tmp_path, spliced=False)
    assert main([
        "score", "--meshes", str(meshes), "--patches", str(patches),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
    ]) == 0
    assert "_spliced" not in capsys.readouterr().err


def test_spliced_with_fit_inputs_does_not_warn(tmp_path, capsys):
    meshes, patches = _tiny_run(tmp_path, spliced=True)
    assert main([
        "score", "--meshes", str(meshes), "--patches", str(patches),
        "--out", str(tmp_path / "rep"), "--overlays", "0",
        "--fit-inputs", str(patches),
    ]) == 0
    assert "_spliced" not in capsys.readouterr().err


# The next block answers the 2026-08-03 pre-push adversarial review: every
# case below used to reach the user as a raw traceback (or, for NaN, as a
# poisoned exit-0 report), despite the "one line, exit 2" contract.

@pytest.mark.parametrize("flag, value", [("--tau", "nan"), ("--unseen-min-dist", "nan")])
def test_score_refuses_nan_thresholds(tmp_path, flag, value, capsys):
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), flag, value,
    ])
    assert code == 2
    assert flag in capsys.readouterr().err


def test_score_refuses_nan_z_range(tmp_path, capsys):
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--z-range", "nan,nan",
    ])
    assert code == 2
    assert "--z-range" in capsys.readouterr().err


def test_score_disjoint_z_range_is_one_line_exit_2(tmp_path, capsys):
    meshes, patches = _tiny_run(tmp_path, spliced=False)
    code = _exit_code([
        "score", "--meshes", str(meshes), "--patches", str(patches),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
        "--z-range", "100000,100001",
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "no patch had a scorable point" in err
    assert "Traceback" not in err


def test_score_rejects_umbilicus_directory(tmp_path, capsys):
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--umbilicus", str(tmp_path),
    ])
    assert code == 2
    assert "directory" in capsys.readouterr().err


@pytest.mark.parametrize("payload", ['{"foo": 1}', '"hello"', "[[1, 2], [3]]"])
def test_score_rejects_wrong_shaped_umbilicus_json_early(tmp_path, payload, capsys):
    bad = tmp_path / "umb.json"
    bad.write_text(payload, encoding="utf-8")
    code = _exit_code([
        "score", "--meshes", str(tmp_path / "nope"), "--patches", str(tmp_path / "x"),
        "--out", str(tmp_path / "y"), "--umbilicus", str(bad),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "umbilicus" in err
    assert "Traceback" not in err


def test_score_rejects_json_that_is_not_a_manifest(tmp_path, capsys):
    meshes, patches = _tiny_run(tmp_path, spliced=False)
    not_manifest = tmp_path / "manifest.json"
    not_manifest.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    code = _exit_code([
        "score", "--meshes", str(meshes), "--patches", str(patches),
        "--out", str(tmp_path / "rep"), "--variant", "plain", "--overlays", "0",
        "--manifest", str(not_manifest),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "split" in err and "manifest" in err
    assert "Traceback" not in err


@pytest.mark.parametrize("payload", ["null", "[1, 2]"])
def test_compare_rejects_non_object_roots(tmp_path, payload, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(payload, encoding="utf-8")
    code = _exit_code(["compare", str(bad), str(bad), "--out", str(tmp_path / "c.md")])
    err = capsys.readouterr().err
    assert code == 2
    assert "not a spiralcheck report.json" in err


def test_demo_rejects_out_path_that_is_a_file(tmp_path, capsys):
    block = tmp_path / "blockfile"
    block.write_text("x", encoding="utf-8")
    code = _exit_code(["demo", "--out", str(block)])
    assert code == 2
    assert "--out" in capsys.readouterr().err


def test_intrinsic_bad_meshes_is_one_line_exit_2(tmp_path, capsys):
    code = _exit_code([
        "intrinsic", "--meshes", str(tmp_path / "nope"), "--out", str(tmp_path / "y"),
    ])
    err = capsys.readouterr().err
    assert code == 2
    assert "Traceback" not in err


def test_help_shows_defaults_and_exit_codes(capsys):
    assert _exit_code(["score", "--help"]) == 0
    out = capsys.readouterr().out
    assert "default: 6.0" in out          # --tau
    assert "default: 2.0" in out          # --unseen-min-dist
    assert "exit codes" in out
    assert _exit_code(["split", "--help"]) == 0
    assert "20260731" in capsys.readouterr().out
    assert _exit_code(["compare", "--help"]) == 0
    assert "B - A" in capsys.readouterr().out
