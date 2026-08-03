# spiralcheck report

- spiralcheck: 0.4.0
- meshes: <runs>/run_cheap2/2026-08-02_s1_slice-10600-10900_389-patch_cheap2/meshes/fitted_cheap2
- patches: <data>/heldout94
- variant: spliced
- n_windings: 120
- tau: 6.0
- z_range: 10600,10900
- umbilicus: <data>/umbilicus.json
- manifest: examples/PHercParis4_v1_split_manifest.json
- fit_inputs: <data>/verified_fit
- unseen_min_dist: 2.0
- patches_dir_listed_in_manifest: 94
- manifest_n_heldout: 985
- fit_inputs_hash_audit: clean

*The scored directory offers 94 of the manifest's 985 held-out patches: a z window legitimately restricts the exam to the fitted slab. A cherry-pick would look the same, which is why both counts are recorded here.*

## Held-out aggregate

*Distances from held-out patch points to the nearest fitted winding, in voxels of the mesh grid. Sheet consistency is the fraction of a patch's points landing on one continuous sheet: 1.0 means the whole patch sits on one sheet, a 50/50 sheet switch scores ~0.5. Definitions: DESIGN.md (Metrics v0); scored reference runs to compare against: examples/ in the spiralcheck repository.*

| metric | value |
|---|---|
| points | 49458 |
| dist p50 / p90 / p99 (vox) | 3.780 / 8.836 / 16.735 |
| within tau = 6.0 | 73.2% |
| sheet consistency (mean / min) | 0.439 / 0.064 |
| single-winding consistency (mean / min) | 0.428 / 0.064 |
| winding agreement | not computed: no scored patch carried a usable winding grid, so winding identity was not checked |

## Evidence leakage vs fit inputs

*Share of scored points lying within touching distance of the fit's own input surfaces. Overlapping patch selections leak evidence through any name-level split; points this close were physically available to the fit, whatever the split says, and only the rest counts as unseen below.*

| measure | value |
|---|---|
| n input patches | 541 |
| frac within 0.5 vox | 54.8% |
| frac within 1 vox | 63.2% |
| frac within 2 vox | 68.7% |
| frac within 6 vox | 72.3% |

## Unseen evidence only (points > 2 vox from every fit input)

*The same metrics, restricted to the points no fit input came near: these are the numbers to quote when claiming evidence was withheld.*

| metric | value |
|---|---|
| patches used / excluded (too few unseen points) | 69 / 25 |
| points | 15437 |
| dist p50 / p90 / p99 (vox) | 4.205 / 9.563 / 17.729 |
| within tau | 67.5% |
| sheet consistency (mean / min) | 0.396 / 0.052 |
| normal angle p90 (deg) | 49.7 |

## Per patch (worst first)

*modal wind. is the winding id most of the patch's points matched (an identity, not a score; the JSON field is modal_winding). Every offered patch is scored whatever its size: weigh rows with few points accordingly.*

| patch | pts | p50 | p99 | <tau | modal wind. | sheet cons. |
|---|---|---|---|---|---|---|
| auto_grown_20260524200130489_sel_20260524_200712_12 | 375 | 6.06 | 20.62 | 49% | 104 | 0.23 |
| auto_grown_20260525070018371_sel_20260525_070935_25 | 49 | 8.08 | 20.60 | 35% | 51 | 0.33 |
| auto_grown_20260420220618223_region_000 | 79 | 7.96 | 20.54 | 41% | 113 | 0.61 |
| auto_grown_20260524200130489_sel_20260524_200712_2 | 81 | 4.96 | 20.00 | 62% | 79 | 0.31 |
| auto_grown_20260524201742979_sel_20260524_202046_4 | 352 | 4.43 | 19.94 | 70% | 83 | 0.41 |
| auto_trace_20260525092018344_sel_20260525_092438_38 | 153 | 6.57 | 19.78 | 44% | 52 | 0.56 |
| fill_0008_sel_20260512_104623_7 | 340 | 6.35 | 19.53 | 44% | 61 | 0.31 |
| auto_grown_20260526130029927_sel_20260526_130618_42 | 330 | 4.46 | 19.53 | 72% | 44 | 0.79 |
| auto_grown_20260521190621512_sel_20260521_190859_18 | 130 | 6.87 | 19.49 | 42% | 89 | 0.13 |
| fill_0007_sel_20260512_111459_33 | 233 | 2.40 | 19.15 | 66% | 48 | 0.46 |
| auto_grown_20260526195309752_sel_20260526_210343_44 | 112 | 4.62 | 18.98 | 65% | 93 | 0.20 |
| auto_trace_20260526151328050_sel_20260526_155150_106 | 323 | 6.77 | 18.91 | 42% | 48 | 0.41 |
| same_wrap001105_lasagna | 1054 | 5.76 | 18.85 | 52% | 33 | 0.50 |
| auto_grown_20260421165403705_sel_20260604_081020_2 | 1192 | 4.98 | 18.84 | 60% | 124 | 0.24 |
| auto_grown_20260526195309752_sel_20260526_210343_1 | 610 | 3.90 | 18.69 | 75% | 64 | 0.25 |
| same_wrap002919_lasagna | 725 | 4.80 | 18.58 | 59% | 49 | 0.17 |
| auto_grown_20260421054221178_region_000 | 1044 | 4.29 | 18.53 | 70% | 90 | 0.08 |
| auto_grown_20260525085134735_sel_20260525_085936_34 | 125 | 3.52 | 18.47 | 86% | 47 | 0.79 |
| auto_grown_20260525091409852_sel_20260525_092057_6 | 895 | 2.00 | 18.38 | 86% | 50 | 0.58 |
| auto_grown_20260429220809522_sel_20260512_104236_38 | 1341 | 3.06 | 17.94 | 77% | 34 | 0.63 |
| auto_grown_20260522204646014_sel_20260522_205109_9 | 406 | 3.10 | 17.86 | 76% | 64 | 0.61 |
| auto_grown_20260421002721090_region_000 | 326 | 4.69 | 17.83 | 63% | 104 | 0.28 |
| auto_grown_20260524200130489_sel_20260524_200712_16 | 234 | 3.68 | 17.76 | 78% | 82 | 0.57 |
| auto_grown_20260416031743018 | 114 | 5.11 | 17.72 | 63% | 49 | 0.62 |
| auto_grown_20260420204459802 | 486 | 4.53 | 17.52 | 62% | 115 | 0.66 |
| auto_grown_20260524200130489_sel_20260524_200712_14 | 300 | 3.83 | 17.29 | 71% | 83 | 0.34 |
| auto_trace_20260526151328050_sel_20260526_155150_31 | 246 | 2.84 | 16.98 | 74% | 56 | 0.50 |
| auto_grown_20260526143735233_sel_20260526_154138_115 | 971 | 5.94 | 16.65 | 51% | 47 | 0.67 |
| auto_grown_20260525085134735_sel_20260525_085936_61 | 360 | 3.55 | 16.63 | 76% | 43 | 0.55 |
| auto_grown_20260421140742657_sel_20260524_234618_21 | 254 | 5.01 | 16.49 | 57% | 89 | 0.27 |
| auto_grown_20260524195627415_sel_20260524_200047_30 | 480 | 5.06 | 16.46 | 59% | 86 | 0.42 |
| 1000_fill_sel_20260512_105755_24 | 289 | 3.96 | 16.31 | 68% | 40 | 0.45 |
| same_wrap002962_lasagna | 2111 | 4.05 | 16.26 | 76% | 63 | 0.43 |
| same_wrap002462_lasagna | 761 | 4.21 | 16.24 | 73% | 31 | 0.45 |
| auto_grown_20260614185053940 | 552 | 2.28 | 16.22 | 82% | 36 | 0.81 |
| auto_grown_20260421140742657_sel_20260524_234618_4 | 45 | 5.24 | 16.16 | 51% | 116 | 0.27 |
| auto_grown_20260526200530340_sel_20260526_211217_54 | 410 | 4.21 | 16.07 | 77% | 76 | 0.36 |
| auto_grown_20260526143735233_sel_20260526_154138_315 | 135 | 6.58 | 16.00 | 41% | 48 | 0.33 |
| auto_grown_20260521133909764_sel_20260521_133956_2 | 562 | 4.40 | 15.90 | 66% | 49 | 0.32 |
| auto_grown_20260521224733336_sel_20260521_225007_21 | 135 | 5.85 | 15.89 | 52% | 98 | 0.67 |
| auto_grown_20260526205436971_sel_20260526_212050_87 | 195 | 6.02 | 15.80 | 50% | 83 | 0.13 |
| same_wrap001130_lasagna | 495 | 2.66 | 15.76 | 90% | 48 | 0.19 |
| fill_0010_sel_20260512_111940_15 | 150 | 6.67 | 15.47 | 40% | 59 | 0.20 |
| same_wrap001896_lasagna | 1490 | 2.89 | 15.46 | 92% | 30 | 0.30 |
| auto_grown_20260522195517999_sel_20260522_200240_16 | 660 | 4.88 | 15.21 | 62% | 61 | 0.20 |
| auto_grown_20260526143735233_sel_20260526_154138_154 | 813 | 4.44 | 15.11 | 68% | 63 | 0.35 |
| same_wrap001894_lasagna | 1344 | 2.68 | 14.97 | 92% | 32 | 0.38 |
| auto_grown_20260526112529933_sel_20260526_113228_31 | 250 | 2.18 | 14.90 | 94% | 12 | 0.86 |
| 4424_david_masked | 2724 | 3.28 | 14.82 | 83% | 33 | 0.45 |
| same_wrap001879_lasagna | 97 | 4.66 | 14.52 | 64% | 20 | 0.55 |
| auto_grown_20260526123645345_sel_20260526_124600_24 | 490 | 4.64 | 14.35 | 62% | 44 | 0.16 |
| same_wrap002468_lasagna | 1336 | 4.27 | 14.27 | 74% | 38 | 0.72 |
| auto_grown_20260526104703844_flatboi_sel_20260526_113725_15 | 535 | 2.12 | 14.24 | 91% | 18 | 0.88 |
| same_wrap000360_lasagna | 726 | 3.45 | 14.22 | 91% | 29 | 0.71 |
| auto_grown_20260525071235545_sel_20260525_072130_19 | 165 | 2.60 | 14.12 | 86% | 54 | 1.00 |
| low_1_sel_20260512_112253_7 | 140 | 3.45 | 14.04 | 79% | 50 | 0.31 |
| auto_grown_20260526143735233_sel_20260526_154138_50 | 798 | 4.64 | 13.96 | 64% | 71 | 0.14 |
| same_wrap002028_lasagna | 1180 | 5.76 | 13.84 | 52% | 68 | 0.19 |
| auto_grown_20260521130313666_sel_20260521_130413_2 | 255 | 4.54 | 13.83 | 63% | 45 | 0.49 |
| auto_grown_20260527134144893_sel_20260527_150051_50 | 210 | 1.63 | 13.66 | 93% | 19 | 0.77 |
| auto_grown_20260526143735233_sel_20260526_154138_116 | 280 | 4.08 | 13.61 | 66% | 61 | 0.09 |
| auto_grown_20260526143735233_sel_20260526_154138_7 | 375 | 1.69 | 13.57 | 82% | 50 | 0.67 |
| auto_grown_20260521225553961_sel_20260521_225725_11 | 471 | 3.23 | 13.43 | 85% | 65 | 0.06 |
| auto_grown_20260521161559989_sel_20260521_162020_14 | 810 | 3.46 | 13.18 | 83% | 69 | 0.17 |
| same_wrap001111_lasagna | 708 | 3.31 | 12.90 | 88% | 34 | 0.47 |
| auto_grown_20260521131254493_sel_20260521_131346_1 | 915 | 3.89 | 12.85 | 72% | 47 | 0.45 |
| fill_0010_sel_20260512_111940_8 | 655 | 4.78 | 12.78 | 62% | 63 | 0.18 |
| auto_grown_20260416100730699 | 714 | 3.23 | 12.75 | 66% | 121 | 0.38 |
| auto_grown_20260521225553961_sel_20260521_225725_5 | 199 | 9.21 | 12.30 | 19% | 51 | 0.71 |
| auto_grown_20260526104703844_flatboi_sel_20260526_113725_22 | 563 | 1.78 | 12.29 | 93% | 16 | 0.89 |
| same_wrap001877_lasagna | 144 | 4.19 | 12.22 | 74% | 31 | 0.59 |
| same_wrap002031_lasagna | 1200 | 4.81 | 12.18 | 62% | 70 | 0.21 |
| auto_grown_20260522194733886_sel_20260522_195015_6 | 462 | 6.04 | 12.02 | 50% | 109 | 0.18 |
| auto_grown_20260526200530340_sel_20260526_211217_35 | 210 | 5.16 | 11.76 | 58% | 89 | 0.14 |
| auto_grown_20260521160538047_sel_20260521_160906_30 | 835 | 0.65 | 11.68 | 88% | 97 | 0.79 |
| auto_grown_20260526143735233_sel_20260526_154138_41 | 630 | 4.49 | 11.64 | 69% | 65 | 0.55 |
| auto_grown_20260526123645345_sel_20260526_124600_23 | 255 | 4.74 | 11.43 | 59% | 41 | 0.73 |
| same_wrap001875_lasagna | 1104 | 3.04 | 11.36 | 94% | 36 | 0.75 |
| auto_grown_20260420154248840_region_000 | 8 | 2.31 | 11.21 | 75% | 30 | 1.00 |
| 1001_fill_sel_20260512_104442_13 | 314 | 3.63 | 10.97 | 85% | 41 | 0.55 |
| same_wrap001890_lasagna | 1461 | 2.68 | 10.94 | 95% | 32 | 0.40 |
| auto_grown_20260526123645345_sel_20260526_124600_9 | 225 | 6.35 | 10.74 | 44% | 43 | 0.81 |
| auto_grown_20260526195309752_sel_20260526_210343_46 | 183 | 3.30 | 10.63 | 74% | 79 | 0.52 |
| auto_grown_20260526200530340_sel_20260526_211217_55 | 300 | 5.49 | 10.52 | 57% | 76 | 0.45 |
| auto_grown_20260527055752931_sel_20260527_060635_25 | 669 | 4.54 | 10.49 | 72% | 71 | 0.56 |
| auto_grown_20260525093749704_sel_20260525_094056_14 | 425 | 4.11 | 10.35 | 71% | 59 | 0.28 |
| auto_grown_20260525103648489_sel_20260525_104031_19 | 495 | 3.77 | 10.35 | 78% | 63 | 0.33 |
| auto_grown_20260524232311199_sel_20260524_232604_9 | 244 | 3.65 | 10.17 | 73% | 88 | 0.14 |
| auto_grown_20260524232311199_sel_20260524_232604_11 | 794 | 2.51 | 9.85 | 88% | 95 | 0.71 |
| auto_grown_20260524201742979_sel_20260524_202046_25 | 441 | 3.84 | 9.22 | 83% | 78 | 0.40 |
| auto_grown_20260525083947023_sel_20260525_090659_7 | 4 | 6.41 | 9.18 | 50% | 68 | 0.50 |
| auto_grown_20260524200130489_sel_20260524_200712_7 | 360 | 4.00 | 8.28 | 83% | 78 | 0.49 |
| auto_grown_20260526143735233_sel_20260526_154138_146 | 214 | 4.35 | 8.13 | 86% | 54 | 0.62 |
| auto_grown_20260526195309752_sel_20260526_210343_56 | 18 | 2.96 | 7.52 | 89% | 95 | 0.33 |

## Intrinsic checks

*Ground-truth-free checks of the winding family itself, along rays from the umbilicus: winding ids must appear in increasing radial order (violations are crossings), and consecutive-winding gaps should be near the run's pitch (collapsed: near zero; inflated: well past it). Bins span the meshes' actual z and theta extent, not --z-range, so offender locations may fall slightly outside the declared window.*

| check | value |
|---|---|
| median pitch (vox) | 20.30 |
| bins checked | 46344 |
| violations (crossings) | 45 (0.10%) |
| collapsed gaps | 98 (0.21%) |
| inflated gaps | 71 (0.15%) |

### Worst offenders

| kind | gap | inner wind | z | theta |
|---|---|---|---|---|
| violation | -32.40 | 78 | 10887..10921 | -2.23..-2.09 |
| violation | -18.80 | 124 | 10887..10921 | 0.13..0.26 |
| violation | -17.78 | 124 | 10887..10921 | 1.31..1.44 |
| violation | -17.74 | 127 | 10578..10612 | -2.49..-2.36 |
| violation | -12.81 | 102 | 10578..10612 | 0.39..0.52 |
| violation | -12.70 | 115 | 10578..10612 | 0.00..0.13 |
| violation | -9.79 | 89 | 10887..10921 | -2.09..-1.96 |
| violation | -9.68 | 94 | 10578..10612 | -1.18..-1.05 |
| violation | -9.52 | 79 | 10578..10612 | 2.88..3.01 |
| violation | -8.40 | 128 | 10887..10921 | -1.96..-1.83 |
