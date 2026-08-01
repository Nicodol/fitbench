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
- **Where "exact" stops being true, measured.** An adversarial review of this
  version built an independent reference (minimum over the three closed edges
  plus the in-plane projection) and found one family the primitive gets wrong:
  a face whose *first two* vertices coincide (`a == b`). Reproduced here on
  20,000 random cases per family: generic, `a == c` and `b == c` faces agree to
  1e-15, while `a == b` over-estimates on 47.9% of queries and exactly collinear
  faces on 1.9%. The error is one-sided, always an over-estimate, so it can only
  make a fit look worse. It does not touch any number in this document: across
  everything scored here, 7,513,224 faces (both demo runs' surfaces, the 98
  held-out patches, the 541 fit inputs), there are **zero** faces with any
  duplicated vertex pair and zero exactly collinear faces. A quad mesh does not
  produce them unless a grid cell is pinched. Worth fixing, not fixed here.
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

**What 53/53 does and does not mean, stated once so it is not read as more
than it is.** That list is a regression harness: it pins bugs we already know
how to describe, and it is what keeps them from coming back. It is not a claim
of exhaustiveness, and no mutation score is. Every independent review round run
against this suite has found fresh survivors: across the three counter-mutation
campaigns documented below, the reviewers wrote 78 counter-mutations and 63
survived on first contact (8 of 8, then 13 of 15, then 42 of 55); each survivor
has since been given a test built to discriminate it. (An earlier revision of
this paragraph quoted a larger aggregate that no shipped artifact reproduces;
the per-round counts below are the ones this repo can back.) The survivors
concentrate outside the numerical core, and the honest summary of where this
suite is strong and weak is:

- *Audited hard, and repeatedly*: the distance engine (the brute-force,
  independent-sampling and degenerate-triangle checks kill everything injected
  into the closest-point code), the aggregates in `metrics.py` (the tests
  recompute values from the per-point payload instead of comparing to
  constants), the continuous winding coordinate and the sheet topology, and the
  split protocol.
- *Thin*: `report.py`, whose Markdown rendering is asserted mostly by substring
  presence; the CLI's default option values, which every test passes
  explicitly; the z axis of the intrinsic localization (theta is checked, z is
  not); several intrinsic thresholds that no fixture straddles; and the
  null control on the inflated-gap indicator.

Those are gaps in test coverage, not known wrong values: the published numbers
in sections 4 to 6 were re-derived from the raw artifacts, the shipped
`report.md` files were checked field by field against their `report.json`, and
a clean synthetic family does report zero violations, zero collapsed and zero
inflated gaps. Closing the coverage gaps is worth doing and is not done.

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
  The remaining pairs are not an engine error, and the reason is villa's own
  definition: `overlapping.json` records that two surfaces touch *somewhere*,
  not that they trace the same sheet throughout. Both of its geometric
  producers test at 2 voxels (`vc_seg_add_overlap.cpp`, and `QuadSurface.cpp`'s
  `overlap()`, the latter on a random sample of points), and one of them also
  lists the segment an expansion grew from with no geometric test at all
  (`vc_grow_seg_from_seed.cpp`). Measured on the same 150 pairs: 23 of the 29
  pairs whose median exceeds 5 vox do touch, at a minimum distance of 0.00 vox,
  with 1.5% to 49% of their points within 2 vox (median 22%), and diverge
  elsewhere, so their per-pair median describes a mixed population. Per-pair medians reach 1,998
  vox at the extreme. An earlier version of this line explained the tail by
  neighbouring windings instead; villa's 2 voxel tolerance rules that out, since
  it cannot pair surfaces a winding pitch apart. See DESIGN.md.

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
nothing. The winding the evidence is matched to moves by exactly two. Every
number in that table comes out of `scripts/pitch_blindness.py` on the demo run.
(An earlier version of this section also quoted a random-direction probe. The
shipped script only displaces radially, so that claim had no artifact behind it
and is withdrawn rather than restated; the radial control is the one with a
known answer, and it is the one that makes the point.)

Scope of this result, stated carefully, because it is easy to overstate.
It says that a **distance-only** evaluation cannot judge a scroll fit,
including a naive version of this suite: it is the reason the suite carries
winding identity next to distance, and the honest limit of every distance
column in this document, which sees regions a fit did not model at all and
sub-pitch misplacement, and nothing in between. It is **not** a criticism of
villa's satisfaction metrics, which check a spiral-space tolerance of 0.45
winding pitches and would also catch a whole-pitch error. The difference
between the two remains the one stated in DESIGN.md: satisfaction checks
identity through the fit's own transform and only on the fit's own inputs,
while this suite checks it on withheld evidence, from the surfaces
themselves.

## 5. Leakage control: hash audit plus geometric measurement

`spiralcheck split` groups patches into families first (overlapping `*_sel_*`
selections, `_region_`/`_flatboi` variants and `same_wrap` producers are
near-duplicate geometry of one parent; a family never straddles the split) and
writes `split_manifest.json` with the seed, every assignment, the grouping and
two SHA-256 hashes per patch (full content, and geometry-only so a metadata
rewrite cannot dodge the audit). `spiralcheck score --manifest --fit-inputs`
refuses to score (exit 3) when a held-out patch is found among the fit inputs
(by geometry hash, recursively, renamed copies included) and refuses (exit 4)
when the scored patches are not the manifest's held-out side. Covered end to
end by the CLI tests.

**A hash audit is not a physical guarantee, so it is not the claim.** On real
Paris 4 data, verified patches overlap heavily: our own adversarial review
measured that with the v1 name-level split, 54.8% of the "held-out" *points* of
the demo window lie within 0.5 vox of some fit-side input patch (66 of its 98
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

For the dense run, spiralcheck's leakage audit measures that 54.8% of the sealed
points lie within 0.5 vox of some fit-side input surface (overlapping patch
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
prints the aggregate's count and the used/excluded patch split (`69 / 25`); the
15,457 is the sum of the per-patch `n_points_unseen` fields, which the report
carries per patch rather than as a total.

| measure | dense run | sparse run (no patches) |
|---|---|---|
| villa satisfaction, patches | 5/389 satisfied (1.3%) | **0/0 (empty denominator)** |
| spiralcheck surface distance p50 | 4.21 vox | 5.01 vox |
| within tau = 6 vox | 67.6% | 60.1% |
| spiralcheck surface distance p90 | 9.6 vox | **53.9 vox** |
| spiralcheck surface distance p99 / max | 17.7 / 23.9 vox | **246.0 / 330.0 vox** |
| sheet consistency (mean) | 0.40 | 0.33 |
| normal agreement p90 (pooled over points) | 49.9 deg | 48.9 deg |

Every spiralcheck row above is the same 15,437 points on both sides. villa's
other satisfaction channel is not, and is therefore quoted separately rather
than as a row: satisfied unattached-pcl points are 211/385 (54.8%) for the
dense run and 336/674 (49.9%) for the sparse one. Those denominators differ
because attaching a point collection to a patch removes it from the unattached
set, so the dense run's own inputs change which points that channel scores.
Two different populations cannot be compared as a gap. (The 54.8% there is a
coincidence of rounding with the 54.8% leakage figure above, which is a
different quantity entirely: 211/385 of villa's pcl points satisfied, against
0.5485 of our sealed points sitting within half a voxel of a fit input.)

Which of those differences are real, and which are the luck of the draw?
`scripts/bootstrap_ci.py --unseen` resamples the 78 patches that carry unseen
points (20,000 paired draws) and answers per metric. **Read the levels before
the gaps**: this table aggregates differently from the one above. It is a
point-weighted mean of per-patch values, so for a percentile metric it is the
mean of per-patch percentiles, not the pooled percentile. The two answer
different questions and do not have to agree; the script prints the same
warning.

| metric (point-weighted mean of per-patch values) | dense | sparse | gap, dense - sparse | 95% interval |
|---|---|---|---|---|
| surface distance p50 | 4.46 vox | 22.91 vox | -18.5 vox | [-43.6, -2.3] |
| surface distance p99 | 15.42 vox | 40.00 vox | -24.6 vox | [-53.9, -3.1] |
| within tau | 0.675 | 0.601 | +0.074 | [-0.007, 0.165] (spans zero) |
| sheet consistency | 0.396 | 0.332 | +0.065 | [-0.058, 0.173] (spans zero) |
| normal agreement p90 | 38.7 deg | 40.5 deg | -1.8 deg | [-7.7, 3.7] (spans zero) |

The sparse column is where the two aggregations part company: a per-patch mean
of 22.91 vox against a pooled median of 5.01, because a handful of patches the
sparse fit missed entirely carry very large per-patch medians while most points
still sit close to some surface. That is the same fact the pooled p90 and p99
report, seen through a different lens.

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

One more thing this pair says, and it is not flattering to half of this suite.
The intrinsic checks, which consume no ground truth, rank the two runs the
other way round: the sparse fit shows 10 radial-monotonicity violations against
the dense fit's 48, 2 inflated inter-winding gaps against 67, and a slightly
higher valid-vertex fraction on every winding the two runs have in common (the
sparse run emits 106 windings against the dense run's 120, so 14 have no
counterpart; all four numbers are in
[`examples/compare_smoke8_vs_sparse2.md`](examples/compare_smoke8_vs_sparse2.md)).
That is not a contradiction, it is the limit of a check with no external
reference: a surface family can be smooth, regular and self-consistent while
sitting in the wrong place, and a fit with fewer constraints has fewer
opportunities to contradict itself. The intrinsic checks earn their keep where
no ground truth exists at all, including on a production fit trained on 100% of
the patches, and they localize defects in (z, theta). They do not rank fits for
accuracy. On this pair, held-out evidence is what does.

Two robustness checks on the table itself, because both are objections a
reader of villa's code will raise.

*The spliced variant.* `fit_spiral` exports each winding twice, `wNNN` and
`wNNN_spliced`, and the spliced one has the fit's own input patches rasterized
into it verbatim (`spiral_helpers.py`, `_build_spliced_overlay`). The reports
above use the spliced variant, so evidence lying near an input would be scored
partly against a copy of that input. Rescored with `--variant plain`, the dense
run's unseen p90, p99, max and normal agreement are unchanged to four decimals,
unseen p50 moves by 0.004 vox and within-tau by 0.0001; the naive full-set
numbers move by 0.05 to 0.26 vox. The sparse run has nothing to splice, so its
two variants are bit-identical. The unseen aggregate is immune because it
already excludes every point within 2 vox of an input, which is exactly where
the splice lives.

*Sheet consistency has a known upward bias here.* An adversarial review of this
version found that the drift-aware merge bridges a genuine full-turn switch when
a patch has a wide hole and an uneven drift, because the rule predicts u across
the gap from a single drift estimate: the error grows with the hole width, and
past half a turn the switch is indistinguishable from a gap. On the demo patches
that arithmetic allows up to about 1.2 turns of uncertainty against a 0.5-turn
tolerance. The bias is one-sided and inflates the score. Both the working case
and the failing one are now pinned in `tests/test_sheet_contract.py` (the latter
as a strict `xfail`), and DESIGN.md states the limit. It is left unfixed on
purpose: this metric has been rewritten three times, the contract exists so that
the next change argues against a table instead of against the previous code, and
the number it produces here is one the bootstrap already declines to call.

*What satisfaction could and could not say.* Patch satisfaction had an empty
denominator on the sparse run. Its unattached-pcl channel did not: it reported
54.8% against 49.9%, in the same direction as our conclusion, on two different
populations. So the honest claim is not that satisfaction was blind here, it is
that its patch channel was silent and its pcl channel was not comparable
between the two runs.

That is the argument, and it survives its own scrutiny: an evaluation reporting
one summary number would have called these two runs comparable, and patch
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

The machine-readable reports behind both tables ship too, so every number above
can be rechecked, and the bootstrap re-run, from this repository alone without
the 1.1 GB of run folders:
[`examples/real_run_smoke8_report.json`](examples/real_run_smoke8_report.json)
and [`examples/real_run_sparse2_report.json`](examples/real_run_sparse2_report.json).
Only the `meta` paths were replaced by placeholders; every measured field is
untouched.

```bash
uv run python scripts/bootstrap_ci.py \
    examples/real_run_smoke8_report.json examples/real_run_sparse2_report.json --unseen
```
The villa satisfaction rows are verbatim log excerpts:
[`examples/real_run_smoke8_villa_metrics.txt`](examples/real_run_smoke8_villa_metrics.txt),
[`examples/real_run_sparse2_villa_metrics.txt`](examples/real_run_sparse2_villa_metrics.txt).

## Reproduce

```bash
uv sync --group dev
uv run pytest -q                      # 104 tests + 1 strict xfail (a frozen known limit)
uv run python scripts/mutation_check.py   # 53/53 injected bugs must be detected
uv run python scripts/real_data_smoke.py <verified_patches_dir> 500
uv run python scripts/real_overlap_check.py <verified_patches_dir> 150
```
