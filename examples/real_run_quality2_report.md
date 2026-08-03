# spiralcheck report

- spiralcheck: 0.4.0
- meshes: <runs>/run/2026-08-02_s1_slice-10600-10900_389-patch_quality2/meshes/fitted_quality2
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
| dist p50 / p90 / p99 (vox) | 1.987 / 7.630 / 16.826 |
| within tau = 6.0 | 84.0% |
| sheet consistency (mean / min) | 0.744 / 0.156 |
| single-winding consistency (mean / min) | 0.718 / 0.156 |
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
| dist p50 / p90 / p99 (vox) | 3.726 / 9.863 / 19.063 |
| within tau | 73.5% |
| sheet consistency (mean / min) | 0.605 / 0.084 |
| normal angle p90 (deg) | 24.1 |

## Per patch (worst first)

*modal wind. is the winding id most of the patch's points matched (an identity, not a score; the JSON field is modal_winding). Every offered patch is scored whatever its size: weigh rows with few points accordingly.*

| patch | pts | p50 | p99 | <tau | modal wind. | sheet cons. |
|---|---|---|---|---|---|---|
| same_wrap002028_lasagna | 1180 | 6.51 | 26.33 | 47% | 61 | 0.52 |
| same_wrap002031_lasagna | 1200 | 3.54 | 22.74 | 65% | 63 | 0.76 |
| fill_0010_sel_20260512_111940_8 | 655 | 2.55 | 22.71 | 71% | 63 | 0.58 |
| same_wrap001105_lasagna | 1054 | 4.09 | 22.47 | 61% | 33 | 0.88 |
| auto_grown_20260526143735233_sel_20260526_154138_50 | 798 | 5.10 | 21.70 | 54% | 65 | 0.32 |
| auto_grown_20260525070018371_sel_20260525_070935_25 | 49 | 7.49 | 20.53 | 33% | 60 | 0.71 |
| auto_grown_20260526195309752_sel_20260526_210343_1 | 610 | 1.75 | 19.85 | 86% | 72 | 0.41 |
| auto_grown_20260524201742979_sel_20260524_202046_4 | 352 | 3.04 | 19.76 | 88% | 83 | 0.70 |
| auto_grown_20260526143735233_sel_20260526_154138_116 | 280 | 3.04 | 19.21 | 78% | 55 | 0.24 |
| auto_trace_20260526151328050_sel_20260526_155150_106 | 323 | 3.13 | 18.64 | 74% | 56 | 0.52 |
| auto_grown_20260420220618223_region_000 | 79 | 4.03 | 18.29 | 67% | 115 | 0.95 |
| auto_grown_20260526130029927_sel_20260526_130618_42 | 330 | 4.58 | 18.03 | 85% | 46 | 0.58 |
| auto_grown_20260521190621512_sel_20260521_190859_18 | 130 | 4.39 | 17.80 | 65% | 83 | 0.28 |
| auto_grown_20260526143735233_sel_20260526_154138_315 | 135 | 6.44 | 17.66 | 42% | 51 | 0.60 |
| fill_0010_sel_20260512_111940_15 | 150 | 7.92 | 17.60 | 33% | 56 | 0.37 |
| auto_grown_20260421165403705_sel_20260604_081020_2 | 1192 | 4.55 | 17.50 | 70% | 115 | 0.25 |
| auto_grown_20260525085134735_sel_20260525_085936_34 | 125 | 4.48 | 17.42 | 80% | 48 | 0.55 |
| auto_grown_20260614185053940 | 552 | 1.42 | 17.25 | 92% | 36 | 0.98 |
| auto_trace_20260525092018344_sel_20260525_092438_38 | 153 | 6.29 | 17.22 | 47% | 57 | 0.93 |
| auto_grown_20260524200130489_sel_20260524_200712_16 | 234 | 4.31 | 17.08 | 72% | 83 | 0.62 |
| auto_grown_20260421002721090_region_000 | 326 | 2.95 | 17.07 | 78% | 107 | 0.90 |
| fill_0008_sel_20260512_104623_7 | 340 | 0.76 | 17.05 | 86% | 62 | 0.82 |
| auto_grown_20260421054221178_region_000 | 1044 | 2.96 | 17.05 | 88% | 101 | 0.20 |
| auto_grown_20260524200130489_sel_20260524_200712_14 | 300 | 3.03 | 17.00 | 89% | 83 | 0.64 |
| auto_grown_20260522204646014_sel_20260522_205109_9 | 406 | 0.21 | 16.74 | 95% | 72 | 0.88 |
| auto_grown_20260420204459802 | 486 | 6.10 | 16.51 | 48% | 114 | 0.56 |
| auto_grown_20260421140742657_sel_20260524_234618_21 | 254 | 6.02 | 16.25 | 50% | 93 | 0.56 |
| same_wrap002919_lasagna | 725 | 3.04 | 16.09 | 70% | 50 | 0.75 |
| auto_grown_20260526205436971_sel_20260526_212050_87 | 195 | 6.70 | 15.71 | 42% | 76 | 0.57 |
| auto_grown_20260522195517999_sel_20260522_200240_16 | 660 | 3.26 | 15.46 | 78% | 70 | 0.35 |
| auto_grown_20260526195309752_sel_20260526_210343_44 | 112 | 2.81 | 15.20 | 91% | 84 | 0.38 |
| same_wrap000360_lasagna | 726 | 3.48 | 15.15 | 88% | 30 | 0.55 |
| auto_grown_20260525085134735_sel_20260525_085936_61 | 360 | 1.74 | 14.86 | 93% | 47 | 0.56 |
| same_wrap001896_lasagna | 1490 | 2.56 | 14.71 | 94% | 31 | 0.65 |
| auto_grown_20260524195627415_sel_20260524_200047_30 | 480 | 5.66 | 14.62 | 56% | 89 | 0.77 |
| auto_grown_20260521133909764_sel_20260521_133956_2 | 562 | 2.85 | 14.50 | 80% | 55 | 0.71 |
| auto_grown_20260525071235545_sel_20260525_072130_19 | 165 | 4.75 | 14.30 | 78% | 60 | 0.78 |
| auto_grown_20260525093749704_sel_20260525_094056_14 | 425 | 3.36 | 14.26 | 77% | 59 | 0.84 |
| auto_grown_20260429220809522_sel_20260512_104236_38 | 1341 | 1.72 | 14.24 | 88% | 34 | 0.81 |
| auto_grown_20260526143735233_sel_20260526_154138_154 | 813 | 0.62 | 14.22 | 84% | 63 | 0.90 |
| auto_grown_20260521224733336_sel_20260521_225007_21 | 135 | 4.68 | 14.21 | 62% | 102 | 0.93 |
| auto_grown_20260526143735233_sel_20260526_154138_115 | 971 | 4.43 | 14.11 | 64% | 55 | 0.67 |
| auto_grown_20260521160538047_sel_20260521_160906_30 | 835 | 0.53 | 13.97 | 90% | 96 | 0.86 |
| auto_grown_20260525103648489_sel_20260525_104031_19 | 495 | 3.24 | 13.57 | 82% | 71 | 0.54 |
| auto_grown_20260524232311199_sel_20260524_232604_11 | 794 | 0.51 | 13.54 | 82% | 94 | 0.90 |
| auto_grown_20260521161559989_sel_20260521_162020_14 | 810 | 2.77 | 13.47 | 84% | 62 | 0.44 |
| auto_grown_20260526200530340_sel_20260526_211217_55 | 300 | 1.06 | 13.23 | 92% | 79 | 0.99 |
| same_wrap001130_lasagna | 495 | 2.05 | 13.02 | 93% | 47 | 0.58 |
| same_wrap001877_lasagna | 144 | 5.09 | 12.27 | 82% | 32 | 0.83 |
| auto_grown_20260526200530340_sel_20260526_211217_35 | 210 | 3.11 | 12.19 | 84% | 84 | 0.61 |
| auto_grown_20260526195309752_sel_20260526_210343_46 | 183 | 4.18 | 12.17 | 63% | 82 | 0.90 |
| auto_grown_20260521130313666_sel_20260521_130413_2 | 255 | 0.68 | 11.96 | 97% | 48 | 0.87 |
| auto_grown_20260521131254493_sel_20260521_131346_1 | 915 | 3.85 | 11.96 | 88% | 51 | 0.88 |
| auto_grown_20260521225553961_sel_20260521_225725_11 | 471 | 4.24 | 11.90 | 73% | 63 | 0.16 |
| 4424_david_masked | 2724 | 2.99 | 11.89 | 88% | 34 | 0.78 |
| auto_grown_20260526112529933_sel_20260526_113228_31 | 250 | 2.22 | 11.53 | 93% | 13 | 0.79 |
| low_1_sel_20260512_112253_7 | 140 | 2.72 | 11.16 | 86% | 51 | 1.00 |
| auto_grown_20260524200130489_sel_20260524_200712_12 | 375 | 5.03 | 11.06 | 60% | 91 | 0.23 |
| same_wrap001111_lasagna | 708 | 2.80 | 11.00 | 93% | 34 | 0.90 |
| same_wrap001894_lasagna | 1344 | 1.26 | 10.93 | 96% | 32 | 0.92 |
| auto_grown_20260521225553961_sel_20260521_225725_5 | 199 | 0.33 | 10.89 | 90% | 59 | 0.98 |
| auto_grown_20260416100730699 | 714 | 1.09 | 10.75 | 86% | 122 | 0.55 |
| auto_grown_20260420154248840_region_000 | 8 | 3.95 | 10.60 | 75% | 31 | 1.00 |
| 1001_fill_sel_20260512_104442_13 | 314 | 2.54 | 10.43 | 89% | 42 | 0.90 |
| auto_grown_20260526104703844_flatboi_sel_20260526_113725_22 | 563 | 0.48 | 10.24 | 96% | 16 | 1.00 |
| same_wrap002962_lasagna | 2111 | 1.16 | 9.75 | 97% | 63 | 0.99 |
| auto_grown_20260525083947023_sel_20260525_090659_7 | 4 | 6.25 | 9.66 | 50% | 65 | 0.75 |
| same_wrap002462_lasagna | 761 | 0.53 | 9.65 | 99% | 31 | 1.00 |
| 1000_fill_sel_20260512_105755_24 | 289 | 4.24 | 9.63 | 91% | 43 | 0.58 |
| auto_grown_20260526195309752_sel_20260526_210343_56 | 18 | 6.06 | 8.91 | 44% | 94 | 0.22 |
| auto_grown_20260524232311199_sel_20260524_232604_9 | 244 | 3.95 | 8.87 | 82% | 93 | 0.47 |
| same_wrap001879_lasagna | 97 | 0.61 | 8.85 | 76% | 20 | 1.00 |
| auto_grown_20260526123645345_sel_20260526_124600_24 | 490 | 2.89 | 8.73 | 88% | 45 | 0.79 |
| auto_trace_20260526151328050_sel_20260526_155150_31 | 246 | 0.34 | 8.72 | 91% | 56 | 1.00 |
| auto_grown_20260522194733886_sel_20260522_195015_6 | 462 | 3.18 | 8.34 | 82% | 98 | 0.27 |
| auto_grown_20260421140742657_sel_20260524_234618_4 | 45 | 3.71 | 8.25 | 80% | 109 | 0.16 |
| auto_grown_20260527134144893_sel_20260527_150051_50 | 210 | 0.21 | 8.10 | 95% | 19 | 1.00 |
| same_wrap001890_lasagna | 1461 | 1.33 | 7.93 | 98% | 32 | 0.89 |
| auto_grown_20260526123645345_sel_20260526_124600_9 | 225 | 5.63 | 7.92 | 64% | 46 | 0.67 |
| auto_grown_20260526123645345_sel_20260526_124600_23 | 255 | 3.01 | 7.92 | 88% | 44 | 0.95 |
| auto_grown_20260524200130489_sel_20260524_200712_2 | 81 | 0.14 | 7.36 | 96% | 79 | 0.98 |
| auto_grown_20260527055752931_sel_20260527_060635_25 | 669 | 0.29 | 7.12 | 98% | 73 | 0.88 |
| same_wrap002468_lasagna | 1336 | 0.85 | 5.64 | 99% | 38 | 1.00 |
| auto_grown_20260526104703844_flatboi_sel_20260526_113725_15 | 535 | 0.37 | 4.61 | 100% | 18 | 1.00 |
| auto_grown_20260526143735233_sel_20260526_154138_146 | 214 | 0.66 | 4.31 | 99% | 54 | 0.99 |
| auto_grown_20260526143735233_sel_20260526_154138_41 | 630 | 0.19 | 3.70 | 100% | 65 | 1.00 |
| auto_grown_20260525091409852_sel_20260525_092057_6 | 895 | 0.27 | 3.44 | 100% | 55 | 1.00 |
| same_wrap001875_lasagna | 1104 | 0.49 | 3.40 | 100% | 36 | 1.00 |
| auto_grown_20260416031743018 | 114 | 0.80 | 2.57 | 100% | 54 | 1.00 |
| auto_grown_20260524201742979_sel_20260524_202046_25 | 441 | 0.11 | 2.45 | 100% | 79 | 1.00 |
| fill_0007_sel_20260512_111459_33 | 233 | 0.15 | 2.27 | 100% | 54 | 1.00 |
| auto_grown_20260526143735233_sel_20260526_154138_7 | 375 | 0.21 | 1.94 | 100% | 55 | 1.00 |
| auto_grown_20260526200530340_sel_20260526_211217_54 | 410 | 0.14 | 0.97 | 100% | 79 | 1.00 |
| auto_grown_20260524200130489_sel_20260524_200712_7 | 360 | 0.09 | 0.77 | 100% | 79 | 1.00 |

## Intrinsic checks

*Ground-truth-free checks of the winding family itself, along rays from the umbilicus: winding ids must appear in increasing radial order (violations are crossings), and consecutive-winding gaps should be near the run's pitch (collapsed: near zero; inflated: well past it). Bins span the meshes' actual z and theta extent, not --z-range, so offender locations may fall slightly outside the declared window.*

| check | value |
|---|---|
| median pitch (vox) | 19.10 |
| bins checked | 46120 |
| violations (crossings) | 138 (0.30%) |
| collapsed gaps | 194 (0.42%) |
| inflated gaps | 682 (1.48%) |

### Worst offenders

| kind | gap | inner wind | z | theta |
|---|---|---|---|---|
| violation | -130.03 | 38 | 10575..10610 | -2.49..-2.36 |
| violation | -96.67 | 91 | 10575..10610 | -2.75..-2.62 |
| violation | -35.30 | 53 | 10890..10925 | -2.09..-1.96 |
| violation | -33.94 | 52 | 10575..10610 | -2.62..-2.49 |
| violation | -30.01 | 112 | 10890..10925 | -2.88..-2.75 |
| violation | -27.78 | 73 | 10575..10610 | -2.75..-2.62 |
| violation | -26.43 | 82 | 10575..10610 | -2.75..-2.62 |
| violation | -25.75 | 65 | 10575..10610 | 1.44..1.57 |
| violation | -25.42 | 119 | 10890..10925 | 0.00..0.13 |
| violation | -24.97 | 96 | 10575..10610 | -1.83..-1.70 |
