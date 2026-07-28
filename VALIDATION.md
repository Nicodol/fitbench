# Validation

What was tested, how, and why the numbers can be trusted. Everything here is
reproducible from this repository; commands are at the bottom.

## 1. The measuring engine is exact

Distances are exact closest-point-on-triangle queries (Voronoi-region case
analysis), accelerated by a KD-tree stage whose search radius comes from a
per-mesh bound, so a nearer triangle can never be missed.

- Cross-checked against brute force over every triangle on 300 random query
  points (`test_surface_distance_matches_brute_force`, agreement 1e-9). That
  check validates the acceleration stage against the primitive; the primitive
  itself is additionally checked against an **independent dense-sampling
  reference that shares no code with it** (barycentric grid, two-sided bracket
  from the sampling resolution, `test_primitive_against_independent_sampling`).
- Degenerate inputs are tested analytically: needle, collinear, and
  point-collapsed triangles, plus a thin-but-valid triangle that fails if the
  epsilon guard is widened (`test_degenerate_and_needle_triangles`).
- Adversarial case included: a large triangle whose surface is nearest but
  whose centroid is far, hidden behind a decoy cluster of small triangles.
  This is the test that fails if the exactness bound is weakened
  (`test_kd_candidate_bound_is_required`).
- The chunked query path (the one large real runs take) is asserted
  bit-identical to the one-shot path.

## 2. Planted-defect matrix

Every metric is exercised against known defects injected into a synthetic
scroll with analytic ground truth. Null-control thresholds are computed from
chordal-discretization bounds, not hand-picked. Each defect must be caught by
the metric designed for it, while the others stay silent, so an alarm
identifies the failure mode.

| Planted scenario | Expected | Observed |
|---|---|---|
| Perfect scroll (null control) | silence everywhere | distances bounded by computed sagitta, 0 violations, consistency 1.0, aggregates recomputable from per-point data |
| Smooth radial drift (3 vox) | distance fires, topology silent | dist p99 > 2 vox, consistency 1.0, 0 gap alarms |
| Two windings swapped in a theta band | consistency fires at near-zero distance | sheet + single-winding consistency < 0.85, dist < 0.2 vox, correct theta bins |
| Perfect patch crossing the theta seam | sheet consistency stays 1.0 (not a defect) | raw modal fraction < 1 by construction, sheet consistency exactly 1.0 |
| Inter-winding gap collapsed to 5% | distance fires, reported as collapsed not crossing | dist p50 > 4 vox, 0 violations, collapsed bins localized |
| Wrap hole (outer windings pushed +2 pitches in a band) | inflated gaps fire, no false crossing | n_inflated > 0, 0 violations |
| Rows alternately pushed +/-2 vox radially | normal agreement fires while distance stays small | angle p50 > 15 deg vs < 8 deg null, dist max < 2.5 vox |
| Holes punched in a winding | no false alarm, validity drops | 0 violations, per-winding validity < 1.0 |
| Winding labels inverted | relative winding agreement collapses | 1.0 clean, < 0.7 broken (per patch and aggregate) |
| Jittered copy of a held-out patch among fit inputs | leakage profile fires, unseen aggregate excludes it | leaked patch ~100% within 2 vox, unseen aggregate keeps only the far patch |
| Family axis far from origin, correct umbilicus passed | identical to centered family | same pitch and zero violations; wrong axis visibly breaks |
| Same run scored twice | identical aggregates | equal dicts |

## 3. The tests are themselves audited by mutation

`scripts/mutation_check.py` (a CI job on Linux, Windows and macOS) injects
deliberate bugs one at a time and requires the suite to fail on each, then
pass unmutated. The list covers the geometry engine, the metrics and their
published aggregates, the CLI glue, the intrinsic checks, and the v0.2
split/audit/leakage code. **Result: 23/23 detected.**

Honest notes, because this is where the value is. The first round (8
mutations) scored 7/8; the survivor exposed a fixture too benign to need the
KD exactness bound, and the adversarial mesh case above was added. On
2026-07-28 an independent test-quality review ran eight counter-mutations of
its own and **all eight survived** the then-current suite (dead normal metric,
published aggregates replaced by constants, inverted CLI `--z-range`, widened
epsilon guard, dead inflated-gap indicator, ignored umbilicus). Each now has a
dedicated test and a mutation entry. One of those new tests was itself first
too symmetric to discriminate (two equal-sized patches) and was caught by the
extended audit. The same review passes also caught two real integration gaps
now fixed and tested: villa's `umbilicus.json` `control_points` structure, and
the shared-seam column of combined surfaces (a half-open split dropped one
bridging quad per seam and inflated distances there).

## 4. Real data (PHerc. Paris 4)

- **Format robustness**: 500/500 randomly sampled verified patch directories
  load cleanly (LZW-compressed masks, uncompressed grids, sizes from 4x4 to
  1056x460 in the initial sync). The full 4,922-patch collection is hashed
  and split without error.
- **Engine accuracy on real geometry**: null control over 150 pairs of
  overlapping verified patches, with the overlap zone defined geometrically
  (the closest partner face must be interior, not rim): the typical pair
  agrees to sub-voxel across its zone (per-pair p95 distance, median 0.80
  vox); 80.7% of pairs are within 2 vox median.
  The residual tail clusters near one winding pitch (~22 vox at full
  resolution), consistent with `overlapping.json` also listing radially
  adjacent patches; see DESIGN.md.

## 5. Leakage control: hash audit plus geometric measurement

`fitbench split` groups patches into families first (overlapping `*_sel_*`
selections, `_region_`/`_flatboi` variants and `same_wrap` producers are
near-duplicate geometry of one parent; a family never straddles the split) and
writes `split_manifest.json` with the seed, every assignment, the grouping and
two SHA-256 hashes per patch (full content, and geometry-only so a metadata
rewrite cannot dodge the audit). `fitbench score --manifest --fit-inputs`
refuses to score (exit 3) when a held-out patch is found among the fit inputs
(by geometry hash, recursively, renamed copies included) and refuses (exit 4)
when the scored patches are not the manifest's held-out side. Covered end to
end by the CLI tests.

**A hash audit is not a physical guarantee, so it is not the claim.** On real
Paris 4 data, verified patches overlap heavily: our own adversarial review
measured that with the v1 name-level split, 54.8% of the "held-out" area of
the demo window lies within 0.5 vox of some fit-side input patch (66 of its 98
held-out patches have a `_sel_` sibling of the same parent on the fit side).
That channel is invisible to any name- or hash-level check. v0.2 therefore
measures leakage geometrically at scoring time: distance of every scored point
to the union of the fit's *actual* input surfaces, reported as a profile, and
an **unseen** aggregate over points farther than 2 vox from every input. The
demonstration below quotes the unseen numbers, not the naive ones.

Split manifests shipped: the family-grouped
[`examples/PHercParis4_v2_split_manifest.json`](examples/PHercParis4_v2_split_manifest.json)
(recommended for new fits) and the original
[`examples/PHercParis4_v1_split_manifest.json`](examples/PHercParis4_v1_split_manifest.json)
(name-level, seed 20260731, 4,922 patches, 985 held out): the demo runs below
consumed the v1 fit side, and their leakage is neutralized by the geometric
audit rather than by re-fitting.

## 6. Demonstration on two real fits (dense vs sparse inputs)

Two real villa `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, consumer
RTX 3060 Ti, identical settings and step budget), differing **in one input
switch** (`use_verified_patches`), both scored against the same 94 sealed
patches (49,458 quad centers, scoring restricted to the fitted window).

For the dense run, fitbench's leakage audit measures that 54.8% of the sealed
area lies within 0.5 vox of some fit-side input surface (overlapping patch
selections; section 5), so the honest column for it is the **unseen** one:
the 15,437 points farther than 2 vox from every input the fit consumed. The
sparse run consumed no patches, so all of its evidence is unseen by
construction.

| measure | dense run, unseen evidence | sparse run (no patches) |
|---|---|---|
| villa satisfaction, patches | 5/389 satisfied (1.3%) | **0/0 (empty denominator)** |
| villa satisfaction, unattached pcl points | 54.8% | 49.9% |
| fitbench surface distance p50 | 4.21 vox | 4.47 vox |
| within tau = 6 vox | 67.6% | 67.4% |
| fitbench surface distance p99 / max | 17.7 / 23.9 vox | **212.2 / 330.0 vox** |
| sheet consistency (mean, seam-aware) | 0.40 | **0.24** |
| normal agreement p90 | 49.9 deg | 41.8 deg |

Reading. Both runs are deliberately cheap (1,500 steps, coarse flow field,
8 GB VRAM), and on the dense run the two instruments agree: a weak fit,
judged weak by both. The sparse run is the regime the project explicitly
wants to support (fits from minimal verified inputs; villa #1237 was closed
as won't-fix for exactly that reason), and there patch satisfaction is an
empty denominator while the held-out **median** distance and within-tau are
statistically indistinguishable from the dense run: a distance-only check
would also see nothing. What actually separates them is sheet identity
(consistency 0.40 vs 0.24: the sparse surface passes near papyrus but far
more often on the wrong winding) and catastrophic tails (p99 at 212 vox: ten
winding pitches; parts of the window are simply not modeled), which only the
held-out, multi-metric view exposes and localizes.

Corrections made in v0.2, stated plainly, because they are the method working:

- The previously published table compared against a sparse companion
  (sparse1) that had accidentally kept villa's fiber input enabled (257
  collections, 6,397 points), found by an independent claims audit of the run
  logs. The sparse run above (sparse2) has patches and fibers off; the one
  changed switch is real this time.
- The previously published dense numbers were computed on all 49,458 sealed
  points, 54.8% of which the fit had effectively seen through overlapping
  input selections (found by our own adversarial review, and now measured by
  the tool itself on every scored run). On leaked evidence the dense run
  looked better than it is: its apparent normal-agreement advantage
  (35.0 vs 48.8 deg in the old table) inverts on unseen evidence
  (49.9 vs 41.8 deg). The headline contrast (sheet identity and tails)
  survives, smaller but real, on clean evidence.

Artifacts: [`examples/real_run_smoke8_report.md`](examples/real_run_smoke8_report.md)
(with the leakage profile and unseen aggregate),
[`examples/real_run_sparse2_report.md`](examples/real_run_sparse2_report.md),
[`examples/compare_smoke8_vs_sparse2.md`](examples/compare_smoke8_vs_sparse2.md),
[`examples/real_run_smoke8_overlay_z10749.png`](examples/real_run_smoke8_overlay_z10749.png).
The villa satisfaction rows are verbatim log excerpts:
[`examples/real_run_smoke8_villa_metrics.txt`](examples/real_run_smoke8_villa_metrics.txt),
[`examples/real_run_sparse2_villa_metrics.txt`](examples/real_run_sparse2_villa_metrics.txt).

## Reproduce

```bash
uv sync --group dev
uv run pytest -q                      # 60 tests: engine, defect matrix, e2e CLI
uv run python scripts/mutation_check.py   # 23/23 injected bugs must be detected
uv run python scripts/real_data_smoke.py <verified_patches_dir> 500
uv run python scripts/real_overlap_check.py <verified_patches_dir> 150
```
