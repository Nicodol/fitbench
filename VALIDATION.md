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

Section 9 plants five of these defects, plus the null control, in a **real**
fit's output surfaces instead, where the geometry is not ideal and not every
answer comes out the same — in particular the "others stay silent" property
above does not survive the trip.

## 3. The tests are themselves audited by mutation

`scripts/mutation_check.py` (a CI job on Linux, Windows and macOS) injects
deliberate bugs one at a time and requires the suite to fail on each, then
pass unmutated. The list covers the geometry engine, the metrics and their
published aggregates, the CLI glue, the intrinsic checks, and the split,
audit and leakage code. **Result: 54/54 detected.**

Two candidate mutations were deliberately left out of the list rather than
counted, because the suite cannot kill them and a mutation that cannot be
killed inflates the score without proving anything: dropping one redundant
`resolve` call inside the geometry-hash merge is an equivalent mutant in
every reachable configuration, and disabling the split's self-check cannot
change any output, since the merge makes a poisoned split unreachable by
construction. Both are noted in `scripts/mutation_check.py`.

**What 54/54 does and does not mean, stated once so it is not read as more
than it is.** That list is a regression harness: it pins bugs we already know
how to describe, and it is what keeps them from coming back. It is not a claim
of exhaustiveness, and no mutation score is. Every independent review round run
against this suite has found fresh survivors: across the three counter-mutation
campaigns documented below, the review rounds wrote 78 counter-mutations and 63
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
  presence (the winding-agreement cell is now pinned end to end, the rest is
  not); `compare`, which silently drops a metric that is null on either side
  instead of saying so; the CLI's default option values, which every test
  passes explicitly; the z axis of the intrinsic localization (theta is
  checked, z is not); several intrinsic thresholds that no fixture straddles;
  and the null control on the inflated-gap indicator.

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

**Read this against section 9 before quoting it.** The experiment above moves
the *evidence* inside an intact family, which tiles space at the pitch exactly,
so distance barely moves. Section 9 does the mirror experiment — it moves the
*fit* by one measured pitch over a z band — and there the median distance goes
from 1.74 to 3.70 vox, because a real family's own gap is irregular and the
displaced family is not a relabelling of itself. "Distance cannot see a whole
pitch" holds for the direction measured here; in the other direction it
under-reports by about tenfold rather than being blind, and section 9 is the
number to quote for that case.

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
(recommended for new fits: 4,922 patches, 1,133 held out, 3,789 on the fit
side, 1,532 families) and the original
[`examples/PHercParis4_v1_split_manifest.json`](examples/PHercParis4_v1_split_manifest.json)
(name-level, seed 20260731, 4,922 patches, 985 held out): the demo runs below
consumed the v1 fit side, and their leakage is neutralized by the geometric
audit rather than by re-fitting.

## 6. Demonstration on two real fits (dense vs sparse inputs)

Two real villa `fit_spiral` runs on PHerc. Paris 4 (z 10600-10900, consumer
RTX 3060 Ti, identical settings and step budget), differing **in one input
switch** (`use_verified_patches`), both scored against the same 94 sealed
patches (49,458 quad centers, scoring restricted to the fitted window). (On
the exact villa `scripts/spiral` state of these local runs, see the commit
attribution note in section 8: the hash our notes first recorded fails a
config-key consistency check, and section 8's cross-platform twin bounds
whatever code-state delta remains at 0.26% relative.)

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

One input channel is shared rather than withheld, measured here so the claim
above stays exact. Both runs also consume the same three winding-annotation
point collections, 719 points made in VC3D. **An earlier version of this
paragraph called all 719 "manually clicked", on the strength of
human-cadence timestamps and the annotator-tool collection names. That is
true of 99 of them and wrong about the other 620**, and section 10 measures
what the difference is worth: the 98 relative-winding points (plus one
absolute anchor) carry a distinct `creation_time` per point, 0.65 to 1.4 s
apart, which is a person clicking; the 620 `same_wrapNNN` points carry one
identical timestamp per collection, because VC3D's `SameWrapAnnotationTool`
writes a whole collection in a single commit. It builds one by
Otsu-thresholding the displayed slice, skeletonising it, snapping two
human-chosen endpoints to the skeleton, running Dijkstra between them along
skeleton pixels, and sampling the resulting path at a fixed spacing
(`SameWrapAnnotationTool.cpp`, `generatePreview`). So those points are traced
by machine along the sheet *in the scan*, under human supervision, rather
than clicked one by one. Those
annotations lie on the papyrus sheet, so some run along surfaces the sealed
patches cover: of the 51,679 sealed vertices in the window, 6 (0.01%) lie
within 2 vox of an annotation point, 70 (0.14%) within tau = 6, and 385
(0.74%) within 20. By construction the channel is identical for the two runs,
so it cannot favor either side of the comparison, and it is invisible to the
unseen filter, which measures distance to input *patches* only (DESIGN.md
names that limit). "Points neither run could have seen" therefore holds
exactly for the patch channel, and for the annotation channel to within the
fractions above. The derived collection that would genuinely break this
(`patch-overlap-pcls.json`, built from patch overlaps upstream) is consumed
by none of the runs scored in this document, and should stay out of any
future one.

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
warning. The populations differ too, by a hair: the aggregate above only
admits patches with at least 8 unseen points (69 patches, 15,437 points),
while the bootstrap resamples every patch carrying unseen points (78 patches,
15,457). That is why within-tau reads 67.6% above and 0.675 here (0.675714 vs
0.675422 unrounded, re-derived from the shipped reports): same fraction, two
denominators, both correct.

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

## 7. Second scroll case study: a community parity fit of PHerc1218

Honest scope first: this is a **feasibility case study**, not a held-out
evaluation. PHerc1218 has no human-verified patches yet, and the review round
summarized below is what established that the machine evidence available
cannot play that role.

The run. [vesuvius-sheet-tools](https://github.com/IyanDopico/vesuvius-sheet-tools)
ships a pinned reproduction of its published PHerc1218 window fit
(`reproduce/spiral_fit_window.py`: the IyanDopico/villa fork at `61bd95c`
carrying the #1207 fix, input pack at `3fd238c`, z 9700-10500, 30k steps,
seed 1, PCL-only config). Wrapped in our session guardrails on a Kaggle T4 it
completed in 24 minutes and **passes every criterion of that repository's
reproduction gate**: `fitting 1 patches`; seed patch 100% satisfied (gate
>= 97); relative windings 972/1,002 = 97.0% (>= 94); same windings
630/644 = 97.8% (>= 91); and the fitted median pitch, measured by this
suite's intrinsic check, 20.17 grid vox = 10.09 L1 vox, inside their
10.1 +/- 0.5 band, independently recovering the 172.8 um physical pitch they
measured. The pack, runner and gate are IyanDopico's work with pscamillo's
parity fixes (the pinned commit *is* the `unattached_pcl_num_per_step` fix).

What this demonstrates for spiralcheck: the loader read another producer's
pack as-is (patches with no mask and no winding grid), scoring ran unmodified
and CPU-only, re-scoring is bit-identical, and the intrinsic block recovered
a physically confirmed pitch on a scroll this suite had never seen. Reports:
[`examples/real_run_pherc1218_report.json`](examples/real_run_pherc1218_report.json)
(+ `.md`).

What it deliberately does not claim. The only candidate evidence was
`seed-z4704`, the sole `main`-pack patch absent from the pinned pack whose z
extent intersects the window. Scored against it: 21 unseen points, distance
p50 4.85 / p90 7.60 / max 10.72 vox, within tau 71.4%, sheet consistency
0.238, leakage-to-input-patches 0.0%. Our own review round then established
that this cannot be read as held-out evaluation: the patch is
machine-synthesized from the same stitched instance labels as the fit's
constraints, from the very instance (global id 206505) whose next slab up is
the fit's anchor patch (their boundary vertices touch at 0.83 vox); the fit
consumed seven relative-winding constraints on that instance; and the 0.0%
leakage figure is exactly the audit's documented blind spot (DESIGN.md): it
certifies distance to declared input patches, nothing more. 21 non-independent
machine points against a reference whose own down-roll error is
uncharacterized support no verdict in either direction. The observation worth
keeping: the producer's satisfaction gate (97-100%) and this suite's sheet
consistency (0.238) tell opposite stories that the available evidence cannot
arbitrate. Independent evaluation of this scroll starts when human-verified
patches exist for it.

## 8. The quality scale: 4x the step budget, on identical sealed evidence

The question section 6 could not answer: does a *better* fit score better?
Two fresh `fit_spiral` runs on the section 6 window, this time twins by
construction: same Kaggle T4, same docker image (pinned by sha256), same
seed, same 162-key override set (reconstructed from the reference run's
requested-config dump and guarded by startup counters that must match the
reference exactly, or the run kills itself), villa `scripts/spiral`
self-hosted at commit `bb6248fe7` (per-file sha256 manifest ships with the
input dataset), differing in **exactly one key**: `num_training_steps`,
1,500 vs 6,000. An independent review pass diffed the two executed notebooks
(only the step constant and cosmetic run tags differ), verified the step
chronology in both logs (strictly monotonic to 1500/1500 and 6000/6000, a
4.35x marginal-compute ratio for 4x the steps), and confirmed the two output
mesh sets differ file by file.

The analysis plan was fixed before any result existed: comparisons, paired
bootstrap (20,000 draws, the same `scripts/bootstrap_ci.py --unseen`),
**paired distance deltas as the primary criterion**, the other declared
metrics reported with intervals but never promoted, no post-hoc metrics. The
plan ships verbatim
([`examples/analysis_plan_quality2.fr.md`](examples/analysis_plan_quality2.fr.md);
provenance, SHA-256 and an English translation in
[`examples/analysis_plan_quality2.md`](examples/analysis_plan_quality2.md)),
from a private working log; an independent review pass verified its git
timestamp (9h50 before the first result, commit to commit) and that it is
unchanged since, re-verified against the log's history when the text was
extracted.

Results, in the pre-registered order, both runs scored against the same
sealed evidence as section 6 (per-patch unseen counts identical across all
three reports):

- **Primary criterion: not met.** Paired distance deltas span zero in both
  tails: p50 -0.41 [-0.82, +0.06] vox, p99 +0.40 [-1.40, +2.64] vox. Four
  times the budget left the distance profile statistically unchanged on this
  window.
- **Declared secondary metrics: all three exclude zero, in the long run's
  favor.** Sheet consistency +0.209 [0.141, 0.268] (0.605 vs 0.396);
  within-tau +0.060 [0.017, 0.103] (0.735 vs 0.675); normal-agreement p90
  16.1 degrees better [11.7, 21.4] (22.6 vs 38.7 degrees).
- Reading: on this window the extra budget polishes sheet coherence and
  orientation rather than raw distance. villa's own satisfaction metric
  ranks the runs the same way (6/389 patches satisfied at 1,500 steps,
  84/389 at 6,000): where both instruments can see, they agree, and the
  held-out metrics see it on evidence the fit was never given.

Platform bound, from the third pair: the 1,500-step twin against the
original consumer-GPU reference run of section 6 (RTX 3060 Ti eager vs T4
triton) agrees within **0.26% relative on every headline metric**; the
paired bootstrap resolves platform effects of order 0.02 vox (CI up to
~0.06 vox, significant on p50), an order of magnitude below the secondary
gaps above.

Commit attribution note, for honesty: our notes first recorded the section 6
local runs at villa commit `51b8499`. A config-key consistency check refutes
that hash (the reference run's requested-config dump carries keys that exist
only in villa's [#1203, #1258) window), the exact local state remains to be
confirmed from the original machine, and the `default_config` dict is
byte-identical across the candidate window while the runtime modules differ
by tens of lines. The 0.26% twin bound is what makes this residual
uncertainty immaterial for the table above.

Artifacts: `examples/real_run_cheap2_report.{json,md}`,
`examples/real_run_quality2_report.{json,md}`, the three bootstrap
tables `examples/bootstrap_*.txt`, the villa satisfaction rows verbatim
(`examples/real_run_cheap2_villa_metrics.txt`,
`examples/real_run_quality2_villa_metrics.txt`), and the pre-registered
plan (`examples/analysis_plan_quality2.md`). The reports' `meta` path prefixes are
redacted to `<runs>`/`<data>` placeholders, run-folder names kept; every
measured field is untouched.

## 9. The planted-defect matrix, on a real fit's own output

Section 2's matrix runs on a synthetic scroll: analytic ground truth, ideal
geometry, and an obvious objection. Nothing there shows the metrics behave on
the irregular surfaces a real `fit_spiral` run emits, and the fits scored above
are all ours. One metric had never been exercised against a label at all: **0
of the 4,922 PHerc. Paris 4 verified patches carry a `winding.tif`**, so
winding agreement — the channel that carries this suite's "identity next to
distance" argument — reads `not computed: no scored patch carried a usable
winding grid` on every real report above.

`scripts/planted_defects_real.py` closes both gaps with one move. It damages a
real run's *output surfaces* in ways whose answer is fixed before the run,
rescores the same sealed evidence, and asks of each scenario not only whether
the intended metric fired but whether it fired in the right (winding, z, theta)
place while the others held still. This is not section 4b rerun: that one
displaces the held-out **evidence** around the umbilicus, this one displaces
the **fit's surfaces**, which is the defect a real fit actually presents.

Protocol: the section 8 `quality2` run (6,000 steps, 120 windings w010-w129),
the same 94 sealed patches (49,458 quad centers), the same knobs as everywhere
above (tau = 6 vox, `--unseen-min-dist 2`, z 10600-10900, `--variant spliced`,
the 541 fit inputs for the leakage audit). The displacement is the run's own
median pitch, measured by the intrinsic block rather than assumed: **19.10
vox** (section 4b's 20.31 is a different run's pitch). The null row is not a
new claim: it is the report already shipped as
[`examples/real_run_quality2_report.json`](examples/real_run_quality2_report.json),
reproduced on every field the two files share — same unseen block, same
leakage profile, same intrinsic counters, all 120 per-winding validity
figures, and all 94 per-patch rows — with **one** difference, which is the
point of the section: the shipped run reports `winding_agreement: null` and
this one reports a number, because this one supplies the labels. (The new
artifact also republishes a subset: it drops per-patch `dist_max`,
`normal_angle_*` and the per-patch unseen block, and the intrinsic `worst`
list is not comparable at all, since the shipped JSON predates the
offender-interleaving change of 2026-08-03.) Only the surfaces change from
row to row. The five defect scenarios were also run a second time in fresh
processes and reproduced byte for byte — a procedural check, not one the
artifact records, unlike everything else here; the null's own two-pass check
*is* in the artifact, in the table below.

### The winding label PHerc. Paris 4 does not ship

Winding agreement compares a patch's own relative winding annotation against
the winding ids the fit assigns it. No verified patch carries that annotation.
Planting the defect manufactures it: each sealed patch is labelled with the
winding the **intact** run assigns it, on the quads where that assignment is
locally unambiguous, and the plant then makes the fit disagree with those
labels somewhere known in advance.

`winding.tif` is a per-vertex grid while the metric reads the mean of a quad's
four corners, so a vertex is labelled only when every quad touching it was
scored and they all agree; a quad then has four finite corners exactly when it
sits strictly inside a constant-assignment region, and its mean is that
constant. Everything else stays NaN, which the metric skips — the convention
villa uses to leave the first column past a seam unlabelled. That labels
**31,080 of the 49,458 scored quads (62.8%)** across 90 of the 94 patches; the
other four have fewer than two labelled quads and report no agreement, as they
should.

What this establishes, said before the table rather than after. The labels come
from the reference fit, not from a human, so the null row's 1.0 is true by
construction and says nothing about whether that fit is right. What is *not* by
construction: the metric is mode-centred on both sides, so a uniform
relabelling is invisible to it by design and only a disagreement varying
**inside one patch** registers; whether a plausible real defect produces one,
whether the arithmetic survives 120 irregular real windings, and whether it
fires on the patches straddling the defect and not on the others, are
measurements. On the whole-turn plant below, agreement drops on **78 of the 80
straddling patches that report one, and holds at exactly 1.0 on 9 of the 10
that do not straddle it** (the tenth reads 0.944, a false alarm on a patch the
plant never touched).

Three things that control does *not* establish, because a reader will assume
them otherwise. First, all 13 non-straddling patches lie entirely **outside**
the band — the straddling patches account for all 16,406 in-band points — so
the 1.0s are a no-false-alarm check on untouched geometry, not a localization
result; and since no sealed patch lies wholly inside the band, the
mode-centring blind spot asserted above is restated from DESIGN.md, never
demonstrated. Second, the label is `score_patch`'s own nearest-face winding
under the intact fit, so agreement and the "matched winding shifted by -1"
figure in the same row are **one measurement seen twice**, not two
confirmations — agreement adds patch-wise pooling and the 62.8% restriction,
nothing more. Third, the null's 1.0 does not police the label builder either:
`score_patch` rounds the labels before comparing them, so labels invented at a
boundary round back onto the assignment they came from. That invariant is
pinned by `tests/test_planted_defect_labels.py` against an independent oracle
instead, which is where it belongs.

Calibrating the metric against human truth still needs a corpus carrying
winding grids; this is detection and localization, not calibration.

### The matrix

| Planted scenario | Expected | Observed |
|---|---|---|
| Nothing (null control) | the shipped report, and a second scoring identical | every field of the section 8 report reproduced, all 94 per-patch rows included; two scorings identical bit for bit (per-point payload, aggregates, intrinsic, face counts); winding agreement exactly 1.0 |
| Whole family +1 pitch (19.10 vox), z 10700-10800 | identity fires, distance barely moves, topology silent | matched winding exactly -1 on **63.1%** of the 16,406 in-band points (67.8% of the 9,901 clear of the band edges), unchanged on 97.9% of the 33,052 outside points and **99.97%** of the 26,504 of those clear of the edges; in-band distance p50 1.74 -> 3.70, a shift of 1.95 vox, a tenth of the 19.10 planted; intrinsic 138 (of 46,120 bins) -> 141 (of 46,107), 6 new and 3 gone, but only **1 of the 6 new ones inside the plant**. **Four other channels fired too** — see below |
| One winding +1 pitch, same band | distance fires, and only on that winding | distance p50 on w063's own in-band evidence 1.12 -> 12.14 vox, elsewhere 2.04 -> 2.08; **37 of the 38** new crossings inside the planted (winding, z) bins |
| Two adjacent windings exchange radius, theta 30-90 deg | sheet consistency falls at near-zero distance | caught, but **not by the named metric**: the intrinsic check gains 72 crossings and **all 72 sit inside the planted (winding, theta) bins**, none outside, none lost; mean sheet consistency only moves 0.744 -> 0.737, and of the 6 patches carrying evidence on the swapped pair 3 lose consistency while 3 *gain* it |
| r += 3 vox * sin(theta), every winding | distance fires, topology frozen | distance p50 1.99 -> 2.50 overall, 1.99 -> 2.06 where sin(theta) is small and 1.99 -> 2.52 where it is not; topology within 3 bins of frozen (crossings 138 -> 139, collapsed 194 -> 196, inflated unchanged) |
| One winding's vertices invalidated in a (z, theta) box | its validity drops, nobody else's | validity of w055 alone 0.4851 -> 0.4517, every other winding unchanged to the last digit; distance over the hole p50 0.29 -> 14.13 vox, elsewhere 2.017 -> 2.033; **zero** crossings invented — but 48 bins fell below the vertex count the check needs and stopped being examined at all, retiring 5 inflated-gap flags with them |

Degenerate faces were recounted after every mutation, because a displaced
vertex can pinch a grid cell and the distance primitive over-estimates on faces
whose first two vertices coincide (section 1). Every row: **zero** faces with
any duplicated vertex pair and zero exactly collinear, out of 1,171,318 faces
(1,170,612 in the punched row, which removes some).

### What it caught badly

Six things, and they are the reason this section exists.

**On real geometry the alarms are not orthogonal.** Section 2's stated design
property is that each defect is caught by the metric meant for it "while the
others stay silent, so an alarm identifies the failure mode". The whole-turn
plant fires four more channels at once: sheet consistency 0.744 -> 0.570,
single-winding consistency 0.718 -> 0.552, pooled normal agreement p90
17.9 -> 34.0 degrees, within-tau 84.0% -> 79.7% (on unseen evidence only,
sheet 0.605 -> 0.483 and normals 24.1 -> 38.1 degrees). None of those is a
false alarm — the plant really does cut every patch that crosses a band edge,
and really does leave a radial wall there — but that is the point: **the
displacement a z band forces is a discontinuity, not a relabelling**, and a
real accumulated-turn error would drift into place instead of stepping. So
this row demonstrates that winding identity moves by the predicted amount; it
does **not** demonstrate that an identity alarm can be read on its own. For
comparison, the sheet-consistency drop here (-0.174) is of the same order as
the entire +0.209 gain section 8 rests on. A reader tempted to use these
metrics to name a failure mode should take that as the warning it is.

**The whole-turn plant is not recovered exactly, and could not be.** On the
ideal synthetic scroll the same plant moves the matched winding by exactly -1
for 100% of in-band evidence; here it is 63.1%. The direction of the reason
is measured and ships in the artifact's `meta`: only **49.9% of this run's
46,120 adjacent-winding gaps lie within 25% of its own median pitch** (22,991
of them), so displacing by exactly that median lands winding k where k+1 was
only where the local spacing is close to it. That statistic is an indication,
not a bound: it is computed over every bin of the whole family, equally
weighted, while the 63.1% is over evidence points inside one z band — and
being the smaller number it plainly does not cap the larger one. The
synthetic 100% is a property of an ideal spiral, not of the metric, and the
honest statement is that on real geometry roughly a third of the evidence
does not follow a median-pitch displacement.

**Distance is not blind to a whole-turn error on a real fit, only
near-sighted.** Section 4b moves the evidence inside an intact family, which
tiles space at the pitch, and gets 0.23 vox out of a two-pitch displacement.
Moving the fit is harder: the family's own gap is irregular, so the displaced
family is not a relabelling of itself, and the in-band median distance goes
from 1.74 to 3.70 vox. That is still a tenfold under-report of a 19.10 vox
error, but "distance cannot see a whole pitch" is too strong for this
direction, and the tenfold statement is the honest one.

**Sheet consistency did not catch the sheet swap.** The defect itself was
caught, and localized perfectly: 72 new crossings, every one of them in the
planted bins. But the metric named for this failure mode barely moved — 0.744
to 0.737 on the aggregate, for a defect touching 4,325 of 49,458 points — and
per patch it moved in *both directions*: three of the six affected patches went
**up**, one from 0.82 to 0.93 after a defect was planted on it. That matches
the upward bias frozen as a strict `xfail` in `tests/test_sheet_contract.py`
(DESIGN.md, "Known limit"), and it is the second independent sighting of it,
this time on real geometry. What discriminated instead was distance, which rose
on **all six** affected patches (0.62 -> 4.36, 0.76 -> 3.69, 1.16 -> 3.57,
2.55 -> 5.12, 3.54 -> 6.64, 6.51 -> 7.55 vox) — and
that is itself a caveat on the plant: exchanging two windings by +/- the median
pitch does invert their order, but where their real separation is not the
median they land a few voxels off each other's place, so this is not the
*near-zero-distance* swap the synthetic row tests. Planting one would need a
per-(z, theta) radius model of each winding, which this script does not build.

**The report's offender table does not localize a fresh defect.** `report.md`
renders the top **ten** offenders, shared between three kinds; after the swap
those ten hold 4 crossings, exactly **1** of them in the planted bins, though
all 72 new ones are. (The JSON's `worst` list is twenty entries and holds 7,
still only 1 in the plant.) On a fit already carrying 138 crossings, its own
worst outrank anything freshly planted. The count is right and the
localization is recoverable in principle — asking the same check for a
`top_n` past the offender count lists every violated bin, which is how the 72
was obtained — but `top_n` is not exposed by `spiralcheck intrinsic` or by
`score`, so from the CLI it is not recoverable at all, and the rows a human
actually reads are not where a new defect will show up.

**The unseen aggregate cannot see the punched hole at all.** Its 15,437-point
block is bit-identical to the null's, so every point whose distance the hole
changed — not only the 404 over it — sits within 2 vox of a fit input. The
leak-free column is the honest one for comparing runs, and it is also the one
that can miss a defect planted where the evidence is densest.

### Scope

One run, one 300-slice window, one scroll, and the defects are ours — and
sited where the sealed evidence is densest, which is the best case for
detection: `one_winding` takes the winding carrying the most in-band points,
`sheet_swap` the adjacent pair carrying the most in the theta band, `hole` the
winding with the most in its box (the runners-up ship in the artifact). Two
properties of the plants themselves are worth knowing before reading the
table. A z-banded displacement necessarily leaves a **one-grid-row radial wall
about 19.9 vox tall** at each band edge, which no real accumulated-turn error
produces — that is what the edge margin stands clear of, and part of why four
other channels fire. And the intrinsic localization is tested at the
resolution of the intrinsic bins, which are **35 vox in z** and 7.5 degrees in
theta, so the theta claims are sharp and the z ones are coarse (VALIDATION
section 3 already lists the z axis of that localization as thin coverage).

The winding labels are manufactured from the reference fit, so this measures
detection and localization, not whether that fit is right. The claim that
survives all of it is narrow and worth exactly what it says: on the output of
a real `fit_spiral` run, every planted defect was detected, and where a
localization could be measured it landed where the plant was. What did *not*
survive is the reading section 2 invites — that the metric which fires names
the failure mode. One defect was caught by a different metric than the one
aimed at it, another fired four metrics at once, and the whole-turn plant is
recovered exactly for under two-thirds of the evidence rather than all of it.

One thing this cannot measure, said because it would be easy to imply
otherwise: villa's satisfaction metrics are computed by `fit_spiral` through
the fit's own transform from its checkpoint, not from the meshes, so they
cannot be recomputed on a tampered mesh set. The narrower true statement is
that a defect planted in a run's *output* is invisible to any metric computed
only from that run's *inputs*.

Artifact: [`examples/planted_defects_real.json`](examples/planted_defects_real.json).
Every scenario carries an aggregate, an unseen block, intrinsic counters,
per-patch rows and a degenerate-face recount; the five defects add a
localization response, the null a two-pass check and the winding-label census.
Local path prefixes redacted to `<runs>`/`<data>` like the section 7 and 8
reports; every measured field untouched.

## 10. Winding agreement meets a real winding label

DESIGN.md said of the winding-agreement metric: "**Never exercised on real
data**", because 0 of the 4,922 PHerc. Paris 4 verified patches carry a
`winding.tif`. Section 9 ran the channel on real geometry against labels
manufactured from the reference fit's own assignment, and said in the same
breath that this was detection, not calibration. This section closes the
other half: winding evidence on this scroll does exist, in a shape the metric
was not written for — villa **point collections**, which VC3D writes and
`fit_spiral` consumes as constraints. `spiralcheck annotations` scores a run
against them from the exported meshes and the umbilicus, with no checkpoint,
no torch and no GPU.

### This is not a held-out measurement, and the word is not used below

The three collections scored here are **inputs to the run being scored**. The
same files are consumed by both runs of section 6 and both twins of section 8;
section 6 already records the channel and measures its geometric overlap with
the sealed patches. So this is an input-side check of the same family as
villa's satisfaction, and every number below is a constraint-satisfaction
number, not a generalization one. What it is worth is stated plainly in
"What this establishes" further down; what it is not worth is the held-out
claim the rest of this document makes, which does not extend here.

Holding a subset of the annotations out would need a refit, which needs a GPU
this project does not have, so it was not attempted and no partial substitute
was improvised.

### What the evidence actually is

719 points in three files, and they are not all the same kind of thing. This
matters enough to lead with, because section 6 previously called all 719
"manually clicked" and that is wrong for 620 of them:

| file | collections | points | `wind_a` | provenance |
|---|---:|---:|---|---|
| `abs_winding.json` | 1 | 1 | 37.0, absolute | one human click |
| `relative_windings.json` | 16 | 98 | 1..15, relative | **human clicks**: one distinct `creation_time` per point, median gap 0.65-1.4 s |
| `same_windings.json` | 26 | 620 | `null` (same winding) | **machine-traced under human supervision**: one identical timestamp for every point of a collection |

The 620 come from VC3D's `SameWrapAnnotationTool`
(`apps/VC3D/volume_viewers/annotation_tools/SameWrapAnnotationTool.cpp`). Its
`generatePreview` Otsu-thresholds the displayed slice, skeletonises it
(Guo-Hall thinning), snaps two human-chosen endpoints to the nearest skeleton
pixel, runs Dijkstra between them over skeleton pixels only, samples the path
at a fixed spacing, and `commit` writes the whole collection at once — hence
the single timestamp. The human asserts "this path stays on one wrap" and
accepts the result; the individual point positions follow the papyrus in the
scan.

That provenance cuts both ways and both should be said. The trace follows real
sheet continuity in the CT, which is stronger evidence than a click at a
guessed position. But its failure mode is correlated with the fit's: where two
sheets touch, the skeleton can bridge them, the path changes wrap, and the
"same wrap" assertion is then false in exactly the place a fit also fails. So
the 620 are supervision, not ground truth, and the 98 clicked points are the
only unambiguously human labels here.

### The measurement

Villa already scores these constraints, in `satisfaction_metrics.py`
(`get_unattached_pcl_satisfied_counts`): each collection is id-sorted into a
strip, mapped through the fitted transform, its shifted radius unwrapped
across theta=0 crossings, and `unwrapped_shifted - wind_a * dr_per_winding` is
required to stay within 0.45 pitches of the strip's snapped median (and the
reprojected target within 6 scan voxels). That needs the checkpoint, torch and
CUDA, and runs inside the fit.

This suite computes the same quantity from the exported meshes. Where villa
reads an unwrapped shifted radius out of its transform, we read the continuous
winding coordinate `u = winding_id + column / columns` off the nearest
exported face — the coordinate sheet consistency is already built on,
continuous across the theta seam — and subtract the azimuth the collection
travels, which `u` accumulates and a winding index must not:

    W = u - theta / 2pi          (theta unwrapped along the collection)
    N = W - wind_a               (villa's unwrapped_shifted - windings * dr)

`N` is constant along a collection exactly when the fit honours it. Its
absolute value carries an arbitrary offset (the mesh column origin and the
umbilicus azimuth origin need not coincide), so only differences are read: a
point disagrees when its `N` is at least half a turn from the collection's
median — the same boundary `sheet_components` uses.

Prior art, since this checks the same annotations from a different side.
Villa's `find_inconsistent_windings.py` derives the winding number a point
*should* have from these very collections, propagating absolute anchors across
a patch graph and measuring the holonomy of relative-annotation loops; it
audits the annotations' mutual consistency, and rebuilds the fit's transform
from a checkpoint to do it. `vc_calc_surface_metrics` scores one tifxyz
surface against a ground-truth point collection post hoc, which is the closest
shipped tool to this one; it takes one surface, not a winding family, and
needs `vc_tifxyz_winding` first. pscamillo's `winding-ruler` and
`constraint-gauge` calibrate winding *constraints* against human labels. Here
the annotations are taken as given and the *output surfaces* are the subject.

### Leakage: do the sealed patches come from these annotations?

They share a naming scheme, so this had to be checked rather than assumed. 16
of the 94 sealed patches are named `same_wrapNNNNNN_lasagna`, and 898 of the
4,922 verified patches carry that prefix. Each such patch records its parent
in its own `meta.json`: `same_wrap000360_lasagna` names the collection
`same_wrap360`. Read off all 16, the sealed patches descend from collections
360, 1105, 1111, 1130, 1875, 1877, 1879, 1890, 1894, 1896, 2028, 2031, 2462,
2468, 2919 and 2962; the 541 fit inputs descend from 101 further collections
in the range 358-3335. The collections scored here are numbered 37 to 141, and
**none of them is a parent of any sealed patch or any fit input**.

The numbering is one shared counter, not two coincidentally similar ones, so
that disjointness means something: 7 of these 26 collections (40, 45, 51, 58,
59, 60, 61) do have a homonymous patch in the 4,922 — and none of those 7 is
in the sealed 94 or the 541 either. The remaining channel is geometric
proximity, which section 6 already measures in the other direction: 6 of
51,679 sealed vertices lie within 2 vox of an annotation point.

### The result

Run `quality2`, `--variant plain`, tau = 6, z 10600-10900.

| set | collections | points | in window | decidable | agree | agreement |
|---|---:|---:|---:|---:|---:|---:|
| all | 43 | 719 | 698 | 338 | 332 | **98.2%** |
| relative (human clicks) | 17 | 99 | 89 | 82 | 81 | 98.8% |
| same-winding (machine-traced) | 26 | 620 | 609 | 256 | 251 | 98.0% |

| Expectation, fixed before the run | Observed |
|---|---|
| the wrap index is constant along a collection the fit honours, well inside the half-turn boundary | largest spread among agreeing points **0.0155 turns** against a boundary of 0.5: a margin of 32x, so the verdict is not a threshold artefact |
| a violation is a whole winding, not a fraction | the 6 disagreeing points sit between **0.994 and 1.001 turns** from their collection's median, none nearer the boundary than 0.49 turns; 3 collections carry them (`same_wrap42` 21/25, `col247` 12/13, `same_wrap47` 20/21), and all 6 are 3.8-5.3 vox from a surface, so none is a marginal read |
| a point far from every surface gets no verdict | 360 of the 698 in-window points declined rather than assigned; 7 collections in the window have no decidable point at all and are reported as undecided, not as 0 |
| the verdict does not hinge on the tolerance | tau = 2: 200/200 (100%); tau = 4: 284/285 (99.6%); tau = 6: 332/338 (98.2%); tau = 10: 427/441 (96.8%); tau = 20: 644/698 (92.3%) — monotone, no cliff |
| collections judged on one point prove nothing | 25 of the 28 collections with at least two decidable points are honoured throughout; the 3 single-point verdicts are excluded from that count, being perfect by construction |

### Cross-check against villa's own verdict

The interesting comparison is not the fractions, which measure different
things, but which collections each instrument refuses to call clean. Of the 24
collections `satisfied_fitted.json` scores, 2 are undecidable here and are
excluded; of the remaining 22, the two instruments give the same verdict on
17 (77.3%). Both flag `col247` and `same_wrap42`. **Neither instrument is
contradicted by the other in the direction that would matter: there is no
collection this suite flags that villa calls clean.**

Villa flags five that this suite does not (`col159`, `col160`, `same_wrap44`,
`same_wrap51`, `same_wrap55`), and the reason is structural rather than a
miss. Villa's satisfaction is a **conjunction**: right winding band *and*
within 6 voxels of the reprojected target. A point on the correct winding in
the wrong place fails villa and passes here. On `same_wrap44` villa reports
9/22 while all 19 decidable points here sit on the annotated winding, so at
least 10 points are "right winding, wrong place". That is not a disagreement
about the geometry; it is this suite separating two failures villa's number
merges — which is the same specificity question section 9 raises from the
other end.

`same_wrap63` is the sharpest case in the other direction: villa scores it
**0/32**, the worst of the run, and every one of its points lies 9-17 vox from
any exported surface, so this suite declines to judge it. Both instruments say
something is wrong there, by different mechanisms, and neither says it in the
other's vocabulary.

### What this establishes, and what it does not

Established: the winding-agreement idea, which had only ever run against
synthetic fixtures or labels manufactured from the fit itself, produces a
number against annotations made by a person in VC3D, from a finished run
folder, on CPU. Its decision margin on real geometry is 32x the noise floor.
It agrees with villa's independent instrument wherever both can decide, and
never accuses a collection villa clears.

Not established, and none of this is a technicality:

- **This is not held-out.** The fit consumed these annotations. A 98.2% here
  is constraint satisfaction measured with a different ruler, not evidence
  the fit generalises.
- **Coverage is under half.** 338 of 698 in-window points are decidable at
  tau = 6. That is mostly a window-edge artefact rather than a property of the
  fit — **357 of the 360 undecidable points (99.2%) lie within 20 vox of a
  window edge**: 20 of the 26 same-winding collections sit at z = 10604.4, 4.4 vox
  inside a 300-voxel window whose exported grids are thin at the boundary
  (per-winding z minima run from 10600.0 to 10613.9). Displacing one
  collection's 16 points in z, holding y and x, the median distance to the
  family falls 15.49 -> 10.83 -> 6.67 -> 5.23 -> 3.13 vox at z = 10604.4,
  10609.4, 10614.4, 10624.4, 10684.4. Read the agreement as a statement about
  mid-window evidence.
- **620 of the 719 points are machine-traced**, so "agrees with a human" is
  precise only for the 98 clicked ones (81 of 82 decidable).
- **An evenly split collection indicts both sides.** The reference is the
  collection's median, so a two-point collection whose points disagree reports
  both as offenders; the metric cannot say which is misplaced because the
  evidence does not. Pinned in `tests/test_annotations.py`.
- **One scroll, one window, one run**, and the azimuth correction is computed
  in scan space about the umbilicus while `u` follows the fit's own deformed
  grid. The two agree only up to the deformation; `wrap_index_spread` carries
  that residual and is the number to watch on a fit less well behaved than
  this one.

Artifact:
[`examples/winding_annotations_real.json`](examples/winding_annotations_real.json),
carrying the per-collection rows, the tau sweep, the decidability profile and
the villa join. Local path prefixes redacted to `<runs>`/`<data>` like sections
7 to 9; every measured field untouched.

## Reproduce

```bash
uv sync --group dev
uv run pytest -q                      # 174 tests + 1 strict xfail (a frozen known limit)
uv run python scripts/mutation_check.py   # 54/54 injected bugs must be detected
uv run python scripts/real_data_smoke.py <verified_patches_dir> 500
uv run python scripts/real_overlap_check.py <verified_patches_dir> 150
uv run python scripts/planted_defects_real.py <meshes> <heldout> \
    --umbilicus <umbilicus.json> --fit-inputs <fit_inputs> \
    --z-range 10600,10900 --out <dir>   # section 9; ~70 min, 9 scoring passes
uv run python scripts/winding_annotations_real.py --meshes <meshes> \
    --pcl <abs_winding.json> --pcl <relative_windings.json> \
    --pcl <same_windings.json> --umbilicus <umbilicus.json> \
    --satisfied <satisfied_fitted.json> --variant plain --tau 6 \
    --z-range 10600,10900 --out <out.json>   # section 10; one pass
```

The planted-defect run scores nine times and peaks around 5 GB, so `--only
<scenario>` runs them one at a time on a small machine; `null` must run first,
since it writes the reference the others read.
