# Validation

What was tested, how, and why the numbers can be trusted. Everything here is
reproducible from this repository; commands are at the bottom.

## 1. The measuring engine is exact

Distances are exact closest-point-on-triangle queries (Voronoi-region case
analysis), accelerated by a KD-tree stage whose search radius comes from a
per-mesh bound, so a nearer triangle can never be missed.

- Cross-checked against brute force over every triangle on 300 random query
  points (`test_surface_distance_matches_brute_force`, agreement 1e-9).
- Adversarial case included: a large triangle whose surface is nearest but
  whose centroid is far, hidden behind a decoy cluster of small triangles.
  This is the test that fails if the exactness bound is weakened
  (`test_kd_candidate_bound_is_required`).

## 2. Planted-defect matrix

Every metric is exercised against known defects injected into a synthetic
scroll with analytic ground truth. Null-control thresholds are computed from
chordal-discretization bounds, not hand-picked. Each defect must be caught by
the metric designed for it, while the others stay silent, so an alarm
identifies the failure mode.

| Planted scenario | Expected | Observed |
|---|---|---|
| Perfect scroll (null control) | silence everywhere | distances bounded by computed sagitta, 0 violations, consistency 1.0 |
| Smooth radial drift (3 vox) | distance fires, topology silent | dist p99 > 2 vox, consistency 1.0, 0 gap alarms |
| Two windings swapped in a theta band | consistency fires at near-zero distance | consistency < 0.85, dist < 0.2 vox, correct (z, theta) bins |
| Inter-winding gap collapsed to 5% | distance fires, reported as collapsed not crossing | dist p50 > 4 vox, 0 violations, collapsed bins localized |
| Holes punched in a winding | no false alarm, validity drops | 0 violations, per-winding validity < 1.0 |
| Winding labels inverted | relative winding agreement collapses | 1.0 clean, < 0.7 broken |
| Same run scored twice | identical aggregates | equal dicts |

## 3. The tests are themselves audited by mutation

`scripts/mutation_check.py` (a CI job) injects eight deliberate bugs one at a
time and requires the suite to fail on each, then pass unmutated: flipped
geometry sign, weakened KD-bound, invalid quads accepted, scrambled z/y/x
axes, inverted tolerance comparison, disabled crossing alarm, swapped angle
convention, split that never holds out. **Result: 8/8 detected.**

Honest note: the first run scored 7/8. The survivor exposed a fixture too
benign to need the KD exactness bound, so the adversarial mesh case above was
added. The same audit pass also caught a real integration gap: villa's
`umbilicus.json` is a `control_points` dict, now parsed and unit-tested.

## 4. Real data (PHerc. Paris 4)

- **Format robustness**: 500/500 randomly sampled verified patch directories
  load cleanly (LZW TIFFs, masks, grids from 4x4 to 1056x460). The full
  4,922-patch collection is hashed and split without error.
- **Engine accuracy on real geometry**: null control over 150 pairs of
  overlapping verified patches, with the overlap zone defined geometrically
  (the closest partner face must be interior, not rim): the typical pair
  agrees to sub-voxel across its zone (per-pair p95 distance, median 0.80
  vox); 80.7% of pairs are within 2 vox median.
  The residual tail clusters near one winding pitch (~22 vox at full
  resolution), consistent with `overlapping.json` also listing radially
  adjacent patches; see DESIGN.md.

## 5. Leak-free protocol

`fitbench split` writes `split_manifest.json` with the seed, every assignment
and a SHA-256 content hash per patch. `fitbench score --manifest ...
--fit-inputs ...` audits a run's inputs against it and refuses to score
(exit 3) when a held-out patch is present, matching by hash so a renamed copy
is still caught. Covered end to end by `test_split_then_score_end_to_end`.

The official Paris 4 split used here ships in
[`examples/PHercParis4_v1_split_manifest.json`](examples/PHercParis4_v1_split_manifest.json):
4,922 patches, 985 held out, seed 20260731.

## 6. Demonstration on two real fits (dense vs sparse inputs)

Two real villa `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, 120
windings, consumer RTX 3060 Ti, identical settings and step budget),
differing **only in their inputs**, both scored against the same 94 sealed
patches (49,458 quad centers, scoring restricted to the fitted window):

| measure | dense run (fit-side patches) | sparse run (no patches at all) |
|---|---|---|
| villa satisfaction, patches | 5/389 satisfied (1.3%) | **0/0 (empty denominator)** |
| villa satisfaction, unattached pcl points | 54.8% | 43.3% |
| fitbench surface distance p50 | 3.83 vox | 3.94 vox |
| fitbench surface distance p99 / max | 16.8 / 23.9 vox | 19.1 / **129.0 vox** |
| within tau = 6 vox | 72.9% | 74.1% |
| single-winding consistency (mean) | 0.43 | **0.20** |
| normal agreement p90 | 35.0 deg | **48.8 deg** |
| winding-order violations | 48 (0.10%) | 52 (0.10%) |

Reading. Both runs are deliberately cheap (1,500 steps, coarse flow field,
8 GB VRAM), and on the dense run the two instruments agree: a weak fit,
judged weak by both. The sparse run is the regime the project explicitly
wants to support (fits from minimal verified inputs; villa #1237 was closed
as won't-fix for exactly that reason), and there patch satisfaction becomes
an empty denominator while even the held-out **median** distance barely
moves. What actually degraded is sheet identity (consistency halved: the
surface passes near the papyrus but on the wrong windings), normal agreement,
and extreme outliers, which only the held-out, multi-metric view exposes.

Artifacts: [`examples/real_run_smoke8_report.md`](examples/real_run_smoke8_report.md),
[`examples/real_run_sparse1_report.md`](examples/real_run_sparse1_report.md),
[`examples/compare_smoke8_vs_sparse1.md`](examples/compare_smoke8_vs_sparse1.md),
[`examples/real_run_smoke8_overlay_z10675.png`](examples/real_run_smoke8_overlay_z10675.png).

## Reproduce

```bash
uv sync --group dev
uv run pytest -q                      # 37 tests: engine, defect matrix, e2e CLI
uv run python scripts/mutation_check.py   # 8/8 injected bugs must be detected
uv run python scripts/real_data_smoke.py <verified_patches_dir> 500
uv run python scripts/real_overlap_check.py <verified_patches_dir> 150
```
