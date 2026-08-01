# spiralcheck

**Held-out geometric evaluation for whole-scroll surface fits.**

Built for the "devise better evaluation suites" item of the Vesuvius Challenge
[2026 open problems](https://scrollprize.org/2026_open_problems). MIT license.

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
that the fit never saw, plus intrinsic topology checks that need no ground truth at all. It is
producer-agnostic: any directory of `tifxyz` winding surfaces whose winding ids are readable from
the directory names (`wNNN`, `wNNN_spliced`, with an optional run tag) can be scored, and two runs can
be compared metric by metric.

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

## Typical uses

Evaluation exists to make iteration safe. Concretely:

- **Tuning**: change a hyperparameter or an input set, re-fit, `spiralcheck compare` the two runs.
- **Regression testing**: after a change to the fitter's code, check that the output surfaces did
  not get worse; satisfaction metrics cannot answer this post hoc.
- **Cross-producer comparison**: any pipeline that emits `tifxyz` winding surfaces is scored with
  the same ruler.
- **Quality gate**: score one run and read the localized alerts (winding, z, theta) before
  spending GPU-hours of ink detection on its surfaces.

Scoring is cheap (75 CPU-seconds for the demo run, against 6 to 16 GPU-minutes for the cheap
demo fits themselves, and far longer for a production fit) and post hoc (existing run folders,
nothing re-run), and the seeded split keeps the sealed exam identical across runs, so numbers
stay comparable over time.

See [DESIGN.md](DESIGN.md) for the metric definitions, the held-out split protocol, and the
planted-defect validation plan, and [VALIDATION.md](VALIDATION.md) for what was tested and the
resulting numbers (planted-defect matrix, mutation audit, real-data controls).

## Status

v0.4 (July 2026): point-to-mesh distance verified against brute force over every
triangle and against an independent dense-sampling reference, held-out metrics
and intrinsic checks validated against planted defects on a synthetic scroll
(null controls silent, every defect class detected by the intended metric),
measured sensitivity floors, split/score/intrinsic/compare CLI covered by
end-to-end tests, loader validated on 500/500 real PHerc. Paris 4 verified
patches, and a demonstration on two real `fit_spiral` runs (see VALIDATION.md,
section 6).

Four external-style review rounds (adversarial code review, claims audit against
artifacts, upstream check, test-quality audit writing its own counter-mutations)
shaped v0.2 onwards: the evidence-leakage audit, the drift-aware sheet
consistency, the family-grouped split with geometry-hash twin merging, and a
regression harness kept at 53/53 injected bugs detected. Each round attacked the
previous round's fixes and found more; the fourth corrected the premise of this
very README, named the villa prior art it had failed to cite, and left one
measured defect frozen in the sheet-consistency contract rather than patched.
VALIDATION.md records what each round caught, including the times it was our own
published numbers that were wrong, and section 3 says plainly what 53/53 does
and does not mean.

## Acknowledgments

- The `tifxyz` conventions and the satisfaction metrics this tool complements live in
  [ScrollPrize/villa](https://github.com/ScrollPrize/villa) (`volume-cartographer/scripts/spiral`).
  villa also ships `vc_calc_surface_metrics` (`docs/surface_metrics.md`), which scores a single
  tifxyz surface against hand-annotated ground-truth point collections, CPU-only and
  checkpoint-free. DESIGN.md says what it covers and what it leaves to this suite.
- The evaluation protocol for this task was published with the method: Paul Henderson,
  [*Virtually Unrolling the Herculaneum Papyri by Diffeomorphic Spiral Fitting*](https://arxiv.org/abs/2512.04927),
  which scores a fit against a hand-made reference mesh with a winding-indexed metric and a
  distance metric side by side. That pairing is the standard this suite follows; what it adds is a
  sealed split over the sparse verified patches that exist for every scroll, a measured leakage
  audit, and a run folder as the unit of work. DESIGN.md maps metric to metric and names the two
  of its five we deliberately do not implement.
- [windcheck](https://github.com/joe-carr-data/windcheck) pioneered label-free consistency checking
  for individual traced segments; spiralcheck targets whole-scroll fit runs and run-to-run comparison.
- Neighbouring work from July 2026, none of which scores whole-fit output against withheld patches,
  and all of which are worth reading first:
  [sheetcheck](https://github.com/DomRusso2/sheetcheck) (local surface-against-CT geometry),
  [winding-ruler](https://github.com/pscamillo/winding-ruler) (the marginal value of winding
  annotations, and a collection-wide pitch atlas that independently confirms the Paris 4 pitch used
  here), ScrollAnchor (discontinuity review candidates), and
  [herculaneum-scroll-tools](https://github.com/axiosdevs/herculaneum-scroll-tools) (CT-consistency
  audit, constraint verification).
- The vesuvius-sheet-tools thread's public PHerc1218 input pack is a candidate second test case.
