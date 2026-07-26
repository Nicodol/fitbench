# fitbench design notes

Working notes, kept in-repo so reviewers can check the reasoning. Dates are 2026.

## The gap

`fit_spiral` (villa, `volume-cartographer/scripts/spiral`) reports *satisfaction metrics*
(`satisfaction_metrics.py`): for each input patch/pcl/track, the fraction of quad centers whose
position, mapped through the **fitted** scan-to-spiral transform, lies within 0.45 winding pitches
(spiral space) AND 6 voxels (scan space) of a snapped target winding. Three properties limit this
as an evaluation:

1. **Inputs only.** Only constraints given to the fit are scored. Regions without constraints are
   invisible, and a fit run with zero patches has nothing to fail against (see villa issue #1237).
2. **Measured through the fit itself.** Both the transform and `dr_per_winding` come from the model
   being evaluated. A systematically wrong deformation can move the goalposts with the surface.
3. **Not post-hoc.** It needs the fit checkpoint, torch, and the input bundle; it cannot score a
   run folder after the fact, nor surfaces produced by a different method (ScrollFiesta, lasagna).

Adjacent tools do not fill the gap: `windcheck` audits *individual traced segments* for
wrap-relapse from mesh geometry (no ground truth), and `get_ink_metrics.py` is a GPU proxy through
an ink model trained on one scroll. Nothing scores a whole-scroll winding family against evidence
withheld from the fit.

## Operating point

- Input: a run's winding surfaces. Layouts supported:
  - `out/<run>/meshes/mesh/wNNN/` and `wNNN_spliced/` directories (one `tifxyz` per winding);
  - a combined QuadSurface with `winding_column_ranges` + `component_winding_ids` in `meta.json`
    (see `save_combined_tifxyz`);
  - any directory of `tifxyz` surfaces with winding ids parseable from names (producer-agnostic).
- Evidence: held-out **verified patches** (`tifxyz`, with optional `mask.tif`, `winding.tif`),
  plus the umbilicus (z to yx polyline) when available.
- Output: `report.json` (machine-readable), a Markdown summary, PNG overlays (windings over
  selected z slices, colored by local score).
- Pure CPU: numpy + scipy. No torch, no checkpoint, no GPU.

## Metrics v0

Held-out, per patch (then aggregated):

- **surface distance**: for each valid patch quad center, distance to the nearest point on the
  nearest winding surface (closest-point-on-triangle over the winding's valid quads, KD-tree
  accelerated). Report p50/p90/p99 and fraction within tau (tau default 6 vox, matching the
  satisfaction tolerance for comparability).
- **single-winding consistency**: fraction of the patch's area assigned to its modal winding id.
  A patch is one piece of papyrus; if its points split across windings, the fit switched sheets.
- **winding-number agreement**: when `winding.tif` is present, difference between relative winding
  deltas in the patch annotation and deltas of assigned winding ids.
- **normal agreement**: angle between patch quad normals and the matched surface normals
  (p50/p90), sign-agnostic.
- **coverage**: fraction of patch area with any winding surface within tau.

Intrinsic, no ground truth:

- **radial monotonicity**: along rays from the umbilicus at sampled (z, theta), winding ids must
  appear in increasing radial order; count and localize violations (sheet swaps, crossings).
- **spacing sanity**: distribution of consecutive-winding radial gaps per (z, theta); flag
  collapsed (near-zero) and inflated gaps vs the run's median pitch.
- **self-intersection indicators**: negative gaps above, plus per-surface quad flips (normal sign
  changes within a surface).
- **validity stats**: valid-vertex fraction per winding, holes, bbox vs declared z range.

Run comparison: same report for runs A and B, plus a delta table keyed by metric.

## Held-out protocol

`fitbench split`: deterministic, seeded split of a verified-patch directory into `fit/` and
`heldout/` (default 80/20 by patch, stratified by z extent). Writes `split_manifest.json` with
seed, per-patch assignment, and content hashes, so a reported number is reproducible and it is
checkable that the fit's input dir matches the manifest's `fit/` side. Scoring refuses to run if a
held-out patch uuid appears in the run's recorded inputs (when the run folder carries that info).

## Validation plan (before any claim)

The windcheck standard, adopted:

- **Planted defects**: start from a clean fit (or synthetic ideal spiral), inject known defects:
  swap two windings in a theta band, collapse a gap to zero, apply smooth radial drift, punch
  holes. Detection precision/recall gated at thresholds fixed *before* the run.
- **Null controls**: unperturbed fits must produce zero monotonicity violations above tolerance;
  metrics on identical runs must be identical.
- **Sensitivity floor**: report the smallest planted defect each metric reliably detects.
- Round-trip: same surface read as per-winding dirs vs combined QuadSurface must agree.

## Test data

- Synthetic ideal spiral + analytic patches (unit tests, no download).
- PHerc. Paris 4 spiral-input dataset (~50 GB, HF `scrollprize/datasets` bucket, syncing).
- Candidate second scroll: PHerc1218 public input pack (vesuvius-sheet-tools thread).

## Non-goals v0

Ink-based anything, VC3D plugin, GPU, fixing fits (we only measure). Later maybe: CI-friendly
tiny fixtures, a `--compare` HTML report, ScrollFiesta adapter if formats differ.
