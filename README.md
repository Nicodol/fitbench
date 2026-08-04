# spiralcheck

**Held-out geometric evaluation for whole-scroll surface fits.**

It scores whole-scroll spiral fits from
[ScrollPrize/villa](https://github.com/ScrollPrize/villa)'s `fit_spiral`, or any
producer of `tifxyz` winding surfaces, from the output meshes alone. Built for
the "devise better evaluation suites" item of the Vesuvius Challenge
[2026 open problems](https://scrollprize.org/2026_open_problems). MIT license.

## Getting started

Requires Python >= 3.12; [uv](https://docs.astral.sh/uv/) installs a matching
interpreter by itself (plain `pip install -e .` also works on a matching Python).

```bash
git clone https://github.com/Nicodol/spiralcheck
cd spiralcheck
uv sync --group dev
uv run spiralcheck demo --out demo/
```

The demo needs no data and takes a few seconds: it builds a small synthetic scroll,
plants two defects from the validation matrix, scores the result exactly like a real run,
and tells you where each defect shows up in `demo/report/report.md`. Add `--clean` for
the null-control twin, where every alarm must stay silent.

On a real `fit_spiral` run folder:

```bash
uv run spiralcheck score \
    --meshes out/<run>/meshes/fitted_<tag> \
    --patches <heldout_patches_dir> \
    --manifest <split_manifest.json> \
    --fit-inputs <fit_patches_dir> \
    --umbilicus <dataset>/umbilicus.json \
    --z-range 10600,10900 \
    --out report/
```

This writes `report/report.json` (machine-readable), `report/report.md` (the same
numbers with a reading guide per section), and two `overlay_z*.png` slice images.
Scoring is post hoc (existing run folders, nothing re-run) and CPU-only; the section 6
demo run scores in about 75 CPU-seconds, against 6 to 16 GPU-minutes for the cheap demo
fits themselves and far longer for a production fit. Only `--meshes`, `--patches` and `--out` are
required, but `--manifest` and `--fit-inputs` are the leakage audit: without them nothing
distinguishes evidence the fit already saw (a first run without `--fit-inputs` warns
about exactly that). Every flag, default and exit code is in `spiralcheck score --help`.

The five subcommands (`spiralcheck <cmd> --help` for each):

| command | what it does |
|---|---|
| `score` | held-out metrics + evidence-leakage audit + intrinsic checks on one run |
| `split` | seeded held-out split of a patch directory, manifest with content and geometry hashes |
| `intrinsic` | ground-truth-free checks only, no patches needed |
| `compare` | metric-by-metric delta table between two `report.json` |
| `demo` | synthetic scroll with planted defects, scored end to end, zero data |

### Try it without data

Everything below replays from the repository alone, deterministically:

```bash
uv run spiralcheck demo --out demo/
uv run pytest -q
uv run spiralcheck compare examples/real_run_smoke8_report.json examples/real_run_sparse2_report.json --out cmp.md
uv run python scripts/bootstrap_ci.py examples/real_run_quality2_report.json examples/real_run_cheap2_report.json --draws 20000 --unseen
uv run python scripts/mutation_check.py
```

The `compare` and `bootstrap_ci` lines reproduce `examples/compare_smoke8_vs_sparse2.md`
and `examples/bootstrap_quality2_vs_cheap2.txt` byte for byte; the last line is the
54-mutation audit of the test suite itself (5 to 15 minutes depending on the machine;
it prints its progress).
[examples/README.md](examples/README.md) indexes every shipped artifact.
[OVERVIEW.md](OVERVIEW.md) is the narrative overview of the whole suite;
[DESIGN.md](DESIGN.md) holds the metric definitions and protocol;
[VALIDATION.md](VALIDATION.md) what was tested and the resulting numbers; the
measurement utilities behind them live in `scripts/` (each has a docstring;
`bootstrap_ci.py`'s doubles as the statistical reading guide).

## What it does

- **Held-out accuracy**: surface-distance percentiles and fraction within tau, sheet consistency
  (seam-aware and drift-aware, via a continuous winding coordinate) plus the raw single-winding
  fraction, winding-number agreement, and normal agreement, per held-out patch and aggregated.
- **Evidence-leakage audit**: given the fit's actual input patches, spiralcheck measures how much of
  the "held-out" evidence lies within touching distance of an input surface (overlapping patch
  selections make name-level splits leaky) and re-scores the genuinely unseen evidence separately.
- **Intrinsic checks**: radial monotonicity of the winding family around the umbilicus,
  inter-winding spacing distribution (collapsed and inflated gaps), validity stats.
- **Run comparison**: the same report for two run folders, with deltas.
- Reports as JSON + Markdown plus PNG overlays. CPU-only, no torch, no GPU, no checkpoint needed.

It is producer-agnostic: any directory of `tifxyz` winding surfaces whose winding ids are
readable from the directory names (`wNNN`, `wNNN_spliced`, with an optional run tag) can
be scored, and two runs can be compared metric by metric.

## Typical uses

Evaluation exists to make iteration safe. Concretely:

- **Tuning**: change a hyperparameter or an input set, re-fit, `spiralcheck compare` the two runs.
- **Regression testing**: after a change to the fitter's code, check that the output surfaces did
  not get worse; satisfaction metrics cannot answer this post hoc.
- **Cross-producer comparison**: any pipeline that emits `tifxyz` winding surfaces is scored with
  the same ruler.
- **Quality gate**: score one run and read the localized alerts (winding, z, theta) before
  spending GPU-hours of ink detection on its surfaces.

The seeded split keeps the sealed exam identical across runs, so numbers stay comparable
over time.

## Why

villa optimises whole-scroll fits for *ink coverage*, and uses *constraint satisfaction* as the
geometric cross-check against it: `scripts/spiral/autoresearch.md` calls ink area "the single
number we optimise" and the satisfaction metrics "a cross-check, not a target", there to catch a
surface "contorting ... to catch stray ink rather than fitting the scroll better".

That cross-check role is what this tool is built for. Satisfaction answers "did the optimizer
honor the constraints it was given", measured through the fit's own fitted transform, and it
cannot see errors in regions where no constraint was given. A fit with no patches at all has
nothing to dissatisfy: it reports 0/0.

There is a second, structural reason a single number cannot do this job. A winding family fills
space at the pitch, so every point inside the modelled region sits within half a pitch of some
sheet: a surface placed one full winding out of place is still close to something. Measured on
real data, displacing the held-out evidence by two full pitches (41 voxels) moves the median
distance by 0.23 vox, while the winding it is matched to moves by exactly two
(`scripts/pitch_blindness.py`). Distance and winding identity are complementary by construction,
not by preference. (villa's satisfaction checks identity too, with a 0.45-pitch spiral-space
tolerance; the difference is that it does so through the fit's own transform, and only on the
fit's own inputs.)

`spiralcheck` evaluates a fit *from its output meshes alone*, against **held-out verified patches**
that the fit never saw, plus intrinsic topology checks that need no ground truth at all.

## Status

v0.4 (July 2026): point-to-mesh distance verified against brute force over every
triangle and against an independent dense-sampling reference, held-out metrics
and intrinsic checks validated against planted defects on a synthetic scroll
(null controls silent, every defect class detected by the intended metric),
and, since August, against six defects planted in a real fit's own output
meshes, where each was caught and localized but the "one alarm names one
failure mode" property did not survive: re-planting the whole-turn error as a
smooth ramp instead of a step shows that 89% of its damage to normal agreement
was the step's own radial wall, while sheet consistency and within-tau are hit
*harder* by the smooth version and so are genuinely not independent of it
(VALIDATION.md section 9),
measured sensitivity floors, split/score/intrinsic/compare CLI covered by
end-to-end tests, loader validated on 500/500 real PHerc. Paris 4 verified
patches, and a demonstration on two real `fit_spiral` runs (see VALIDATION.md,
section 6).

August 2026 update: the quality-scale question answered on identical sealed
evidence (VALIDATION.md section 8): against a twin differing only in
`num_training_steps` (1,500 vs 6,000, same seed, same code, same GPU), the
pre-registered primary criterion (paired distance deltas) is honestly *not
met*, while the declared secondary metrics all separate the runs decisively
in the long run's favor (sheet consistency +0.21, within-tau +0.06, normals
16 degrees better, every interval excluding zero), and villa's satisfaction
metric agrees. Cross-platform reproduction of the section 6 reference within
0.26% relative bounds the platform's contribution. Plus a second-scroll
feasibility case study (section 7) and the measured shared-annotation
channel (section 6). A first-contact usability round (still August) added the
demo subcommand, the reading guides in the reports, and this Getting started;
no metric changed, and a fifth review round (four blind review passes) gated the
publication ([CHANGELOG.md](CHANGELOG.md)).

Four external-style review rounds (adversarial code review, claims audit against
artifacts, upstream check, test-quality audit writing its own counter-mutations)
shaped v0.2 onwards: the evidence-leakage audit, the drift-aware sheet
consistency, the family-grouped split with geometry-hash twin merging, and a
regression harness kept at 54/54 injected bugs detected. Each round attacked the
previous round's fixes and found more; the fourth corrected the premise of this
very README, named the villa prior art it had failed to cite, and left one
measured defect frozen in the sheet-consistency contract rather than patched.
VALIDATION.md records what each round caught, including the times it was our own
published numbers that were wrong, and section 3 says plainly what 54/54 does
and does not mean.

## In progress

Holes this repository already admits to, rather than new ideas. Anything
published here is measured and reproducible; anything in this list is not done
yet, and this section is how you can tell which is which.

- **A diagnostic layer that reads the combination of alarms.** Section 9's ramp
  measurement settled the question it was aimed at — normal agreement was
  accused wrongly, sheet consistency and within-tau were not — and left a
  consequence: those channels are genuinely not independent of a whole-turn
  error, so no single alarm names a failure mode and none should be narrowed
  until it does. What would name one is the *pattern*: identity shifted by a
  constant integer over a contiguous z band with distance barely moved is a
  turn error; distance exploding on one winding with the radial order violated
  is a misplaced sheet. The seven planted scenarios are a labelled training set
  for such rules. Nothing of it is written yet.
- **Scoring a fit that is not ours.** Every report in `examples/` scores our
  own runs on one 300-slice window of one scroll, which is the weakest thing
  about this repository. The tool is producer-agnostic within the tifxyz
  convention and CPU-only, so a run folder is all it needs — but as of early
  August 2026 the neighbouring community projects publish code rather than
  output meshes, so there is no third-party run folder to point it at.

Recently closed, with its caveats rather than without: **winding agreement
against real annotations**. No PHerc. Paris 4 verified patch carries a
`winding.tif`, so section 9 could only exercise that metric against labels
derived from the fit itself. The winding evidence exists in another shape —
villa point collections — and `spiralcheck annotations` now scores a run
against them from the exported meshes and the umbilicus, with no checkpoint and
no GPU (VALIDATION.md section 10). Three things bound that result and are
stated wherever it is quoted: the annotations are **inputs to the run scored**,
so it is constraint satisfaction and not a held-out number; under half the
in-window points are decidable, mostly a window-edge artefact; and 620 of the
719 points are traced by VC3D's annotation tool along a skeletonised CT slice
under human supervision rather than clicked one by one.

## Acknowledgments

- The `tifxyz` conventions and the satisfaction metrics this tool complements live in
  [ScrollPrize/villa](https://github.com/ScrollPrize/villa) (`volume-cartographer/scripts/spiral`).
  villa also ships `vc_calc_surface_metrics` (`docs/surface_metrics.md`), which scores a single
  tifxyz surface against hand-annotated ground-truth point collections, CPU-only and
  checkpoint-free. DESIGN.md says what it covers and what it leaves to this suite.
- The evaluation protocol for this task was published with the method: Paul Henderson,
  [*Virtually Unrolling the Herculaneum Papyri by Diffeomorphic Spiral Fitting*](https://arxiv.org/abs/2512.04927),
  which scores a fit against a hand-made reference mesh with a winding-indexed metric and a
  distance metric side by side, and implements two of its five metrics inside the fitting loop.
  DESIGN.md maps metric to metric, says which of them this suite has no analogue for and why, and
  states what is left over: a post-hoc entry point, a sealed split, and a measured leakage audit.
- [`mesh_quality.py`](https://github.com/schillij95/ThaumatoAnakalyptor/blob/main/ThaumatoAnakalyptor/mesh_quality.py)
  in ThaumatoAnakalyptor has scored an output mesh against a ground-truth mesh, aligned by winding
  angle around the umbilicus, since 2024. It is the closest prior art to the pairing used here.
- [windcheck](https://github.com/joe-carr-data/windcheck) is a label-free, deterministic
  self-intersection validator for individual traced segments; spiralcheck targets whole-scroll fit
  runs and run-to-run comparison.
- Neighbouring work from July 2026, none of which scores whole-fit output against withheld patches,
  and all of which are worth reading first:
  [constraint-gauge](https://github.com/pscamillo/constraint-gauge) (sealed, hashed criteria and
  provenance declaration applied to winding-constraint generators — the same discipline as this
  suite, on the input side),
  [TIFXYZ Doctor](https://github.com/aviad12g/tifxyz-doctor) (frozen patch benchmark, planted
  defects, byte-identical null controls),
  [sheetcheck](https://github.com/DomRusso2/sheetcheck) (local surface-against-CT geometry, and a
  warning about azimuthal winding coordinates that applies to our intrinsic checks),
  [winding-ruler](https://github.com/pscamillo/winding-ruler) (the marginal value of winding
  annotations, and the first collection-wide pitch atlas), ScrollAnchor (discontinuity review
  candidates), and
  [herculaneum-scroll-tools](https://github.com/axiosdevs/herculaneum-scroll-tools) (CT-consistency
  audit, constraint verification).
- The vesuvius-sheet-tools thread's public PHerc1218 input pack became the section 7
  second-scroll case study: its parity fit reproduced and scored unmodified (VALIDATION.md).
