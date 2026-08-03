# Changelog

Versions are the `pyproject.toml` version at the time; v0.2 was a milestone inside the
0.1 series (the first external-style review round), not a separate release. Dates are
commit dates; the full detail of what each review round caught, including the times our
own published numbers were wrong, is in [VALIDATION.md](VALIDATION.md).

## Unreleased (August 2026): first-contact usability round

Shaped by an external first-contact test report (fresh Windows machine, no GPU, no data).
No metric changed: every number in `examples/` is unchanged, and the regenerated
Markdown reports were verified numerically identical.

- `spiralcheck demo`: a full scored run on a synthetic scroll with planted defects
  (and `--clean` for the null-control twin), so there is something to try without the
  dataset.
- README rewritten around Getting started: install, one real invocation, what comes out,
  the data-free trial path.
- CLI contract: every option documented with its default shown, options validated before
  any heavy loading, one-line errors with exit 2 instead of tracebacks, a runtime warning
  when scoring the `_spliced` variant without `--fit-inputs`.
- `report.md` now carries a reading guide per section (what the numbers mean, where the
  intrinsic bins live, what "unseen" is), names the per-patch winding column `modal
  wind.` to match the JSON's `modal_winding`, and lists the overlay PNGs it wrote.
- `compare` records both input paths, sorts per-winding rows numerically, and fails on
  files that share no metric instead of printing an empty success table; `bootstrap_ci`
  states its inputs, draws and seed in its output.
- `examples/README.md` indexes every shipped artifact; `scripts/rerender_report_md.py`
  regenerates any `report.md` from its `report.json`.
- Python floor lowered from a tacit >= 3.14 to >= 3.12 (full suite verified on 3.12,
  3.13 and 3.14; resolved dependency versions unchanged), and CI now tests both ends.
- The whole round was itself gated by a fifth review round before publication (four
  blind review passes: adversarial, claims audit against artifacts, upstream check, test
  quality). What it caught, and the fix for each finding with its test, is in the
  "Answer the pre-push review round" commit.

## v0.4.0 (2026-07-28 to 2026-08-02)

- Drift-aware sheet consistency (review round three): components merged across holes only
  on drift evidence; the v0.3 median rule was measurably wrong on real patches and was
  withdrawn. One measured limit is frozen as a strict xfail rather than patched
  (DESIGN.md, "Known limit").
- Evidence-leakage audit hardened: geometric measurement against the fit's actual input
  surfaces, unseen-only aggregate, hard refusals (exit 3/4/5) on contaminated or
  unloadable inputs.
- Real-run demonstrations: dense vs sparse (VALIDATION section 6), PHerc1218 second-scroll
  case study (section 7), and the quality-scale twins on identical sealed evidence
  (section 8), with paired bootstrap tables.
- Renamed parrhesia to spiralcheck (2026-07-31).
- Mutation audit grown to 54/54 detected.

## v0.3.0 (2026-07-28)

- Review round two folded in: 39/39 mutations detected, 74 tests.
- Family-grouped split with geometry-hash twin merging; split self-check.

## v0.1 series (2026-07-26 to 2026-07-28)

- v0.2 milestone: first external-style review round; geometric leakage measurement
  introduced after the name-level split was shown leaky on real data.
- Initial engine: exact point-to-mesh distance (verified against brute force), held-out
  metrics, intrinsic checks, seeded split, report generation, CI on three OS, first
  mutation audit (8/8), real-data loader validation on 500 patches.
