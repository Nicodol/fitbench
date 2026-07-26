# Progress prize submission draft (July 2026)

Form-ready text. Fill the [PLACEHOLDER] after the real-fit demo run.

---

**Title**: fitbench, a held-out evaluation suite for whole-scroll surface fits

**What problem does this solve?**

The 2026 open problems ask for "better evaluation suites" for the spiral fit.
Today a whole-scroll fit is judged by its satisfaction metrics: the fraction
of its *own inputs* it honors, measured *through its own fitted transform*,
computable only with the checkpoint. That leaves three blind spots: regions
with no constraints are invisible (a zero-patch fit has nothing to fail,
see villa issue #1237), a systematically wrong deformation moves the
goalposts with the surface, and a finished run folder (or a surface set from
another producer, e.g. ScrollFiesta) cannot be scored at all.

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

**Demonstration on a real fit**

[PLACEHOLDER: small-window fit_spiral run, scored held-out; plus the
zero-patch #1237 scenario detected by intrinsic checks where satisfaction
reports nothing.]

**Links**

- Repository: https://github.com/Nicodol/fitbench, MIT, CI on
  Linux/Windows/macOS.
- DESIGN.md documents metrics, protocol, and validation; report examples in
  the repo.
