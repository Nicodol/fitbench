# spiralcheck design notes

Working notes, kept in-repo so reviewers can check the reasoning. Dates are 2026.

## The gap

First, what villa optimises is not the satisfaction metrics. `scripts/spiral/autoresearch.md` is
explicit: "The single number we optimise is" the ink area recovered by rendering the fitted meshes
through an nnU-Net ink model, while the satisfaction metrics "are **not the objective** (ink
coverage is), but they are a useful *diagnostic* ... a cross-check, not a target". The same
document says what the cross-check is for: "if ink coverage climbs while the satisfaction metrics
fall off a cliff, be suspicious that you are contorting the surface to catch stray ink rather than
fitting the scroll better."

So the role in question is not "the judge", it is **the geometric cross-check against an ink
score**, and satisfaction is the one currently available for it. That is the role this suite is
built for.

`fit_spiral` reports *satisfaction metrics* (`satisfaction_metrics.py`): for each input
patch/pcl/track, the fraction of quad centers whose position, mapped through the **fitted**
scan-to-spiral transform, lies within 0.45 winding pitches (spiral space) AND 6 voxels (scan
space) of a snapped target winding. Three properties limit it in the cross-check role:

1. **Inputs only.** Only constraints given to the fit are scored, so the measure degenerates
   exactly where evidence is sparse, and reports 0/0 when there are none. This is not a corner
   case: fitting with minimal verified inputs is an explicitly supported goal (villa #1237, closed
   as won't-fix: "runs with no patches are a valid use-case... we want to be able to fit a spiral
   with minimal verified inputs"). The leaner the inputs, the less satisfaction can say, and the
   more a held-out measure is needed. (Unverified patches are scored in a separate block, but they
   are fit inputs too, carrying their own losses.)
2. **Partly measured through the fit itself.** The target a patch is judged against is that
   patch's own median shifted-radius, snapped to the nearest integer winding
   (`satisfaction_metrics.py:242-248`); the spiral-space tolerance is `0.45 * dr_per_winding`
   (`:75`), proportional to the pitch the fit learned; and the transform is applied forwards
   (`:118`) and inverted (`:289`). Part of the ruler therefore moves with the model. An earlier
   version of this note overstated it: the check is *not* purely relative, because an absolute
   6-voxel scan-space tolerance (`:291-292`) anchors it, so a fit cannot satisfy a patch by
   placing its surface far away from it. What remains is that the reference is internal.
3. **No post-hoc entry point.** `satisfaction_metrics.py` is a library with no `__main__`; it is
   called only from `fit_spiral.py` and `spiral_helpers.py`, and its signature takes a live
   transform object and the learned `dr_per_winding`. Recomputing it needs the checkpoint, torch
   and the input bundle. It cannot score a finished run folder as it stands, nor surfaces from a
   different producer (ScrollFiesta, lasagna), which have no villa checkpoint at all. This one is
   a tooling gap rather than a conceptual one: `find_inconsistent_windings.py` already rebuilds a
   transform from a checkpoint without fitting, so a post-hoc satisfaction CLI is a short script
   away for anyone with the checkpoint and a CUDA device.

### What villa already has, and what it does not cover

Stated plainly, because these are shipped and documented, and an evaluation tool that ignores
them is not credible:

- **`vc_calc_surface_metrics`** (`apps/src/`, documented in `docs/surface_metrics.md`) scores a
  tifxyz surface against a hand-annotated ground-truth point collection, CPU-only, no checkpoint,
  post hoc: `surface_missing_fraction`, `winding_error_fraction`, `in_surface_metric`. It needs
  `vc_tifxyz_winding` first. This is the closest prior art to what spiralcheck does, and it covers
  three of the same ideas. It scores *one surface* against *point collections*; it does not score
  a whole winding family against withheld tifxyz patches, and it carries no split protocol and no
  leakage audit.
- **`scripts/evaluation/eval_surface_tracer.py`** runs the surface *tracer* end to end against
  ground-truth wrap labels and aggregates the metrics above. It re-runs the pipeline rather than
  scoring an existing run folder, and it targets the tracer, not the spiral fit.
- **`find_inconsistent_windings.py`** checks the loop holonomy of the winding *annotation graph*
  and proposes a minimal set of annotations to fix. It audits the inputs' mutual consistency, not
  the output surfaces, and it requires a checkpoint and a CUDA device.
- **`get_ink_metrics.py`** is the objective itself: a GPU nnU-Net ink proxy. It says nothing about
  a region with no ink, or about a scroll with no trained ink model.
- **`windcheck`** (external, as rebuilt in July 2026) is a deterministic self-intersection
  validator for *individual traced surfaces*, label-free and threshold-free, from mesh geometry
  alone.

What is left uncovered, and is what this suite does: scoring a whole-scroll winding family, post
hoc and CPU-only, against verified patches withheld from the fit, with the leakage between "held
out" and "consumed" measured rather than assumed.

## Operating point

- Input: a run's winding surfaces. Layouts supported:
  - `out/<run>/meshes/fitted[_<tag>]/wNNN[_<tag>]/` and `wNNN_spliced[_<tag>]/` directories (one
    `tifxyz` per winding, as `fit_spiral` writes them; the tag comes from `FIT_SPIRAL_RUN_TAG`);
  - a combined QuadSurface with `winding_column_ranges` + `component_winding_ids` in `meta.json`
    (see `save_combined_tifxyz`);
  - any directory of `tifxyz` surfaces whose winding ids are readable from the directory names
    (`^w(\d+)(_spliced)?(_<tag>)?$`). Producer-agnostic within that convention: a producer that
    names its surfaces differently needs a rename or a small loader change, not a new metric.
- **The `_spliced` variant contains the fit's input patches verbatim.** `spiral_helpers.py`'s
  `_build_spliced_overlay` rasterizes the original scan coordinates of every sufficiently
  satisfied input patch into the exported mesh. Scoring that variant against evidence near an
  input therefore partly measures the splice, not the fit. `--variant plain` avoids it entirely.
  On the demo runs the effect on the published (unseen) numbers is nil, because the unseen
  aggregate already excludes everything within 2 vox of an input: rescoring the dense run with
  `--variant plain` leaves unseen p90, p99, max and normal agreement unchanged to four decimals
  and moves unseen p50 by 0.004 vox; the naive full-set numbers move by 0.05 to 0.26 vox. The
  sparse run has no patches to splice, so its two variants are identical. The leakage audit is
  what makes this true, so it stops being true if you quote the naive numbers.
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
- **sheet consistency** (component-based, drift-aware): a patch is one piece of papyrus, so its
  points must land on one *continuous sheet*. Winding ids alone cannot express that at the theta
  seam, where a patch legitimately spans windings w and w+1 (that is what winding indexing means
  on a spiral). So each face carries a continuous winding coordinate
  `u = winding_id + column / columns` (grid columns follow the spiral and are continuous across
  seams), grid-adjacent quads whose u agree within half a turn are connected, and consistency is
  the fraction of points on the largest resulting component. Holes split one physical sheet into
  several components, so components are merged, but only on evidence: a patch on one sheet has a
  roughly constant u-drift per grid step, and two components are merged only when the u
  difference at their closest grid-space pair matches what that drift predicts across the gap. A
  hole is bridged whatever its size; a switch shows a full-turn residual at zero grid distance
  and is never bridged. 1.0 for a seam-crossing or many-turn patch on a perfect fit; ~0.5 for a
  50/50 sheet switch, wherever it happens.

  **Known limit, measured and frozen rather than fixed.** The rule estimates *one* drift per
  grid direction, the median over surviving edges. When a patch's drift is not homogeneous, the
  predicted u across a hole is wrong by (drift error) x (hole width), so past 0.5 turns of
  prediction error a full-turn switch stops being distinguishable from an ordinary gap and gets
  bridged. Concretely, with a flat left half and a 0.006 turns/column right half, the switch is
  correctly seen at a 150-column hole and silently bridged from 167 columns on; with a single
  homogeneous drift it is seen at any width. On the real demo patches the same arithmetic gives
  up to about 1.2 turns of prediction uncertainty against a 0.5-turn tolerance, so this is not a
  synthetic-only concern. Both cases are pinned in `tests/test_sheet_contract.py`, the failing
  one as a strict `xfail` so that a future fix reports itself. The error is one-sided: it
  inflates the score, never deflates it. Treat sheet consistency as a lower-bound-flavoured
  indicator on patches with large holes and uneven drift, and note that on the demo pair this
  metric is also the one the bootstrap declines to call (VALIDATION.md section 6).

  Two simpler rules were tried and withdrawn, both measurably wrong on real data. A fixed-width
  window over u misreads any patch longer than the window, and Paris 4 bands run to 26 turns.
  Merging components whose *median* u are close does the opposite: it chains fragments across
  many turns. On one real patch that produced 0.986 for a surface whose own grid adjacencies were
  cut 18% of the time, against 0.399 from the raw modal fraction in the same report. See
  VALIDATION.md section 6.
- **single-winding consistency** (raw): fraction of the patch's scored quad centers assigned to
  its modal winding id. Kept alongside because it is the simplest possible definition, but it has
  a structural floor at the theta seam, where a correct fit necessarily splits a patch across two
  winding ids.
- **winding-number agreement**: when `winding.tif` is present, difference between relative winding
  deltas in the patch annotation and deltas of assigned winding ids. **Never exercised on real
  data**: 0 of the 4,922 Paris 4 verified patches carry a `winding.tif`, so every real report
  prints `winding agreement: None`. It is validated on synthetic fixtures only, and it saturates
  at 1.0 for any patch whose annotation stays inside the modal winding, whatever that annotation
  contains. Do not read a 1.0 here as evidence until a corpus with real winding grids exists.
- **normal agreement**: angle between patch quad normals and the matched surface normals
  (p50/p90), sign-agnostic.
- **fraction within tau** doubles as coverage: the share of a patch's scored quad centers with a
  winding surface within tolerance. Every metric here counts quad centers, not surface area; the
  two coincide only for evenly sampled grids.

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

`spiralcheck split`: deterministic, seeded split of a verified-patch directory into `fit/` and
`heldout/` (default 80/20 of *families*, stratified by z: the z-ordered families are cut into as
many near-equal blocks as there are families to hold out, and one family per block is drawn.
Families differ in size, so the patch-level fraction that comes out is close but not equal to the
requested one; the manifest records both). Patches are grouped into *families* before splitting
(villa's `*_sel_*` exports, `_region_NNN` crops, `_flatboi`/`_copy`/`_front`/`_back` variants and
`same_wrapNNNNNN_*` producers are near-duplicate geometry of one parent, suffixes stripped to a
fixpoint), families sharing a geometry hash are merged (byte-identical twins under unrelated
names must not straddle), and a whole family goes to one side; the writer self-checks that no
held-out geometry exists on the fit side before writing the manifest.
`split_manifest.json` records the seed, every assignment, the grouping, and two hashes per patch:
`content_sha256` (all files) and `geometry_sha256` (geometry files only, immune to metadata
rewrites). `spiralcheck score --manifest --fit-inputs` refuses to score (exit 3) when a held-out
patch is found among the fit inputs, matching by geometry hash, recursively; it also refuses
(exit 4) when the *scored* patches are not the manifest's held-out side.

Honest limits of hash auditing: an exact-copy check cannot see a copy whose bytes were changed, or
geometric overlap between *different* patches. That channel is real on PHerc. Paris 4, where
verified patches overlap heavily, and it is why scoring with `--fit-inputs` also measures
**evidence leakage** geometrically: the distance of every scored point to the union of the fit's
actual input surfaces, reported as a profile, plus an **unseen** aggregate over the points farther
than `--unseen-min-dist` (default 2 vox) from every input. That measurement holds whatever the
split did, and it is the number to quote when claiming evidence was withheld. An input patch that
cannot be read is a hard refusal (exit 5), because silently skipping it would understate leakage;
`--allow-input-load-errors` accepts the weaker guarantee and records the count in the report.

One caveat on the hash side: a manifest written before `geometry_sha256` existed (v1) makes the
audit fall back to the full-content hash, which a metadata rewrite would defeat. The manifests
shipped in `examples/` say which they are, and the leakage measurement does not depend on either.

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
  normal agreement p90 of 42.9 deg on the naive sealed set (54.8% of it effectively seen)
  against 49.9 deg on unseen evidence, both pooled over points. (An earlier version of this
  line quoted 35.0 deg on the left, which is the point-weighted mean of per-patch p90 and not
  the pooled percentile on the right. That is the same estimator mismatch VALIDATION.md
  section 6 records as a correction, so it is worth saying that it survived here until an
  independent claims audit caught it.)

## Validation plan (before any claim)

The windcheck standard, adopted:

- **Planted defects**: start from a clean fit (or synthetic ideal spiral), inject known defects:
  swap two windings in a theta band, collapse a gap to zero, apply smooth radial drift, punch
  holes. Detection precision/recall gated at thresholds fixed *before* the run.
- **Null controls**: unperturbed fits must produce zero monotonicity violations above tolerance;
  metrics on identical runs must be identical.
- **Sensitivity floor**: report the smallest planted defect each metric reliably detects.
  *Done*: `scripts/sensitivity_floor.py`, numbers in VALIDATION.md section 3.
- Round-trip: same surface read as per-winding dirs vs combined QuadSurface must agree.
  *Done*: `test_split_combined` pins the shared-seam convention and the quad count from both
  sides.
- **Resampling**: report which differences between two runs survive a resample of the scored
  patches, and which do not. *Done*: `scripts/bootstrap_ci.py`, used on the demo in
  VALIDATION.md section 6, where it shows that two of our own metrics do not separate that
  particular pair.

## Test data

- Synthetic ideal spiral + analytic patches (unit tests, no download).
- PHerc. Paris 4 spiral-input dataset (~50 GB, HF `scrollprize/datasets` bucket, sync complete:
  4,922/4,922 verified patch dirs).
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
indicator, ignored umbilicus, and more). Every one of those got a dedicated
test and a mutation entry. A second review round then attacked the fixes
themselves with fifteen fresh counter-mutations, of which thirteen survived:
the dominant pattern was fixtures pinned at a null point where weighted equals
unweighted, min equals max, one input equals many, and a passed value equals
its default. Each survivor now has a test built to discriminate (asymmetric
sizes, known displacement deltas, reference implementations inside the test),
and the audit currently stands at 53/53 detected. Two of the new tests were
themselves first written too symmetrically to discriminate and were caught by
the audit: the audit polices the tests, including the new ones.

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
  sub-voxel head is what validates loader and distance engine on real data.
  The rest is villa's overlap semantics, not an engine error, and the earlier
  guess about it was wrong. `overlapping.json` records that two surfaces touch
  *somewhere*: both geometric producers test at 2 voxels
  (`apps/src/vc_seg_add_overlap.cpp`, `kOverlapTolerance = 2.0f`, and
  `core/src/QuadSurface.cpp`'s `overlap()`, which samples random points and
  accepts at `<= 2.0`), and `apps/src/vc_grow_seg_from_seed.cpp` additionally
  inserts the segment an expansion grew from with no geometric test at all. A 2
  voxel test cannot pair surfaces a winding pitch apart, so the earlier working
  hypothesis (radially adjacent patches on neighbouring windings) is ruled out
  by villa's own code. Measured on the same 150 pairs: of the 29 whose median
  exceeds 5 vox, 23 do touch, at a minimum distance of 0.00 vox and with 1.5% to
  49% of their points within 2 vox (median 22%), then diverge elsewhere, so their
  per-pair median describes a mixed population rather than a displacement. Per-pair
  medians run to 1,998 vox at the extreme, which no same-sheet reading explains
  and which the pair-level "touches somewhere" rule does.

## Non-goals v0

Ink-based anything, VC3D plugin, GPU, fixing fits (we only measure). Later maybe: CI-friendly
tiny fixtures, a `--compare` HTML report, ScrollFiesta adapter if formats differ.
