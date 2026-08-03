# examples/: every shipped artifact, and how to regenerate it

All artifacts here come from the runs and protocols documented in
[VALIDATION.md](../VALIDATION.md) (sections 5 to 8). Everything marked *replayable*
regenerates byte-identically from this repository alone; the reports themselves need the
run meshes and the patch data. Each report's `meta` block records its parameters, with
local filesystem prefixes redacted: the section 6 reports to bare `<meshes>`-style
placeholders, the section 7 and 8 reports to `<runs>`/`<data>` prefixes that keep the
run-folder names the reading note below relies on.

## Scored reports (`real_run_*_report.{json,md}`)

Five real runs, one JSON + Markdown pair each. The `.md` is a pure rendering of the
`.json` (*replayable*: `uv run python scripts/rerender_report_md.py <file>.json`, and
`tests/test_examples_coherence.py` keeps the pair in sync).

| run | what it is |
|---|---|
| `smoke8` | VALIDATION section 6, the dense-input demo fit (389 in-window verified patches, 1,500 steps, consumer GPU) |
| `sparse2` | section 6, the sparse twin: same settings and step budget, no patch inputs (`use_verified_patches=false` is the one changed switch), so the fit must interpolate |
| `cheap2` | section 8, the 1,500-step twin re-run on Kaggle (reproduces smoke8 within 0.26% relative on the unseen aggregate, the numbers the repo quotes) |
| `quality2` | section 8, the 6,000-step twin: same seed, code, data, GPU; only the step budget differs |
| `pherc1218` | section 7, the second-scroll feasibility case study (community parity fit, PHerc. 1218) |

Reading note for the Paris 4 runs: the run names say `389-patch` (what the fit actually
fitted inside its z window; villa's own log and `real_run_smoke8_villa_metrics.txt` count
`/389`), while the reports say `n input patches: 541`, the whole input directory offered
to the fit. The leakage audit deliberately measures against all 541: more inputs can only
reveal more leakage, never hide it.

## Split manifests

- `PHercParis4_v1_split_manifest.json`: the original name-level split (seed 20260731,
  4,922 patches, 985 held out). The sealed exam of every Paris 4 report above is its
  held-out side (94 of the 985 fall inside the demo z window). Written before family
  grouping and geometry hashes existed, so audits against it match by full-content hash;
  the geometric leakage measurement is what neutralizes its name-level blindness
  (VALIDATION section 5).
- `PHercParis4_v2_split_manifest.json`: the same source tree split by the current code
  (family grouping, geometry hashes; 1,133 held out, 1,532 families). Recommended for new
  fits; no shipped report used it, because the demo fits had consumed the v1 fit side.

## Run comparisons (*replayable*)

- `compare_smoke8_vs_sparse2.md`:
  `uv run spiralcheck compare examples/real_run_smoke8_report.json examples/real_run_sparse2_report.json --out <file>`
- `bootstrap_quality2_vs_cheap2.txt`, `bootstrap_quality2_vs_smoke8.txt`,
  `bootstrap_cheap2_vs_smoke8.txt`: paired bootstrap over the shared sealed patches,
  e.g. `uv run python scripts/bootstrap_ci.py examples/real_run_quality2_report.json examples/real_run_cheap2_report.json --draws 20000 --unseen`
  (each file's header states its own A, B and knobs).

## Cross-checks against villa's own instrument

- `real_run_smoke8_villa_metrics.txt`, `real_run_sparse2_villa_metrics.txt`: the
  satisfaction metrics printed by villa's `fit_spiral.py` at the end of each section 6
  run, quoted verbatim from the run logs, so the reports can be compared against an
  independent measurement made through the fit's own transform.

## Overlay

- `real_run_smoke8_overlay_z10749.png`: one overlay slice of the smoke8 run (the file a
  scoring run writes as `overlay_z10749.png`, prefixed here with its run name). Gray
  points are winding-mesh vertices; patch points are colored by distance, capped at tau.
