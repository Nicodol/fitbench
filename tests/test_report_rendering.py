"""The human-facing report must never render a missing metric as a value.

"| winding agreement | None |" reads as "no disagreement", i.e. as a pass,
while the metric was simply not computable (no scored patch carried a usable
winding grid: file absent, all-zero "single" marker, or too few finite
values). These tests pin the wording end to end: the helper, the report.md
that ``write_report`` actually produces, and the shipped example reports,
all against the same string.
"""

from pathlib import Path

from spiralcheck.report import _winding_agreement_cell, write_report

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MISSING_CELL = _winding_agreement_cell({"mean_winding_agreement": None})


def test_missing_winding_agreement_is_spelled_out():
    assert "not computed" in MISSING_CELL
    assert "winding" in MISSING_CELL
    assert MISSING_CELL != "None"


def test_present_winding_agreement_renders_number():
    assert _winding_agreement_cell({"mean_winding_agreement": 0.875}) == "0.875"


def test_write_report_spells_out_the_missing_metric(tmp_path):
    aggregate = {
        "n_points": 21,
        "dist_p50": 4.8, "dist_p90": 7.6, "dist_p99": 10.1,
        "tau": 6.0, "frac_within_tau": 0.71,
        "mean_sheet_consistency": 0.24, "min_sheet_consistency": 0.24,
        "mean_single_winding_consistency": 0.24,
        "min_single_winding_consistency": 0.24,
        "mean_winding_agreement": None,
    }
    write_report(tmp_path, None, aggregate, None)
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert f"| winding agreement | {MISSING_CELL} |" in text
    assert "| winding agreement | None |" not in text


def test_shipped_example_reports_carry_the_exact_helper_wording():
    for name in ("real_run_smoke8_report.md", "real_run_sparse2_report.md"):
        text = (EXAMPLES / name).read_text(encoding="utf-8")
        assert "| winding agreement | None |" not in text, name
        assert f"| winding agreement | {MISSING_CELL} |" in text, name
