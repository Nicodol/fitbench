# parrhesia

**Held-out geometric evaluation for whole-scroll surface fits.**

Built for the "devise better evaluation suites" item of the Vesuvius Challenge
[2026 open problems](https://scrollprize.org/2026_open_problems). MIT license.

## Why

Whole-scroll fits (villa's `fit_spiral`, and other producers of per-winding surface sets) are
currently judged by *constraint satisfaction*: what fraction of the fit's own inputs the final
surface honors, measured through the fit's own fitted transform. That number answers "did the
optimizer satisfy its constraints", not "is this surface geometrically right", and it cannot see
errors in regions where no constraint was given. A fit with no patches at all has nothing to
dissatisfy.

`parrhesia` evaluates a fit *from its output meshes alone*, against **held-out verified patches**
that the fit never saw, plus intrinsic topology checks that need no ground truth at all. It is
producer-agnostic: anything that emits `tifxyz` winding surfaces can be scored, and two runs can
be compared metric by metric.

## What it does

- **Held-out accuracy**: surface-distance percentiles and fraction within tau, sheet consistency
  (seam-aware, via a continuous winding coordinate) plus the raw single-winding fraction,
  winding-number agreement, and normal agreement, per held-out patch and aggregated.
- **Evidence-leakage audit**: given the fit's actual input patches, parrhesia measures how much of
  the "held-out" evidence lies within touching distance of an input surface (overlapping patch
  selections make name-level splits leaky) and re-scores the genuinely unseen evidence separately.
- **Intrinsic checks**: radial monotonicity of the winding family around the umbilicus,
  inter-winding spacing distribution (collapsed and inflated gaps), validity stats.
- **Run comparison**: the same report for two run folders, with deltas.
- Reports as JSON + Markdown plus PNG overlays. CPU-only, no torch, no GPU, no checkpoint needed.

## Typical uses

Evaluation exists to make iteration safe. Concretely:

- **Tuning**: change a hyperparameter or an input set, re-fit, `parrhesia compare` the two runs.
- **Regression testing**: after a change to the fitter's code, check that the output surfaces did
  not get worse; satisfaction metrics cannot answer this post hoc.
- **Cross-producer comparison**: any pipeline that emits `tifxyz` winding surfaces is scored with
  the same ruler.
- **Quality gate**: score one run and read the localized alerts (winding, z, theta) before
  spending GPU-hours of ink detection on its surfaces.

Scoring is cheap (CPU minutes, against GPU hours for a fit) and post hoc (existing run folders,
nothing re-run), and the seeded split keeps the sealed exam identical across runs, so numbers
stay comparable over time.

See [DESIGN.md](DESIGN.md) for the metric definitions, the held-out split protocol, and the
planted-defect validation plan, and [VALIDATION.md](VALIDATION.md) for what was tested and the
resulting numbers (planted-defect matrix, mutation audit, real-data controls).

## Status

v0.3 (July 2026): exact point-to-mesh distance (verified against brute force
over every triangle and against an independent dense-sampling reference),
held-out metrics and intrinsic checks validated against planted defects on a
synthetic scroll (null controls silent, every defect class detected by the
intended metric), split/score/intrinsic/compare CLI covered by end-to-end
tests, loader validated on 500/500 real PHerc. Paris 4 verified patches, and a
demonstration on two real `fit_spiral` runs (see VALIDATION.md, section 6).
Two external-style review rounds (adversarial code review, claims audit
against artifacts, upstream check, test-quality audit with its own
counter-mutations) shaped v0.2 and v0.3: the evidence-leakage audit, the
component-based sheet consistency (robust to patches spanning many turns),
the family-grouped split with geometry-hash twin merging, and a test suite
hardened until 39/39 injected bugs are detected. VALIDATION.md records what
each round caught, including in our own numbers.

## Acknowledgments

- The `tifxyz` conventions and the satisfaction metrics this tool complements live in
  [ScrollPrize/villa](https://github.com/ScrollPrize/villa) (`volume-cartographer/scripts/spiral`).
- [windcheck](https://github.com/joe-carr-data/windcheck) pioneered label-free consistency checking
  for individual traced segments; parrhesia targets whole-scroll fit runs and run-to-run comparison.
- The vesuvius-sheet-tools thread's public PHerc1218 input pack is a candidate second test case.
