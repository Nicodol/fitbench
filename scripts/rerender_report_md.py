"""Re-render a report's Markdown from its report.json after a renderer change.

The Markdown summary is a pure view of report.json (``render_markdown``), so
improving the wording must never touch a number: this script rewrites the .md
sibling of each given report.json from the JSON alone. With ``--check`` it
verifies instead of writing, which is how the shipped ``examples/`` reports
are kept identical to what the current code renders (see
``tests/test_examples_coherence.py``). Overlay listings are the one section
that cannot be reconstructed from JSON and are omitted by a re-render.

    uv run python scripts/rerender_report_md.py examples/real_run_*_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiralcheck.report import render_markdown


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reports", nargs="+", help="report.json files (the .md sibling is derived)")
    p.add_argument("--check", action="store_true",
                   help="verify the .md files are in sync instead of rewriting them")
    args = p.parse_args(argv)

    stale = []
    for report in args.reports:
        json_path = Path(report)
        md_path = json_path.with_suffix(".md")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        rendered = render_markdown(payload)
        if args.check:
            current = md_path.read_text(encoding="utf-8") if md_path.exists() else None
            status = "in sync" if current == rendered else "STALE"
            print(f"{md_path}: {status}")
            if current != rendered:
                stale.append(md_path)
        else:
            md_path.write_text(rendered, encoding="utf-8")
            print(f"rendered {md_path}")
    if stale:
        print(f"{len(stale)} file(s) differ from what the current renderer produces; "
              "rerun without --check to regenerate")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
