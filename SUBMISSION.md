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
  much sealed area lies within touching distance of an input surface) and
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
- The tests are themselves audited by mutation (23 injected bugs, all
  detected, a CI job on three OSes), and the whole package went through an
  independent-style review round (adversarial code review, claims audit
  against artifacts, upstream check, test-quality audit) whose findings are
  documented and fixed in VALIDATION.md, including a public correction of
  our own first demo numbers.
- Real data: the loader reads 500/500 sampled verified patches of PHerc.
  Paris 4; on overlapping verified patches, the typical pair agrees to
  sub-voxel across the geometric overlap zone (per-pair p95 median 0.80 vox),
  with a residual tail near one winding pitch consistent with radially
  adjacent listings.

**Demonstration on two real fits (the blind spot, measured)**

Two real `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, consumer GPU,
identical settings and step budget), differing in one input switch
(`use_verified_patches`), both scored against the same 94 sealed patches.
The dense run's numbers are quoted on its **unseen evidence** only (15,437
points farther than 2 vox from every input it consumed; parrhesia's leakage
audit measures that 54.8% of the naive "sealed" area was effectively visible
to it through overlapping input selections):

- *Dense run* (fit-side patches): the two instruments agree. Satisfaction
  5/389 patches (1.3%); parrhesia median distance 4.21 vox, 67.6% within
  tau = 6, mean sheet consistency 0.40. A deliberately cheap fit
  (1,500 steps, 8 GB VRAM), judged weak by both.
- *Sparse run* (no patches, the minimal-input regime #1237 declares a valid
  use-case): patch satisfaction is an **empty denominator (0/0)**, and the
  held-out median distance and within-tau are indistinguishable from the
  dense run (4.47 vox, 67.4%), so a distance-only check would also see
  nothing. What the held-out suite exposes and localizes: sheet identity
  degrades (mean consistency 0.40 -> 0.24, the surface passes near papyrus
  but on the wrong windings) and catastrophic tails appear (p99 17.7 -> 212
  vox, max 23.9 -> 330 vox: parts of the window are simply not modeled).

Reports, the leakage profile, and the delta table (`parrhesia compare`) ship
in `examples/`; VALIDATION.md section 6 also documents, openly, the two
corrections our own review round forced on the first version of this very
table (a fiber input left enabled in the first sparse companion; leaked
evidence flattering the dense run's normals).

**Links**

- Repository: https://github.com/Nicodol/parrhesia, MIT, CI on
  Linux/Windows/macOS.
- DESIGN.md documents metrics, protocol, and validation; report examples in
  the repo.
