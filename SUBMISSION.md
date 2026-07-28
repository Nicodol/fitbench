# Progress prize submission draft

Form-ready text.

---

**Title**: fitbench, a held-out evaluation suite for whole-scroll surface fits

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

fitbench scores a run from its output meshes alone, CPU-only, no checkpoint:

- `fitbench split`: seeded, z-stratified held-out split of verified patches,
  with a content-hash manifest; `score` refuses to run if the fit's inputs
  contain held-out patches (audit built in).
- `fitbench score`: for each held-out patch, exact surface-distance
  percentiles against the winding family, fraction within tau (default 6 vox,
  matching the satisfaction tolerance), single-winding consistency (a physical
  patch must land on one winding), optional relative-winding agreement, and
  normal agreement. JSON + Markdown + PNG overlays.
- `fitbench intrinsic`: ground-truth-free checks: radial monotonicity around
  the umbilicus, collapsed/inflated inter-winding gaps, validity; violations
  localized in (z, theta).
- `fitbench compare`: same metrics for two runs, delta table.

Reads standard tifxyz (per-winding `wNNN[_spliced]` dirs or combined
QuadSurfaces with `winding_column_ranges`); producer-agnostic by design.

**Why trust it? (controls first, in the windcheck tradition)**

- The distance engine is exact (closest-point-on-triangle with a KD-tree
  candidate bound) and verified against brute force in the test suite.
- Planted-defect matrix on a synthetic scroll, all covered by tests:
  radial drift is caught by distance while topology stays silent; a swapped
  sheet band is caught by consistency at near-zero distance; a collapsed gap
  is caught by distance and reported as collapsed, not as a false crossing;
  punched holes lower validity without false alarms. Null controls are bounded
  by computed chordal-discretization limits, not magic numbers.
- Real data: the loader reads 500/500 sampled verified patches of PHerc.
  Paris 4; on overlapping verified patches, the typical pair agrees to
  sub-voxel across the geometric overlap zone (per-pair p95 median 0.80 vox),
  with a residual tail near one winding pitch consistent with radially
  adjacent listings.

**Demonstration on two real fits (the blind spot, measured)**

Two real `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, 120 windings,
consumer GPU, identical settings), differing only in inputs, both scored
against the same 94 sealed patches (49,458 points):

- *Dense run* (fit-side patches): the two instruments agree. Satisfaction
  5/389 patches (1.3%); fitbench median distance 3.83 vox, 72.9% within
  tau = 6, mean single-winding consistency 0.43. A deliberately cheap fit
  (1,500 steps, 8 GB VRAM), judged weak by both.
- *Sparse run* (no patches at all, the minimal-input regime #1237 declares
  a valid use-case): patch satisfaction is an **empty denominator (0/0)**,
  and even the held-out median distance barely moves (3.94 vox, 74.1%
  within tau), so a distance-only check would also pass it. What the
  held-out suite exposes is that sheet identity halved (mean consistency
  0.43 -> 0.20: the surface passes near the papyrus but on the wrong
  windings), normal agreement degraded (p90 35.0 -> 48.8 deg) and extreme
  outliers appeared (max 23.9 -> 129.0 vox).

Same window, same sealed patches, one variable. Reports and the delta table
(`fitbench compare`) in `examples/`.

**Links**

- Repository: https://github.com/Nicodol/fitbench, MIT, CI on
  Linux/Windows/macOS.
- DESIGN.md documents metrics, protocol, and validation; report examples in
  the repo.
