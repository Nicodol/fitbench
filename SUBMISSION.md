# Progress prize submission draft

Form-ready text.

---

**Title**: parrhesia, a held-out evaluation suite for whole-scroll surface fits

**What problem does this solve?**

The 2026 open problems ask for "better evaluation suites" for the spiral fit.
Today a whole-scroll fit is judged by its satisfaction metrics: the fraction
of its *own inputs* it honors, measured *through its own fitted transform*,
computable only with the checkpoint. That leaves three blind spots: the
measure degenerates exactly where evidence is sparse (with few or no patches
in a region there is little or nothing to dissatisfy), a systematically wrong
deformation moves the goalposts with the surface, and a finished run folder
(or a surface set from another producer, e.g. ScrollFiesta) cannot be scored
at all.

The first point matters most for where the project is heading. Fitting with
minimal verified inputs is an explicitly supported goal (villa #1237 was
closed as won't-fix precisely because "runs with no patches are a valid
use-case... we want to be able to fit a spiral with minimal verified
inputs"). The leaner the inputs, the less constraint satisfaction can say,
and the more an independent, held-out measure is needed.

**What does the tool do?**

parrhesia scores a run from its output meshes alone, CPU-only, no checkpoint:

- `parrhesia split`: seeded, z-stratified held-out split of verified patches,
  grouped by family so overlapping selections of one parent never straddle
  the split, with content and geometry hashes in the manifest; `score`
  refuses to run if the fit's inputs contain held-out patches, or if the
  scored patches are not the manifest's held-out side (audits built in).
- `parrhesia score`: for each held-out patch, exact surface-distance
  percentiles against the winding family, fraction within tau (default 6 vox,
  matching the satisfaction tolerance), seam-aware sheet consistency (a
  physical patch must land on one continuous sheet), optional
  relative-winding agreement, and normal agreement. Given the fit's actual
  input patches, it also **measures evidence leakage geometrically** (how
  many sealed points lie within touching distance of an input surface) and
  re-scores the genuinely unseen evidence separately: on real Paris 4 data,
  name-level splits leak massively through overlapping patch selections, and
  a hash audit cannot see that. JSON + Markdown + PNG overlays.
- `parrhesia intrinsic`: ground-truth-free checks: radial monotonicity around
  the umbilicus, collapsed/inflated inter-winding gaps, validity; violations
  localized in (z, theta).
- `parrhesia compare`: same metrics for two runs, delta table.

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
  equivalent mutants rather than counted). Measured sensitivity floors say
  how small a defect each metric still catches.
- The whole package went through three independent-style review rounds
  (adversarial code review, claims audit against artifacts, upstream check,
  test-quality audit writing its own counter-mutations), each attacking the
  previous round's fixes. Every finding, including the ones that were in our
  own published numbers, is documented and corrected in VALIDATION.md.
- Real data: the loader reads 500/500 sampled verified patches of PHerc.
  Paris 4; on overlapping verified patches, the typical pair agrees to
  sub-voxel across the geometric overlap zone (per-pair p95 median 0.80 vox),
  with a residual tail near one winding pitch consistent with radially
  adjacent listings.

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
consumed, so neither run could have seen it. parrhesia's leakage audit is
what identifies those points: 54.8% of the naively "sealed" evidence was in
fact within half a voxel of an input the dense run had, through overlapping
patch selections that no name- or hash-level split can see.

- *Dense run* (fit-side patches): the two instruments agree. Satisfaction
  5/389 patches (1.3%); parrhesia median distance 4.21 vox, p99 17.7 vox,
  67.6% within tau = 6. A deliberately cheap fit (1,500 steps, 8 GB VRAM),
  judged weak by both.
- *Sparse run* (no patches, the minimal-input regime #1237 declares a valid
  use-case): patch satisfaction is an **empty denominator (0/0)**. The median
  held-out distance barely moves (5.01 vox), so a summary-number check would
  call the two runs comparable. The distribution says otherwise: p90 goes
  from 9.6 to 53.9 vox and p99 from 17.7 to **246 vox**, twelve winding
  pitches, which is what an unmodelled region looks like in numbers.
  Resampling the patches (`scripts/bootstrap_ci.py`) confirms the distance
  gaps clear zero and reports honestly that the sheet-consistency and
  within-tau gaps, though pointing the same way, do not.

Reports, the leakage profile, and the delta table (`parrhesia compare`) ship
in `examples/`; VALIDATION.md section 6 also documents, openly, every
correction our own review rounds forced on earlier versions of this very
table: a fiber input left enabled in the first sparse companion, dense
numbers computed on evidence the fit had seen, a normal-agreement row that
compared two different estimators, and a sheet-consistency rule whose entire
published gain came from one mis-rated patch.

**Links**

- Repository: https://github.com/Nicodol/parrhesia, MIT, CI on
  Linux/Windows/macOS.
- DESIGN.md documents metrics, protocol, and validation; report examples in
  the repo.
