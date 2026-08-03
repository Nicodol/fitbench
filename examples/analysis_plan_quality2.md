# Pre-registered analysis plan for the quality-scale experiment (VALIDATION section 8)

[`analysis_plan_quality2.fr.md`](analysis_plan_quality2.fr.md) reproduces, verbatim, the
section « PLAN D'ANALYSE PRÉ-ENREGISTRÉ » of the private working log that ran the
section 8 experiment. Provenance, re-verified against that log's git history on
2026-08-03: the section was committed on 2026-08-02 at 11:18:39 (+02:00) and is
unchanged since. The pair's kernel had been pushed once the evening before (it
errored before fitting anything) and again at 12:12 on the day of the plan, 54
minutes after it; no attempt before the one that ran produced a number. The
version that ran (cheap2) was pushed at 20:24 and printed its first numbers at
completion about thirty minutes later, more than nine and a half hours after the
plan was committed; the journal entry recording those numbers was committed at
21:08:13, and that commit-to-commit margin is the one VALIDATION section 8 quotes
(9h50 before the first result). SHA-256 of the shipped French file:

```
58caa95a92aaa112b0dbff330fd8282db238cf07326e1529f1547aa782f50508  analysis_plan_quality2.fr.md
```

(The file is stored and checked out with LF line endings, pinned by
`.gitattributes`, so `sha256sum` reproduces this on any platform; so does
`git show HEAD:examples/analysis_plan_quality2.fr.md | sha256sum`.)

The log itself stays private (day-to-day operational notes, machine paths and
unrelated work); the section shipped here is the part that binds the analysis.

## Courtesy translation (the French text is the binding one)

**PRE-REGISTERED ANALYSIS PLAN (August 2, 11:05, BEFORE any cheap2/v7 result)**

Written and committed before any Kaggle fit of the pair had produced a number. The
pre-registered predictions on the desktop machine (WORKPLAN_v02.md, not to be
touched) will be confronted IN ADDITION once retrieved; the present plan is the one
that binds the analysis.

The three comparisons, all on the same 94 sealed patches (v1), paired bootstrap,
20,000 draws, `--unseen`:

1. cheap2 vs quality2 (v7): THE proof, platform-pure (same T4, same image, same
   seeds, only num_training_steps changes, 1,500 vs 6,000).
2. smoke8 vs quality2: the comparison against the published reference.
3. smoke8 vs cheap2: isolates the platform effect (3060 Ti/eager vs T4/triton,
   identical config).

Decision rules, frozen at the time of writing:

- "The tool ranks the long run above" = the paired distance deltas (per-patch p50
  and p99, point-weighted mean) favor quality2 with a bootstrap interval excluding
  zero on comparison 1.
- If the deltas favor quality2 but cross zero: publish "consistent but not
  conclusive under the bootstrap", no overselling; that is an acceptable, honest
  result.
- If the deltas are null or favor cheap2: publish it as is, with the hypothesis to
  examine (1,500 steps may be enough to converge on a 300-slice window; with the
  deferred losses only activating at 25,000 steps, the 6,000 budget may only add
  polish). An evaluation tool that discovers "longer does not mean better" on this
  window is still a valid discovery of the tool.
- Comparison 3 (platform) has NO victory rule: it is descriptive, to bound what
  comparison 2 can say.
- Secondary metrics (within-tau, sheet consistency, normals): reported with their
  intervals, never promoted to the primary criterion after the fact.
- No new metric will be computed after seeing the results; any deviation from the
  plan will be flagged as such.

How it resolved: VALIDATION section 8 reports the primary criterion as not met
(paired distance deltas span zero) and the three declared secondary metrics with
their intervals, as prescribed here; no metric was added by the analysis after the
results. The villa satisfaction cross-check quoted alongside is that instrument's
own printout during the runs, outside this plan's scope, cited as concordance
rather than as a criterion.
