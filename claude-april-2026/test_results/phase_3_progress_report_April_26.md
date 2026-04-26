# Phase 3 E2E Tests — Progress Report

**Date**: April 26, 2026
**Status**: Phase 3 (T21–T34) complete — 14/14 passing on `gemini-3.1-flash-lite-preview`
**Environment**: Google Colab, `pipeline_e2e_testing_post_llm_resiliency.ipynb`

---

## What Was Tested

Phase 3 extends end-to-end coverage beyond the single-task and basic-dependency shapes exercised in Phase 1 (T1–T10) and Phase 2 (T11–T20). The fourteen new tests probe two task-shape classes that prior phases did not exercise:

**Run 1 (T21–T28) — single-task semantic coverage:**
- T21–T23: cross-field AND across three attribute pairings (Director+Loc, Actor+Loc, Writer+Loc)
- T24–T25: cross-field OR (Director|Writer; Title|Loc)
- T26–T27: constraint-vs-output dimension — fields named in the query that are output dimensions, not filters
- T28: cross-field AND with location granularity

**Run 2 (T29–T34) — multi-task dependency coverage:**
- T29–T30: retrieve→count with distinct count_basis
- T31: retrieve→retrieve where the dependent task adds a new predicate
- T32: retrieve→rank where the rank dimension is the output, not a filter
- T33: three-task chain ending in compare (`dependsOn: ["t1", "t2"]`)
- T34: count_basis disambiguation when t1 source has location framing but t2 source explicitly says "films"

All test values are anchored to real rows in the dataset (verified against `some_real_rows_from_dataset.txt`).

---

## Results

**Run 1 — T21–T28: 8/8 passing.** Achieved on the third execution; the first two were contaminated by normalizer corruption that mangled inputs before Step 4 saw them. See the normalizer changelog (April 26) for the three fixes that made the run clean.

**Run 2 — T29–T34: 6/6 passing on the first execution.** No normalizer issues, no LLM resilience events except one bare-array response on T34 that the Step 4 envelope handled silently.

---

## What Each Test Confirmed About the Pipeline

### Step 4 — predicate extraction is robust

Cross-field AND was correctly emitted for Director+Loc (T21), Actor+Loc with three-column OR expansion (T22), Writer+Loc (T23), and Title+Loc with location granularity (T28). Cross-field OR was correctly emitted across Director+Writer (T24) and Title+Loc (T25).

The constraint-vs-output-dimension distinction holds in both single-task and multi-task settings. Step 4 correctly emits *no* Writer predicate for "which writers filmed at..." (T26), no Actor predicate for "which actors filmed at..." (T27), and no Director predicate for the rank task in "which directors appear most often there" (T32). The mentioned-but-not-constraining field is consistently treated as the output dimension.

Dependency hygiene is correct on T31. The dependent retrieve task (`t2.predicate = Director == nicholas meyer`) does not redundantly re-emit t1's Locations clause. Step 4 understands that the upstream filter is inherited via `dependsOn` and produces only the *added* predicate. This is a non-trivial property and was not exercised by Phase 1 or Phase 2.

### Step 3 — task decomposition handles the new shapes

Two-task chains for retrieve→count (T29, T30, T34), retrieve→retrieve (T31), and retrieve→rank (T32) all decomposed correctly with `dependsOn: ["t1"]` on the dependent task.

T33 is the first three-task chain to be exercised end-to-end. The decomposer correctly produced two independent retrieves (`dependsOn: []` on both t1 and t2) and a downstream compare with `dependsOn: ["t1", "t2"]`. The fan-in dependency shape is functional.

### Step 5 — granularity resolution is internally consistent

For multi-task chains, Step 5 resolves granularity per-task in a way that is coherent with downstream computation: T31's t1 resolves to location while t2 resolves to film (the dependent narrow shifts granularity), T32 resolves t2 to film for the rank output, and T33 resolves all three tasks to location for the set-comparison data model.

### Step 6 — generated code is correct against the per-row data model

The dataset is one-row-per-(film, location). T29 returned `count: 27, count_basis: 'locations'` for "films shot at golden gate bridge and how many are there" — manually verified to be correct. T30 returned location-basis count (23) for The OA Part II. T34 returned film-basis count (1 film across 24 location rows) for the explicit "how many films" phrasing. These three together confirm count_basis behaves correctly across phrasings on this dataset.

### Compare kind — first end-to-end exercise

T33's compare task produced a set-difference output: `{golden_gate_bridge_only, port_of_sf_only, both, total_unique_films}`. Step 6 inferred this shape without explicit guidance from the IR. The choice is reasonable for a film-set comparison, though it represents Step 6's interpretive autonomy rather than a tightly specified contract. See the open-items document for follow-up.

---

## What Phase 3 Surfaced That Earlier Phases Did Not

Three normalizer bugs were exposed by the new test queries, all under the same root cause class — the cluster extractor and city-pattern stripper had no awareness of multi-word locations in the dataset. None of these bugs were visible in T1–T20 because earlier phases used different anchors. All three were closed during this session; see the normalizer changelog.

The compare kind's output shape is currently inferred by Step 6 rather than specified by the IR. This was not exercised by any prior phase. T33 produced a sensible result, but the under-specification is a real contract gap.

---

## Performance

End-to-end pipeline latency was uneventful — no quota events, one infrastructure 503 burst on the first attempt at T22–T27 in Run 1 that cleared on retry. The bare-array response on T34's Step 4 was handled by the existing resilience envelope without a retry being triggered (it was a content-shape variation, not a transport failure).

---

## Phase 3 Closes Out

| Phase | Tests | Status |
|---|---|---|
| Phase 1 | T1–T10 | passing (validated April 20) |
| Phase 2 | T11–T20 | passing (validated April 21, re-confirmed April 22 + April 24) |
| Phase 3 Run 1 | T21–T28 | passing (April 26) |
| Phase 3 Run 2 | T29–T34 | passing (April 26) |

Cumulative coverage: 34 e2e tests passing on the lite-preview model. The single-task semantic surface, the basic dependency surface, and the multi-task / fan-in dependency surface are all validated.

---

## Files

- `pipeline_e2e_testing_post_llm_resiliency.ipynb` — notebook with PHASE_3_TESTS cell and runner
- `query_normalizer_changelog_April_26.md` — accompanying normalizer fixes
- `phase_3_open_items_April_26.md` — open items and forward-looking notes (compare kind, normalizer follow-ups)
