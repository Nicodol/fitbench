"""The human-facing report must never render a missing metric as a value.

"| winding agreement | None |" reads as "no disagreement", i.e. as a pass,
while the metric was simply not computable (no winding.tif in the evidence).
These tests pin the explicit wording, in the renderer and in the shipped
example reports alike.
"""

from pathlib import Path

from spiralcheck.report import _winding_agreement_cell

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_missing_winding_agreement_is_spelled_out():
    cell = _winding_agreement_cell({"mean_winding_agreement": None})
    assert "not computed" in cell
    assert "winding.tif" in cell
    assert cell != "None"


def test_present_winding_agreement_renders_number():
    assert _winding_agreement_cell({"mean_winding_agreement": 0.875}) == "0.875"


def test_shipped_example_reports_carry_the_explicit_wording():
    for name in ("real_run_smoke8_report.md", "real_run_sparse2_report.md"):
        text = (EXAMPLES / name).read_text(encoding="utf-8")
        assert "| winding agreement | None |" not in text, name
        assert "not computed: the scored evidence carries no winding.tif" in text, name
