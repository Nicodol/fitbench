# Progress prize submission draft

Form-ready text.

---

**Title**: spiralcheck, a held-out evaluation suite for whole-scroll surface fits

**What problem does this solve?**

The 2026 open problems ask for "better evaluation suites" for the spiral fit.

villa optimises ink coverage, not geometry: `scripts/spiral/autoresearch.md`
says "The single number we optimise is" recovered ink area, and that the
satisfaction metrics "are **not the objective** ... a cross-check, not a
target". It also says what the cross-check is for: "if ink coverage climbs
while the satisfaction metrics fall off a cliff, be suspicious that you are
contorting the surface to catch stray ink rather than fitting the scroll
better."

So the open slot is the *geometric cross-check*, and satisfaction is what
currently fills it: the fraction of the fit's *own inputs* it honors, with the
target derived from each patch's own image under the fit's transform. Three
properties limit it there. It degenerates exactly where evidence is sparse,
reporting 0/0 with no patches at all. Part of its ruler moves with the model
(the spiral-space tolerance scales with the pitch the fit learned; an absolute
6-voxel scan-space tolerance does anchor the rest). And it has no post-hoc
entry point: `satisfaction_metrics.py` is a library taking a live transform
object, so a finished run folder cannot be scored as it stands, and a surface
set from another producer (ScrollFiesta, lasagna) has no villa checkpoint at
all.

villa does ship post-hoc geometric evaluation elsewhere, and this suite is
positioned next to it rather than over it: `vc_calc_surface_metrics`
(`docs/surface_metrics.md`) scores one tifxyz surface against hand-annotated
ground-truth point collections, CPU-only and checkpoint-free, and
`scripts/evaluation/eval_surface_tracer.py` drives it for the surface tracer.
Neither scores a whole winding family against withheld tifxyz patches, and
neither carries a sealed split or a leakage audit.

The first point matters most for where the project is heading. Fitting with
minimal verified inputs is an explicitly supported goal (villa #1237 was
closed as won't-fix precisely because "runs with no patches are a valid
use-case... we want to be able to fit a spiral with minimal verified
inputs"). The leaner the inputs, the less constraint satisfaction can say,
and the more an independent, held-out measure is needed.

**What does the tool do?**

spiralcheck scores a run from its output meshes alone, CPU-only, no checkpoint:

- `spiralcheck split`: seeded, z-stratified held-out split of verified patches,
  grouped by family so overlapping selections of one parent never straddle
  the split, with content and geometry hashes in the manifest; `score`
  refuses to run if the fit's inputs contain held-out patches, or if the
  scored patches are not the manifest's held-out side (audits built in).
- `spiralcheck score`: for each held-out patch, exact surface-distance
  percentiles against the winding family, fraction within tau (default 6 vox,
  matching the satisfaction tolerance), seam-aware sheet consistency (a
  physical patch must land on one continuous sheet), optional
  relative-winding agreement, and normal agreement. Given the fit's actual
  input patches, it also **measures evidence leakage geometrically** (how
  many sealed points lie within touching distance of an input surface) and
  re-scores the genuinely unseen evidence separately: on real Paris 4 data,
  name-level splits leak massively through overlapping patch selections, and
  a hash audit cannot see that. JSON + Markdown + PNG overlays.
- `spiralcheck intrinsic`: ground-truth-free checks: radial monotonicity around
  the umbilicus, collapsed/inflated inter-winding gaps, validity; violations
  localized in (z, theta).
- `spiralcheck compare`: same metrics for two runs, delta table.

Reads standard tifxyz (per-winding `wNNN[_spliced]` dirs or combined
QuadSurfaces with `winding_column_ranges`); producer-agnostic by design.

**Why trust it? (controls first, in the windcheck tradition)**

- The distance engine is exact (closest-point-on-triangle with a KD-tree
  candidate bound), verified against brute force over every triangle and
  against an independent dense-sampling reference, degenerate triangles
  included.
- Planted-defect matrix on a synthetic scroll, all covered by tests:
  radial drift is caught by distance while topology stays silent; a swapped
  sheet band is caught by consistency at near-zero distance while a perfect
  seam-crossing patch is not flagged; a collapsed gap is caught by distance
  and reported as collapsed, not as a false crossing; a planted leaked patch
  is caught by the leakage profile. Null controls are bounded by computed
  chordal-discretization limits, not magic numbers.
- The tests are themselves audited by mutation (53 injected bugs, all
  detected, a CI job on three OSes; two further candidates were left out as
  equivalent mutants rather than counted). 53/53 is a regression harness, not
  a claim of exhaustiveness: independent review rounds kept writing
  counter-mutations that survived on first contact, and VALIDATION.md section
  3 counts them and says where the suite is thin. Measured sensitivity floors
  say how small a defect each metric still catches.
- The whole package went through four independent-style review rounds
  (adversarial code review, claims audit against artifacts, upstream check,
  test-quality audit writing its own counter-mutations), each attacking the
  previous round's fixes. Every finding, including the ones that were in our
  own published numbers, is documented and corrected in VALIDATION.md.
- Real data: the loader reads 500/500 sampled verified patches of PHerc.
  Paris 4; on overlapping verified patches, the typical pair agrees to
  sub-voxel across the geometric overlap zone (per-pair p95 median 0.80 vox),
  and the pairs that do not are villa's overlap semantics rather than an engine
  error: `overlapping.json` records that two surfaces touch *somewhere* (a 2
  voxel test on sampled points), and one of its producers also lists the
  segment an expansion grew from with no geometric test. Measured: 23 of the 29
  tail pairs do touch, at a minimum distance of 0.00 vox, and diverge
  elsewhere.

**The blind spot, measured on real data**

A winding family fills space at the pitch, so every point inside the modelled
region is within half a pitch of some sheet. Any measure that reduces to "how
far is the evidence from the nearest surface" is therefore blind to a surface
that is one full winding out of place, which is the characteristic failure of
scroll fitting. `scripts/pitch_blindness.py` shows it with a known answer on
the real pipeline: displacing the held-out evidence by **two full winding
pitches (41 voxels)** moves the median distance by 0.23 vox and within-tau by
2.2 points, while the winding it is matched to moves by exactly two. This is
why the suite carries winding identity next to distance, and it bounds what
its own distance columns may claim. It is not a criticism of satisfaction,
which checks a 0.45-pitch spiral-space tolerance and would catch the same
error; the difference stays the one above, that satisfaction checks it
through the fit's own transform and only on the fit's own inputs.

**Demonstration on two real fits**

Two real `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, consumer GPU,
identical settings and step budget), differing in one input switch
(`use_verified_patches`). Both are scored on **the same 15,437 points**: the
sealed evidence lying more than 2 vox from every patch the dense run
consumed, so neither run could have seen it. spiralcheck's leakage audit is
what identifies those points: 54.8% of the naively "sealed" evidence was in
fact within half a voxel of an input the dense run had, through overlapping
patch selections that no name- or hash-level split can see.

- *Dense run* (fit-side patches): the two instruments agree. Satisfaction
  5/389 patches (1.3%); spiralcheck median distance 4.21 vox, p99 17.7 vox,
  67.6% within tau = 6. A deliberately cheap fit (1,500 steps, 8 GB VRAM),
  judged weak by both.
- *Sparse run* (no patches, the minimal-input regime #1237 declares a valid
  use-case): patch satisfaction is an **empty denominator (0/0)**. The median
  held-out distance barely moves (5.01 vox), so a summary-number check would
  call the two runs comparable. The distribution says otherwise: p90 goes
  from 9.6 to 53.9 vox and p99 from 17.7 to **246 vox**, twelve winding
  pitches, which is what an unmodelled region looks like in numbers.
  Resampling the patches (`scripts/bootstrap_ci.py`, 20,000 paired draws over
  the 78 patches carrying unseen points) confirms the distance gaps clear zero
  and reports honestly that the sheet-consistency and within-tau gaps, though
  pointing the same way, do not. That table aggregates as a point-weighted mean
  of per-patch values, so its numbers are not the pooled percentiles above and
  are not meant to restate them: it answers whether a gap is stable under
  resampling, not how large the pooled gap is.

Reports, the leakage profile, and the delta table (`spiralcheck compare`) ship
in `examples/`; VALIDATION.md section 6 also documents, openly, every
correction our own review rounds forced on earlier versions of this very
table: a fiber input left enabled in the first sparse companion, dense
numbers computed on evidence the fit had seen, a normal-agreement row that
compared two different estimators, and a sheet-consistency rule whose entire
published gain came from one mis-rated patch.

**Related work, and what is genuinely new here**

The pairing this suite rests on is not our invention, and the paper behind
`fit_spiral` states it: Henderson, *Virtually Unrolling the Herculaneum Papyri
by Diffeomorphic Spiral Fitting* (arXiv:2512.04927), scores a fit against a
hand-made reference mesh with winding-indexed metrics (winding jump fraction,
mean radial winding distance) next to a distance metric (chamfer), plus two
intrinsic sheet-quality metrics. Two of the five are implemented, in
`evaluate_wrt_gp`, inside the fitting loop and on GPU. Older still,
ThaumatoAnakalyptor's `mesh_quality.py` has scored an output mesh against a
ground-truth mesh aligned by winding angle since 2024.

So the honest claim is narrow. What no existing tool does is score a finished
run folder, from its output surfaces alone, against verified patches withheld
from that fit, on a CPU, with the leakage between "held out" and "consumed"
measured rather than assumed — and that leakage audit is the part with no
counterpart anywhere: 54.8% of the naively sealed evidence turned out to lie
within half a voxel of an input the fit had consumed. The reference mesh both
prior tools need is hundreds of hours of annotation covering one region of one
scroll; sparse verified patches exist wherever segmentation is under way.

Two of the paper's five metrics, angular defect and stretching, judge the
flattened chart rather than its placement; they are out of scope, and DESIGN.md
says why. A third, MRWD, has no analogue here at all, because it needs the
absolute winding index of the evidence and 0 of the 4,922 Paris 4 verified
patches carry a `winding.tif`. The consequence is stated there rather than left
to be found: this suite catches a winding error that cuts across a held-out
patch, not a uniform offset over a region wider than a patch.

Seven community QA efforts landed in the four weeks to 1 August 2026, none
scoring whole-fit output against withheld patches, but two now sharing this
suite's method and worth naming for that reason: constraint-gauge (criteria
hashed before measurement, and provenance declared as independent /
shared-parent / in-sample — leakage accounting as a publication rule, on the
input side) and TIFXYZ Doctor (frozen 709-patch benchmark, planted defects, 128
byte-identical null controls, declared out-of-scope defect class). Then
sheetcheck (local surface-against-CT geometry, whose warning about azimuthal
winding coordinates applies to our intrinsic checks), winding-ruler (the
marginal value of winding annotations, and the first collection-wide pitch
atlas, whose headline is that pitch is a distribution rather than a constant),
herculaneum-scroll-tools (CT-consistency audit of published predictions, the
nearest anyone comes to this object), ScrollAnchor (discontinuity review
candidates), and khj1222's held-out harness for ink. windcheck remains the
closest in spirit, on individual traced segments rather than whole fits.

**Links**

- Repository: https://github.com/Nicodol/spiralcheck, MIT, CI on
  Linux/Windows/macOS.
- DESIGN.md documents metrics, protocol, and validation; report examples in
  the repo.
