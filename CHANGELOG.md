# Changelog

Versions are the `pyproject.toml` version at the time; v0.2 was a milestone inside the
0.1 series (the first external-style review round), not a separate release. Dates are
commit dates; the full detail of what each review round caught, including the times our
own published numbers were wrong, is in [VALIDATION.md](VALIDATION.md).

## Unreleased (August 2026): first-contact usability round, planted defects on a real fit, then a real winding label

- `spiralcheck annotations`: score a run against villa point collections — the winding
  evidence VC3D actually produces on PHerc. Paris 4 — from the exported meshes and the
  umbilicus, with no checkpoint, no torch and no GPU. It is villa's own pcl satisfaction
  (`satisfaction_metrics.py`, `get_unattached_pcl_satisfied_counts`) transposed: the
  continuous winding coordinate off the nearest exported face, minus the azimuth the
  collection travels, minus the annotation, must stay constant along a collection. Points
  farther than `--tau` from every surface are declined rather than assigned a winding, and
  the report says how many. New module `src/spiralcheck/annotations.py`,
  `scripts/winding_annotations_real.py` for the real-data artifact, 17 tests.
- VALIDATION.md section 10: the winding-agreement idea run against real annotations for the
  first time — 332 of 338 decidable points on the `quality2` run, disagreements at exactly
  one turn, decision margin 32x the instrument's noise floor, and the same verdict as
  villa's own satisfaction on 17 of the 22 collections both can decide with no collection
  flagged here that villa clears. Bounded in the same section: the annotations are **fit
  inputs**, so this is constraint satisfaction and not a held-out result; under half the
  in-window points are decidable at tau = 6, mostly a window-edge artefact; and the sealed
  patches are shown *not* to descend from these collections, by reading each patch's
  recorded parent rather than assuming it.
- **Correction to VALIDATION.md section 6.** It described the 719 annotation points as
  "manually clicked in VC3D", which is true of 99 of them and wrong about the other 620.
  The `same_wrapNNN` collections are written in one commit by VC3D's
  `SameWrapAnnotationTool`, which lays down a path and resamples it at a fixed spacing:
  those 620 are not clicked one at a time. What the tool does *not* let anyone assert is
  how the path was found — it offers three modes, two image-driven and one a hand-drawn
  polyline consulting no image, and the JSON records neither the mode nor anything that
  tells them apart. An earlier draft of this entry claimed all 620 were traced along the
  papyrus in the scan; that is true of two modes out of three and not establishable per
  collection. The section now says so, and section 10 measures what the distinction is
  worth.
- `scripts/planted_defects_real.py` gains a `pitch_ramp` scenario: one pitch accumulated
  smoothly across a z band and held above it, reaching `pitch_band`'s end state without the
  one-grid-row radial wall a step leaves at each band edge. The difference between the two
  is the cliff's contribution to the collateral alarms section 9 reports, measured instead
  of argued — and it splits them. **89.2% of the step's damage to normal agreement was the
  wall** (17.9 -> 34.0 degrees stepped, 17.9 -> 19.7 ramped; 88.8% on unseen evidence), so
  that channel was accused wrongly. Sheet consistency, single-winding consistency and
  within-tau are all hit *harder* by the smooth version, so they are genuinely not
  independent of a whole-turn error and narrowing them would be a regression: a patch
  spanning a shifted labelling really does land on two sheets. Section 9 now says what
  follows from that — what names a failure mode is the combination, which this suite does
  not yet compute.
- The matrix was re-run end to end to add the seventh scenario, and the six published
  before it came back **byte-identical**, meta included, on a different day in a different
  process. `examples/planted_defects_real.json` is replaced by the seven-scenario file.

## Earlier in Unreleased: first-contact usability round, then planted defects on a real fit

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
- A second first-contact pass (same profile: fresh clone, Windows, no GPU, no data)
  before publication:
  - the follow-up commands `demo` prints are `uv run`-prefixed, so they copy-paste
    outside an activated venv (the bare form printed `command not found` for the
    Getting-started user who had just typed `uv run spiralcheck demo`);
  - a ninth demo patch crosses the theta seam into the next winding with its relative
    `winding.tif`, so winding agreement runs end to end on the zero-data path (1.0 on
    the clean twin, dropped by the swap) and the seam's structural effect on the raw
    single-winding fraction is visible on the null control instead of only documented;
  - intrinsic worst offenders interleave kinds by severity rank: 80 swap crossings can
    no longer crowd the 60 collapsed gaps out of the demo report's table, and inflated
    gaps are localized at all (they were counted but never listed). Shipped example
    reports are byte-identical: each report.json carries its own offender list;
  - the mutation audit announces 5 to 15 minutes (measured 13 on a mid-range laptop)
    in the README and its own banner, instead of "several minutes";
  - exit codes stated in every subcommand's `--help` (they were only in score and
    compare), and `.gitignore` covers `split_out/`.
- The section 8 provenance ships instead of being attested: the pre-registered
  analysis plan, verbatim (`examples/analysis_plan_quality2.fr.md`, the French
  original; SHA-256 pinned against end-of-line conversion by `.gitattributes`;
  provenance, both time anchors and an English translation in the companion
  `.md`), and the twins' villa satisfaction rows
  (`examples/real_run_{cheap2,quality2}_villa_metrics.txt`, verbatim from the
  run logs). The README header now also names villa's `fit_spiral` as what
  gets scored, with the producer-agnostic claim kept.
- Python floor lowered from a tacit >= 3.14 to >= 3.12 (full suite verified on 3.12,
  3.13 and 3.14; resolved dependency versions unchanged), and CI now tests both ends.
- The whole round was itself gated by a fifth review round before publication (four
  blind review passes: adversarial, claims audit against artifacts, upstream check, test
  quality). What it caught, and the fix for each finding with its test, is in the
  "Answer the pre-push review round" commit.
- **The planted-defect matrix stops being synthetic-only.**
  `scripts/planted_defects_real.py` damages a real `fit_spiral` run's output surfaces in
  five known ways — a whole-turn displacement over a z band, the same displacement on a
  single winding, two windings exchanging radius over a theta band, a smooth radial drift
  and a punched hole — and rescores the same 94 sealed patches under the section 8
  protocol (VALIDATION section 9, `examples/planted_defects_real.json`). The null row
  reproduces the shipped section 8 report on every field the two share except the one the
  section adds, two scorings of it are identical bit for bit, and the five defect
  scenarios reproduced byte for byte across two separate runs.
- **Winding agreement runs against a label for the first time on real data.** No PHerc.
  Paris 4 verified patch carries a `winding.tif`, so each sealed patch is labelled with
  the winding the intact fit assigns it wherever that assignment is locally unambiguous
  (31,080 of 49,458 scored quads, 90 of 94 patches). The null is 1.0 by construction;
  what section 9 reports is that a planted whole-turn error is detected and localized —
  agreement falls on 78 of the 80 straddling patches and holds at 1.0 on 9 of the 10
  that do not straddle it.
- What the planted-defect round caught *against* us is most of section 9: on real geometry
  the alarms are **not orthogonal** (the whole-turn plant fires sheet consistency,
  single-winding consistency, normal agreement and within-tau as well as winding identity,
  so section 2's "an alarm identifies the failure mode" does not transfer); the whole-turn
  plant is recovered exactly for 63% of in-band evidence rather than 100%, the run's own
  gap being irregular; distance is near-sighted rather than blind to it, which qualifies
  section 4b in the fit-side direction; sheet consistency failed to catch the sheet swap
  that the intrinsic check localized perfectly; and `report.md`'s ten-row offender table
  surfaces just 1 of 72 freshly planted crossings on a fit that already has 138.
- `tests/test_planted_defect_labels.py` pins the manufactured winding label against an
  independently written oracle (soundness, completeness and the published count), because
  the null control provably cannot: `score_patch` rounds the labels before comparing them,
  so deleting the unambiguity rule leaves winding agreement reading exactly 1.0 while
  quads whose corners disagree enter the count. CI now lints `scripts/` too, which it
  never did.

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
