"""The demo is the zero-data first contact: it must run the real scoring path
and the planted defects must fire the metrics built to catch them, while the
clean twin stays silent (the same null-control discipline as the validation)."""

import json

from spiralcheck.cli import main


def _report(out_dir):
    return json.loads((out_dir / "report" / "report.json").read_text())


def test_demo_defects_fire_the_intended_metrics(tmp_path, capsys):
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    report = _report(out)
    agg = report["heldout_aggregate"]
    intrinsic = report["intrinsic"]

    # The swap is a sheet switch: identity metrics fire...
    assert agg["min_sheet_consistency"] < 0.9
    assert agg["min_single_winding_consistency"] < 0.9
    assert intrinsic["n_violations"] > 0
    # ...including relative-winding agreement on the seam-crossing patch,
    # whose annotation disagrees with the fit exactly where the swap is...
    assert agg["mean_winding_agreement"] is not None
    assert agg["mean_winding_agreement"] < 0.9
    # ...while the collapse shows as collapsed spacing.
    assert intrinsic["n_collapsed"] > 0
    # Crossings must not crowd the collapse out of the localized offender
    # list: both kinds have rows to jump to.
    kinds = {w["kind"] for w in intrinsic["worst"][:10]}
    assert {"violation", "collapsed"} <= kinds
    # The pitch-blindness lesson: distances alone stay unremarkable.
    assert agg["dist_p50"] < 2.0

    text = capsys.readouterr().out
    assert "planted" in text
    assert "report" in text
    assert (out / "report" / "report.md").exists()
    assert list((out / "report").glob("overlay_z*.png"))


def test_demo_clean_is_a_null_control(tmp_path):
    out = tmp_path / "demo_clean"
    assert main(["demo", "--clean", "--out", str(out)]) == 0
    report = _report(out)
    agg = report["heldout_aggregate"]
    assert agg["frac_within_tau"] == 1.0
    assert agg["min_sheet_consistency"] == 1.0
    assert agg["mean_winding_agreement"] == 1.0
    assert report["intrinsic"]["n_violations"] == 0
    assert report["intrinsic"]["n_collapsed"] == 0
    assert report["intrinsic"]["n_inflated"] == 0
    assert report["intrinsic"]["worst"] == []
    # The seam-crossing patch spans two winding ids on the clean scroll: its
    # raw single-winding fraction is legitimately below 1 while its sheet
    # consistency is exactly 1.0 (the seam is why the sheet metric exists).
    # Every single-winding patch must still sit at exactly 1.0 on both.
    seam = [p for p in report["heldout_patches"] if p["winding_agreement"] is not None]
    assert len(seam) == 1
    assert seam[0]["single_winding_consistency"] < 1.0
    assert seam[0]["sheet_consistency"] == 1.0
    rest = [p for p in report["heldout_patches"] if p["winding_agreement"] is None]
    assert rest and all(p["single_winding_consistency"] == 1.0 for p in rest)


def test_demo_is_deterministic_across_invocations(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert main(["demo", "--out", str(a)]) == 0
    assert main(["demo", "--out", str(b)]) == 0
    ra, rb = _report(a), _report(b)
    assert ra["heldout_aggregate"] == rb["heldout_aggregate"]
    assert ra["intrinsic"] == rb["intrinsic"]
    assert ra["heldout_patches"] == rb["heldout_patches"]
