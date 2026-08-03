"""The two scripts whose output ships in examples/ have a contract too:
bootstrap_ci must say what it compared (its files are archived and reread
weeks later), and rerender_report_md --check must fail loudly on drift,
because its exit code is the only thing a caller can build on."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _run(*argv):
    return subprocess.run(
        [sys.executable, *argv], cwd=ROOT, capture_output=True, text=True, check=False
    )


def test_bootstrap_ci_states_its_inputs_and_knobs_first():
    proc = _run(
        "scripts/bootstrap_ci.py",
        "examples/real_run_quality2_report.json",
        "examples/real_run_cheap2_report.json",
        "--draws", "50", "--unseen",
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == "A: examples/real_run_quality2_report.json"
    assert lines[1] == "B: examples/real_run_cheap2_report.json"
    assert lines[2] == "draws: 50, seed: 20260731, blocks: unseen"


def test_rerender_check_passes_on_shipped_examples():
    proc = _run(
        "scripts/rerender_report_md.py", "--check",
        *(str(p.relative_to(ROOT)) for p in sorted(EXAMPLES.glob("real_run_*_report.json"))),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "STALE" not in proc.stdout


def test_rerender_check_fails_on_a_stale_md(tmp_path):
    src = EXAMPLES / "real_run_sparse2_report.json"
    json_copy = tmp_path / "real_run_sparse2_report.json"
    md_copy = tmp_path / "real_run_sparse2_report.md"
    shutil.copy(src, json_copy)
    md_copy.write_text(
        (EXAMPLES / "real_run_sparse2_report.md").read_text(encoding="utf-8") + "tampered",
        encoding="utf-8",
    )
    proc = _run("scripts/rerender_report_md.py", "--check", str(json_copy))
    assert proc.returncode == 1
    assert "STALE" in proc.stdout


def test_rerender_rewrites_a_stale_md_in_place(tmp_path):
    src = EXAMPLES / "real_run_sparse2_report.json"
    json_copy = tmp_path / "real_run_sparse2_report.json"
    md_copy = tmp_path / "real_run_sparse2_report.md"
    shutil.copy(src, json_copy)
    md_copy.write_text("stale", encoding="utf-8")
    assert _run("scripts/rerender_report_md.py", str(json_copy)).returncode == 0
    expected = (EXAMPLES / "real_run_sparse2_report.md").read_text(encoding="utf-8")
    assert md_copy.read_text(encoding="utf-8") == expected
