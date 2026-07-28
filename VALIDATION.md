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
published aggregates, the CLI glue, the intrinsic checks, and the split,
audit and leakage code. **Result: 53/53 detected.**

Two candidate mutations were deliberately left out of the list rather than
counted, because the suite cannot kill them and a mutation that cannot be
killed inflates the score without proving anything: dropping one redundant
`resolve` call inside the geometry-hash merge is an equivalent mutant in
every reachable configuration, and disabling the split's self-check cannot
change any output, since the merge makes a poisoned split unreachable by
construction. Both are noted in `scripts/mutation_check.py`.

Sensitivity floors, so a reader can ask "how small a defect would this have
missed?" (`scripts/sensitivity_floor.py`, measured on the synthetic fixture,
pitch 10 vox): a smooth radial drift is caught from **1.1 vox**; a sheet swap
from a band **0.05 rad wide, 2% of the patch's angular span**; a collapsed
inter-winding gap from **0.5 vox of displacement** by the held-out distance;
an alternating row tilt from **0.35 vox**. The intrinsic *collapsed* label is
a deliberate classification threshold and only fires once 80% of the gap is
gone, which is why the distance metric, not the label, is what catches small
collapses.

Honest notes, because this is where the value is. The first round (8
mutations) scored 7/8; the survivor exposed a fixture too benign to need the
KD exactness bound, and the adversarial mesh case above was added. On
2026-07-28 an independent test-quality review ran eight counter-mutations of
its own and **all eight survived** the then-current suite (dead normal metric,
published aggregates replaced by constants, inverted CLI `--z-range`, widened
epsilon guard, dead inflated-gap indicator, ignored umbilicus). Each got a
dedicated test and a mutation entry. A second review round then attacked the
fixes with **fifteen fresh counter-mutations, of which thirteen survived**;
the dominant pattern was fixtures pinned at a null point (weighted equals
unweighted, min equals max, one input equals many, passed value equals its
default). Each survivor now has a test built to discriminate: asymmetric
patch sizes, a known displacement delta bracketed from both sides, a
multi-input leakage reference recomputed independently inside the test, and a
reference implementation of the whole split draw. Two of the new tests were
themselves first too symmetric to discriminate and were caught by the
extended audit: the audit polices the tests, including the new ones. A third
round then attacked *those* fixes with **55 counter-mutations, of which 42
survived**, concentrated on the newest code (the rewritten sheet rule and the
unseen block had one mutation entry between them). The pattern was the same
every time: fixtures pinned at a point where two different definitions agree
(weighted equals unweighted, min equals max, one input equals many, a passed
value equals its default, x equals minus z). The suite now discriminates at
each of those points, and the mutation list covers the new code.

Those rounds caught real defects, all fixed and tested: villa's
`umbilicus.json` `control_points` structure; the shared-seam column of
combined surfaces; a sheet-consistency rule that rated a heavily switched
patch 0.986 (section 6); a split that byte-identical twins under unrelated
names could deadlock; an estimator mismatch that invented an "inversion" in
the published table; a report line stating a false reason for an empty
aggregate; and a block scheme that held out 11% of families when 20% was
asked.

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

## 4b. The blind spot a distance metric cannot cover, measured on real data

A winding family fills space at the pitch: inside the modelled region every
point is within half a pitch of *some* sheet. A surface that is one full
winding out of place is therefore still close to something, and any measure
that reduces to "how far is the evidence from the nearest surface" cannot see
it. That is not a corner case; it is the characteristic failure of scroll
fitting.

`scripts/pitch_blindness.py` turns that into a control with a known answer,
on the real pipeline: displace the held-out evidence radially around the true
umbilicus by a measured multiple of the run's own pitch (20.31 vox here) and
rescore against the real fitted surfaces.

| displacement | dist p50 | dist p99 | within tau | matched winding |
|---|---|---|---|---|
| none | 3.83 vox | 16.79 vox | 72.9% | reference |
| half a pitch (10.2 vox) | 4.01 | 16.91 | 71.1% | +0.0 |
| one pitch (20.3 vox) | 3.93 | 17.01 | 72.2% | **+1.0** |
| two pitches (40.6 vox) | 4.06 | 17.12 | 70.7% | **+2.0** |

Moving every held-out point by **two full winding pitches, 41 voxels**, moves
the median distance by 0.23 vox and the within-tau fraction by 2.2 points:
nothing. The winding the evidence is matched to moves by exactly two. A
random-direction probe confirms the mechanism directly: displacing points by
2, 4, 8 or 16 vox in arbitrary directions leaves the median distance to the
nearest surface between 5.99 and 6.11 vox. The distance saturates at the
geometry's own resolution.

This is why the suite reports winding identity alongside distance, and why it
computes it from the surfaces themselves rather than through the fit's
transform. It is also the honest limit of the distance columns everywhere
else in this document: they detect regions the fit did not model at all
(large distances) and sub-pitch misplacement, and nothing in between.

## 5. Leakage control: hash audit plus geometric measurement

`parrhesia split` groups patches into families first (overlapping `*_sel_*`
selections, `_region_`/`_flatboi` variants and `same_wrap` producers are
near-duplicate geometry of one parent; a family never straddles the split) and
writes `split_manifest.json` with the seed, every assignment, the grouping and
two SHA-256 hashes per patch (full content, and geometry-only so a metadata
rewrite cannot dodge the audit). `parrhesia score --manifest --fit-inputs`
refuses to score (exit 3) when a held-out patch is found among the fit inputs
(by geometry hash, recursively, renamed copies included) and refuses (exit 4)
when the scored patches are not the manifest's held-out side. Covered end to
end by the CLI tests.

**A hash audit is not a physical guarantee, so it is not the claim.** On real
Paris 4 data, verified patches overlap heavily: our own adversarial review
measured that with the v1 name-level split, 54.8% of the "held-out" area of
the demo window lies within 0.5 vox of some fit-side input patch (66 of its 98
held-out patches have a `_sel_` sibling of the same parent on the fit side).
That channel is invisible to any name- or hash-level check. Since v0.2,
every run scored with `--fit-inputs` therefore measures leakage geometrically:
distance of every scored point to the union of the fit's *actual* input
surfaces, reported as a profile, and an **unseen** aggregate over points
farther than 2 vox from every input; an input patch that fails to load is a
hard refusal (exit 5), because silently skipping it would flatter the unseen
numbers. The demonstration below quotes the unseen numbers, not the naive
ones.

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

For the dense run, parrhesia's leakage audit measures that 54.8% of the sealed points
area lies within 0.5 vox of some fit-side input surface (overlapping patch
selections; section 5), so the honest column for it is the **unseen** one:
the 15,437 points farther than 2 vox from every input the fit consumed. The
sparse run consumed no patches, so all of its evidence is unseen by
construction.

Both columns are scored on **exactly the same 15,437 points**: the sealed
evidence that lies more than 2 vox from every patch the dense run consumed,
so neither run could have seen it. (Scoring each run on its own unseen set
instead would compare two different point sets and flatter whichever run saw
more; the sparse run saw none.) 15,457 points clear the 2 vox threshold in
total; the aggregate uses 15,437 of them, because 25 patches contribute fewer
than the eight unseen points required to enter a per-patch average. The report
prints both counts.

| measure | dense run | sparse run (no patches) |
|---|---|---|
| villa satisfaction, patches | 5/389 satisfied (1.3%) | **0/0 (empty denominator)** |
| villa satisfaction, unattached pcl points | 54.8% | 49.9% |
| parrhesia surface distance p50 | 4.21 vox | 5.01 vox |
| within tau = 6 vox | 67.6% | 60.1% |
| parrhesia surface distance p90 | 9.6 vox | **53.9 vox** |
| parrhesia surface distance p99 / max | 17.7 / 23.9 vox | **246.0 / 330.0 vox** |
| sheet consistency (mean) | 0.40 | 0.33 |
| normal agreement p90 (pooled over points) | 49.9 deg | 48.9 deg |

Which of those differences are real, and which are the luck of the draw?
`scripts/bootstrap_ci.py --unseen` resamples the 78 patches that carry unseen
points (20,000 paired draws) and answers per metric:

| metric (point-weighted mean of per-patch values) | gap, dense - sparse | 95% interval |
|---|---|---|
| surface distance p50 | -18.5 vox | [-43.6, -2.3] |
| surface distance p99 | -24.6 vox | [-53.9, -3.1] |
| within tau | +0.074 | [-0.007, 0.165] (spans zero) |
| sheet consistency | +0.065 | [-0.058, 0.173] (spans zero) |
| normal agreement p90 | -1.8 deg | [-7.7, 3.7] (spans zero) |

So on this pair, the discriminating measure is the **distance distribution's
tail**, not sheet identity: the sheet-consistency and within-tau gaps point
the right way but are inside resampling noise, and we say so rather than
quoting them as evidence. A suite that could not tell those cases apart would
be worth less than one that can.

Reading. Both runs are deliberately cheap (1,500 steps, coarse flow field,
8 GB VRAM), and on the dense run the two instruments agree: a weak fit,
judged weak by both. The sparse run is the regime the project explicitly
wants to support (fits from minimal verified inputs; villa #1237 was closed
as won't-fix for exactly that reason). There, patch satisfaction has an empty
denominator: nothing to report, on a run that is measurably worse.

What a cursory check would see: almost nothing. The median held-out distance
moves from 4.21 to 5.01 vox, less than one voxel, on a fit that has lost
whole regions of the window. What the full distribution shows: p90 goes from
9.6 to 53.9 vox and p99 from 17.7 to 246 vox, twelve winding pitches, which
is what "this part of the scroll is not modelled at all" looks like in
numbers. Sheet identity moves the same way (0.40 to 0.33) but not far enough
to clear the resampling interval on this evidence.

That is the argument, and it survives its own scrutiny: an evaluation
reporting one summary number would have called these two runs comparable;
satisfaction could not have called them anything at all.

Corrections made along the way, stated plainly, because they are the method
working:

- The previously published table compared against a sparse companion
  (sparse1) that had accidentally kept villa's fiber input enabled (257
  collections, 6,397 points), found by an independent claims audit of the run
  logs. The sparse run above (sparse2) has patches and fibers off; the one
  changed switch is real this time.
- An earlier version of this table computed the dense numbers on all 49,458
  sealed points, 54.8% of which the fit had effectively seen through
  overlapping input selections (found by our own adversarial review, and now
  measured by the tool itself on every run scored with the fit's inputs).
  The dense column above is therefore restricted to unseen evidence.
- That earlier table also compared normal agreement across two different
  estimators: a point-weighted mean of per-patch p90 on one side, a pooled
  p90 on the other. The "inversion" it reported was an artefact of that
  mismatch, not a property of the runs. Both aggregates now pool over points,
  like the distance percentiles, and the row above is homogeneous.
- Between those two and this one, a rewritten sheet-consistency rule merged
  fragments whose median winding coordinate was close. On one real patch that
  chained 87 fragments spread over 4.6 turns into a single "continuous
  sheet" (0.986) while 18% of that patch's own grid adjacencies were cut, and
  the rest of the report scored it 0.399. Worse, the entire published gain of
  that version came from that one patch. The rule was replaced by the
  drift-aware one described in DESIGN.md (a hole is bridged only when the u
  difference matches the patch's own drift across the gap), which rates that
  patch 0.447 with a winning group spanning 0.93 turns instead of 4.59. The
  numbers landed back within 0.01 of where the first, cruder definition had
  them, this time for a reason that survives inspection.

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
uv run pytest -q                      # 86 tests: engine, defect matrix, e2e CLI
uv run python scripts/mutation_check.py   # 53/53 injected bugs must be detected
uv run python scripts/real_data_smoke.py <verified_patches_dir> 500
uv run python scripts/real_overlap_check.py <verified_patches_dir> 150
```
