# spiralcheck report

- spiralcheck: 0.4.0
- meshes: D:/projets/vesuvius/quality2_results/run_p1218/2026-08-01_pherc1218_slice-9700-10500_1-patch_repro-z9700-10500-s1/meshes/fitted_repro-z9700-10500-s1
- patches: D:/projets/vesuvius/kaggle_work/pherc1218/heldout
- variant: spliced
- n_windings: 154
- tau: 6.0
- z_range: 9700,10500
- umbilicus: D:/projets/vesuvius/kaggle_work/pherc1218/umbilicus.json
- manifest: None
- fit_inputs: D:/projets/vesuvius/kaggle_work/pherc1218/fit_inputs
- unseen_min_dist: 2.0

## Held-out aggregate

*Distances from held-out patch points to the nearest fitted winding, in voxels of the mesh grid. Sheet consistency is the fraction of a patch's points landing on one continuous sheet: 1.0 means the whole patch sits on one sheet, a 50/50 sheet switch scores ~0.5. Definitions: DESIGN.md (Metrics v0); scored reference runs to compare against: examples/ in the spiralcheck repository.*

| metric | value |
|---|---|
| points | 21 |
| dist p50 / p90 / p99 (vox) | 4.848 / 7.601 / 10.132 |
| within tau = 6.0 | 71.4% |
| sheet consistency (mean / min) | 0.238 / 0.238 |
| single-winding consistency (mean / min) | 0.238 / 0.238 |
| winding agreement | not computed: no scored patch carried a usable winding grid, so winding identity was not checked |

## Evidence leakage vs fit inputs

*Share of scored points lying within touching distance of the fit's own input surfaces. Overlapping patch selections leak evidence through any name-level split; points this close were physically available to the fit, whatever the split says, and only the rest counts as unseen below.*

| measure | value |
|---|---|
| n input patches | 1 |
| frac within 0.5 vox | 0.0% |
| frac within 1 vox | 0.0% |
| frac within 2 vox | 0.0% |
| frac within 6 vox | 0.0% |

## Unseen evidence only (points > 2 vox from every fit input)

*The same metrics, restricted to the points no fit input came near: these are the numbers to quote when claiming evidence was withheld.*

| metric | value |
|---|---|
| patches used / excluded (too few unseen points) | 1 / 0 |
| points | 21 |
| dist p50 / p90 / p99 (vox) | 4.848 / 7.601 / 10.132 |
| within tau | 71.4% |
| sheet consistency (mean / min) | 0.238 / 0.238 |
| normal angle p90 (deg) | 61.5 |

## Per patch (worst first)

*modal wind. is the winding id most of the patch's points matched (an identity, not a score; the JSON field is modal_winding). Every offered patch is scored whatever its size: weigh rows with few points accordingly.*

| patch | pts | p50 | p99 | <tau | modal wind. | sheet cons. |
|---|---|---|---|---|---|---|
| seed-z4704-pherc1218 | 21 | 4.85 | 10.13 | 71% | 58 | 0.24 |

## Intrinsic checks

*Ground-truth-free checks of the winding family itself, along rays from the umbilicus: winding ids must appear in increasing radial order (violations are crossings), and consecutive-winding gaps should be near the run's pitch (collapsed: near zero; inflated: well past it). Bins span the meshes' actual z and theta extent, not --z-range, so offender locations may fall slightly outside the declared window.*

| check | value |
|---|---|
| median pitch (vox) | 20.17 |
| bins checked | 71039 |
| violations (crossings) | 4 (0.01%) |
| collapsed gaps | 5 (0.01%) |
| inflated gaps | 20 (0.03%) |

### Worst offenders

| kind | gap | inner wind | z | theta |
|---|---|---|---|---|
| violation | -2.10 | 94 | 10340..10420 | 0.00..0.13 |
| violation | -1.57 | 54 | 10340..10420 | 0.00..0.13 |
| violation | -0.39 | 35 | 10260..10340 | 0.00..0.13 |
| violation | -0.26 | 54 | 10260..10340 | -2.88..-2.75 |
| collapsed | 1.08 | 105 | 10340..10420 | -2.88..-2.75 |
| collapsed | 1.90 | 64 | 10340..10420 | 0.00..0.13 |
| collapsed | 1.93 | 22 | 10260..10340 | 0.00..0.13 |
| collapsed | 2.08 | 78 | 10340..10420 | 0.00..0.13 |
| collapsed | 3.66 | 40 | 10260..10340 | 0.00..0.13 |
