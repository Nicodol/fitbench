"""The shipped example reports must be exactly what the current renderer
produces from their own JSON. A renderer change without a regeneration of
examples/ would ship documents the tool can no longer produce; this pins the
two together (regenerate with scripts/rerender_report_md.py)."""

import json
from pathlib import Path

import pytest

from spiralcheck.report import render_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
REPORTS = sorted(EXAMPLES.glob("real_run_*_report.json"))


def test_the_expected_example_reports_are_present():
    # A silently empty glob would turn the parametrized test below into a
    # no-op that passes; pin the actual set.
    assert [p.name for p in REPORTS] == [
        "real_run_cheap2_report.json",
        "real_run_pherc1218_report.json",
        "real_run_quality2_report.json",
        "real_run_smoke8_report.json",
        "real_run_sparse2_report.json",
    ]


@pytest.mark.parametrize("json_path", REPORTS, ids=lambda p: p.stem)
def test_example_md_is_the_rendering_of_its_json(json_path):
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    md_path = json_path.with_suffix(".md")
    assert md_path.read_text(encoding="utf-8") == render_markdown(payload)
