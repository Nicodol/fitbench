# parrhesia design notes

Working notes, kept in-repo so reviewers can check the reasoning. Dates are 2026.

## The gap

`fit_spiral` (villa, `volume-cartographer/scripts/spiral`) reports *satisfaction metrics*
(`satisfaction_metrics.py`): for each input patch/pcl/track, the fraction of quad centers whose
position, mapped through the **fitted** scan-to-spiral transform, lies within 0.45 winding pitches
(spiral space) AND 6 voxels (scan space) of a snapped target winding. Three properties limit this
as an evaluation:

1. **Inputs only.** Only constraints given to the fit are scored, so the measure degenerates
   exactly where evidence is sparse. This is not a corner case: fitting with minimal verified
   inputs is an explicitly supported goal (villa #1237, closed as won't-fix: "runs with no patches
   are a valid use-case... we want to be able to fit a spiral with minimal verified inputs"). The
   leaner the inputs, the less satisfaction can say, and the more a held-out measure is needed.
2. **Measured through the fit itself.** Both the transform and `dr_per_winding` come from the model
   being evaluated. A systematically wrong deformation can move the goalposts with the surface.
3. **Not post-hoc.** It needs the fit checkpoint, torch, and the input bundle; it cannot score a
   run folder after the fact, nor surfaces produced by a different method (ScrollFiesta, lasagna).

Adjacent tools do not fill the gap: `windcheck` (as rebuilt in July 2026) is a deterministic
self-intersection validator for *individual traced surfaces*, label-free and threshold-free, from
mesh geometry alone; `get_ink_metrics.py` is a GPU proxy through an nnU-Net ink ensemble. Nothing
scores a whole-scroll winding family against evidence withheld from the fit.

## Operating point

- Input: a run's winding surfaces. Layouts supported:
  - `out/<run>/meshes/fitted[_<tag>]/wNNN[_<tag>]/` and `wNNN_spliced[_<tag>]/` directories (one
    `tifxyz` per winding, as `fit_spiral` writes them; the tag comes from `FIT_SPIRAL_RUN_TAG`);
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
- **sheet consistency** (seam-aware): a patch is one piece of papyrus, so its points must land on
  one *continuous sheet*. Winding ids alone cannot express that at the theta seam, where a patch
  legitimately spans windings w and w+1 (that is what winding indexing means on a spiral), so each
  face carries a continuous winding coordinate `u = winding_id + column / columns` (grid columns
  follow the spiral and are continuous across seams) and consistency is the largest fraction of
  the patch's points that fit within one window of 0.9 turns. 1.0 for a seam-crossing patch on a
  perfect fit; ~0.5 for a 50/50 sheet switch.
- **single-winding consistency** (raw): fraction of the patch's area assigned to its modal
  winding id. Kept alongside because it is the simplest possible definition, but it has a
  structural floor at the seam; the seam-aware metric above is the headline.
- **winding-number agreement**: when `winding.tif` is present, difference between relative winding
  deltas in the patch annotation and deltas of assigned winding ids.
- **normal agreement**: angle between patch quad normals and the matched surface normals
  (p50/p90), sign-agnostic.
- **fraction within tau** doubles as coverage: the share of patch area with a winding surface
  within tolerance.

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

`parrhesia split`: deterministic, seeded split of a verified-patch directory into `fit/` and
`heldout/` (default 80/20, stratified by z). Patches are grouped into *families* before splitting
(villa's `*_sel_*` exports, `_region_NNN` crops, `_flatboi` variants and `same_wrapNNNNNN_*`
producers are near-duplicate geometry of one parent), and a whole family goes to one side.
`split_manifest.json` records the seed, every assignment, the grouping, and two hashes per patch:
`content_sha256` (all files) and `geometry_sha256` (geometry files only, immune to metadata
rewrites). `parrhesia score --manifest --fit-inputs` refuses to score (exit 3) when a held-out
patch is found among the fit inputs, matching by geometry hash, recursively; it also refuses
(exit 4) when the *scored* patches are not the manifest's held-out side.

Honest limits of hash auditing: an exact-copy check cannot see a copy whose bytes were changed, or
geometric overlap between *different* patches. That channel is real on PHerc. Paris 4, where
verified patches overlap heavily, and it is why scoring with `--fit-inputs` also measures
**evidence leakage** geometrically: the distance of every scored point to the union of the fit's
actual input surfaces, reported as a profile, plus an **unseen** aggregate over the points farther
than `--unseen-min-dist` (default 2 vox) from every input. That measurement holds whatever the
split did, and it is the number to quote when claiming evidence was withheld.

### Why holding out is sound here, and what it costs

There is no train/test generalization in `fit_spiral`: it is per-scroll optimization, not
learning. Held-out evaluation is still the right instrument, for the same reason it has long been
standard when validating interpolations (geostatistics used withheld control points well before
machine learning): a model with millions of degrees of freedom (the deformation field) can
satisfy every constraint it was given while being wrong *between* them. Scoring on withheld
evidence measures exactly that "between": is the surface right where nothing dictated it?

Two consequences are accepted deliberately:

- A scored run is fit on the fit side only, so it is slightly less guided than a production fit
  would be. The suite's job is comparative: settings, code versions and producers are ranked
  while deprived of the same held-out side. For the surface actually shipped, refit the winning
  configuration on 100% of the patches; the intrinsic checks, which consume no ground truth,
  apply to that production fit unchanged.
- Performance on the evidence the fit consumed is a different quantity, not a wrong one: it is
  constraint satisfaction measured with a neutral ruler. The **gap** between it and the unseen
  score is the overfitting signal. A report produced with `--fit-inputs` carries both sides of
  that gap (the leakage-stratified aggregates); the headline numbers are the unseen ones, because
  the consumed side is directly optimized and therefore gameable. Deliberately scoring the fit
  side stays possible behind `--allow-unlisted-patches`, as a diagnostic. The v0 correction in
  VALIDATION.md section 6 is an involuntary demonstration of the gap's size on a real run:
  normal agreement p90 of 35.0 deg on the naive sealed set (54.8% of it effectively seen)
  against 49.9 deg on unseen evidence.

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

## Mutation audit (2026-07-27, extended 2026-07-28)

The tests themselves are audited by mutation: `scripts/mutation_check.py`
injects deliberate bugs one at a time and requires the suite to fail on every
one, then pass again unmutated. First round (eight mutations: flipped geometry
sign, broken KD-bound exactness, invalid quads treated as valid, scrambled
z/y/x axes, inverted tolerance comparison, disabled crossing alarm, swapped
angle convention, split that never holds out): 7/8 detected; the survivor
(KD-bound break) exposed a fixture too benign to need the bound, so an
adversarial mesh test (far-centroid nearest surface behind a decoy cluster)
was added; then 8/8. Integration fix found by the same audit pass: villa's
real `umbilicus.json` is a dict with `control_points`, now parsed and
unit-tested.

On 2026-07-28 an independent test-quality review ran its own counter-mutations
and eight of eight survived the suite (dead normal metric, constant published
aggregates, inverted CLI z-range, widened epsilon guard, dead inflated-gap
indicator, ignored umbilicus, and more). Every one of those now has a
dedicated test and lives in the mutation list, which also covers the v0.2
leakage/split/seam code; the audit currently stands at 23/23 detected. One of
the new tests was itself first written too symmetrically to discriminate (two
equal-sized patches) and was caught by the audit: the audit polices the tests,
including the new ones.

## Real-data notes (night of 2026-07-26/27, PHerc. Paris 4 verified patches)

- Some real patch files are LZW-compressed (mask.tif mostly; most coordinate
  grids are uncompressed): `imagecodecs` is a hard dependency to read them all.
- Loader validated on 500/500 randomly sampled complete patch dirs. The shape
  statistics below were measured on the partial sync of 2026-07-26 (3,272 of
  4,923 listed dirs) and are kept as a dated snapshot, not a reproducible
  claim: grids 4x4 to 1056x460 (median ~35x44), valid-vertex fraction median
  1.00, z spans 416..18,255, ~6% with `mask.tif`. On the complete set,
  **0/4,922 patches carry `winding.tif`**, so the winding-agreement metric is
  optional in practice and the consistency metric does the heavy lifting on
  real data.
- Overlap null-control (150 pairs from `overlapping.json`), with the overlap
  zone defined geometrically (points whose closest partner face is interior,
  not rim): the typical pair agrees to sub-voxel across its zone (per-pair p95
  distance: median 0.80 vox), and 80.7% of pairs have median <= 2 vox. The
  remaining tail clusters around ~18 vox, close to one winding pitch at full
  resolution (~173 um / 7.91 um per vox = ~22 vox): the working hypothesis is
  that `overlapping.json` also lists radially adjacent patches on neighboring
  windings, which a same-sheet check correctly reports at ~pitch distance. To
  confirm against villa's overlap semantics before quoting publicly; the
  sub-voxel head already validates loader + distance engine on real data.

## Non-goals v0

Ink-based anything, VC3D plugin, GPU, fixing fits (we only measure). Later maybe: CI-friendly
tiny fixtures, a `--compare` HTML report, ScrollFiesta adapter if formats differ.
