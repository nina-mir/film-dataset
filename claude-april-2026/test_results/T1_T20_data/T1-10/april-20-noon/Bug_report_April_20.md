Here's a handoff report you can drop straight into your project files.

---

# End-to-End Pipeline Testing — April 20 Session Report

**Date**: April 20, 2026
**Status**: Single-task test suite (T1–T10) passing legitimately
**Environment**: Google Colab Pro, Gemini API
**Predecessor**: `bug_report_handoff.md` (April 19)

---

## Summary

Started the session with the April 19 state: 9/10 passing, but with one silent failure (T3) and one reproducible bug (T5). Ended the session with a real 10/10 — every test exercising the full pipeline as architected, with post-processors reaching their inputs and codegen consuming structured IR instead of reverse-engineering from source text.

Two distinct bugs were fixed and one model swap was validated. The April 19 score and the April 20 final score are both "10/10," but only the April 20 version is honest.

---

## Fixed Bugs

### F5. B1 — T5 double-conversion on rank tasks (invariant 23)
- **Status**: Fixed in `code_generation_v2.2.md` as invariant 23.
- **Approach considered**: Executor-level `_coerce_result_data` post-processor in `execute_code`. Rejected after tracing the bug — the `AttributeError` fires inside the generated function's try/except, so the executor never sees a successful result to coerce. Prompt-level fix was the only viable route.
- **Fix**: Added hard invariant forbidding application of additional type conversions (`.to_dict()`, `.tolist()`, `.to_json()`, `dict(...)`, `list(...)`) to a value that has already been stored in `task_results[...]['result']` when assembling the outer `result` dictionary. Conversion happens exactly once, at point of storage. Includes a wrong/right example pulled from T5's failure mode.
- **Verification**: T5 ran clean on first test after the prompt update. `Top 5 directors with the most films are: Andrew Haigh (11), Chris Columbus (4), ...` — correct output, no `AttributeError`.

### F6. Step 4 envelope-mismatch (validator fix)
- **Status**: Fixed in `extract_filters` (pipeline harness, not the prompt).
- **Symptom (initially hidden)**: Across the first April 20 run, every Step 4 call printed `[filter_extractor] Validation failed, null predicates fallback`. Pipeline still scored 10/10 because the codegen LLM was reverse-engineering predicates from `source` text — exactly the architectural anti-pattern the refactor was meant to eliminate. Tests "passed" without the predicate path running.
- **Root cause**: `gemini-3.1-flash-lite-preview` returns Step 4 responses as a bare array `[ {...} ]` rather than the wrapped `{"tasks": [...]}` envelope the validator expects. Earlier Gemini models (2.5-pro, 2.0-flash) wrapped by convention. The validator's first check is "top-level `tasks` array present" — bare array fails immediately, fallback fires, post-processors silently run on null IR.
- **Fix**: Four lines in `extract_filters`. After `json.loads`, check `isinstance(result, list)` and wrap as `{"tasks": result}` before validation:
  ```python
  if isinstance(result, list):
      print("  [filter_extractor] Normalizing bare-array response")
      result = {"tasks": result}
  ```
- **Verification**: Final April 20 run shows real predicates flowing through every test — `Director ==`, `Locations contains`, `Year between`, AND trees, OR trees for actor expansion, spatial predicates with geocoded coordinates. Two architectural side-effects unblocked: (a) actor-expansion post-processor now reaches T3, (b) geocoding resolver now reaches T8 (predicate gains `latitude`/`longitude` between Step 4 and Step 5).

### F7. Step 3 missing-log diagnostic
- **Status**: Resolved — not actually a bug.
- **Investigation**: Step 3 raw responses were missing for most tests, while Step 4 and Step 6 logged consistently. Suspected logging bug.
- **Root cause**: `decompose_query` short-circuits via `MULTI_INTENT_PATTERNS` regex check and returns `make_fallback(query)` locally for single-intent queries — never calls Gemini, so no log written. Only T4 ("how many films...") was matching a multi-intent pattern (`\bhow many\b`).
- **Action taken**: Added a one-line diagnostic print to surface which pattern matched when the LLM path is taken. Kept for visibility into future test runs:
  ```python
  matched = next((p for p in MULTI_INTENT_PATTERNS if p.search(query)), None)
  if matched is None:
      return make_fallback(query)
  print(f"  [decomposer] matched pattern: {matched.pattern}")
  ```
- **Open question**: Whether `\bhow many\b` should match for "how many films were shot in the 80s" — this is a single-intent query and could fallback locally. Pattern set may be over-firing. Worth revisiting alongside multi-task test design.

---

## Model Swap — Validated

Switched code generator and filter extractor from prior Gemini model to `gemini-3.1-flash-lite-preview`.

**Verdict**: Working well. Audit of Step 4 raw responses across all ten tests confirmed lite-preview produces structurally correct predicates for every shape — flat attribute, AND tree, OR tree, spatial value object, virtual `Actor` field (correctly leaving expansion to post-processor), null for open-ended rank. Step 6 codegen quality is also clean: proper guarded string masks, numeric coercion for Year, correct spatial reprojection workflow, melt-based actor counting for ranking.

**Trade-off**: Lite-preview emits responses as bare arrays where prior models wrapped — hence the F6 validator fix. Once that fix is in, the model is a net positive: faster, cheaper, no observed correctness regressions on single-task queries.

**Caveat**: Multi-task and nested queries have not been tested with lite-preview yet. Re-evaluate when those test categories come online.

---

## Final Test Results (April 20, 19:51 run — post-fixes)

| Test | Outcome | IR shape verified |
|------|---------|-------------------|
| T1 | ✓ Pass | `Director == "alfred hitchcock"` |
| T2 | ✓ Pass | `Locations contains "market st"` |
| T3 | ✓ Pass | OR-expanded actor tree (post-processor verified) |
| T4 | ✓ Pass | `Year between [1980, 1989]` |
| T5 | ✓ Pass | `predicate: null` (correct for open-ended rank) |
| T6 | ✓ Pass | `Year == 1985` |
| T7 | ✓ Pass | AND tree, two clauses |
| T8 | ✓ Pass | Spatial predicate with geocoded coordinates (resolver verified) |
| T9 | ✓ Pass | `Title contains "vertigo"` |
| T10 | ✓ Pass | `Year between [1990, 1999]` |

Numerical answers match April 18/19 runs across all tests, confirming the architectural fix did not change correctness — only the path to it.

---

## Carried-Forward Items (Not Addressed This Session)

### B2. `==` → `contains` operator swap (now in codegen, not Step 4)
- **Status update**: Step 4 now correctly emits `op: "=="` on string fields. The bug has migrated to Step 6 — codegen still translates `==` on Director/Title as `str.contains(value, case=False)` rather than equality.
- **Impact**: Same as before. Silent on current dataset (no substring collisions). Will misfire on real queries like "Sean Penny" matching `contains("sean penn")`.
- **Next step**: Codegen prompt enhancement, or a post-processor on the generated code. Deferred.

### `data` shape variance across task kinds
- **Observation**: Lite-preview standardizes shape *within* a kind but varies *across* kinds: retrieve → `{records, count}`, count → `{count, count_basis}`, rank → `{ranking, rank_dimension, rank_basis, N}`. Internally consistent, externally undocumented.
- **Decision needed**: Document the contract or standardize via prompt. Defer until downstream consumers exist.

### I1, I2, I3 (from April 19 handoff)
- All still open. None encountered in this session — all three Gemini calls completed cleanly across all ten tests. Worth keeping in the priority queue for the next harness improvement pass.

---

## Recommended Next Session

1. **Re-run T1–T10 single-task suite** to confirm stability of the April 20 fixes across multiple runs. Determinism check.
2. **Begin multi-task and nested-query test suite (Phase 2)**. This will stress lite-preview on Step 4's structural complexity in ways T1–T10 did not — `dependsOn` chains, compare tasks, retrieve→count pipelines. The right moment to discover whether the model swap holds up.
3. **Tackle B2** if multi-task tests don't reveal something more urgent first. Step 6 prompt or post-processor — open question which.

---

## Files Changed This Session

- `code_generation_v2.2.md` — added invariant 23
- `step-6-code-gen-progress-report_changelog.md` — added v2.2 changelog entry for invariant 23
- `pipeline_e2e_testing.ipynb` — patched `extract_filters` (envelope normalization), patched `decompose_query` (diagnostic print)

---

