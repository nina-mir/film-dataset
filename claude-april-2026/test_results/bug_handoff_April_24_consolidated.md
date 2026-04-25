# Bug Handoff Report — Consolidated

**Date compiled:** April 24, 2026
**Purpose:** Single source of truth for every bug and issue raised across all test sessions (April 17 – April 24). Supersedes `bug_report_handoff.md` and `Bug_report_April_20.md`.
**Sources reviewed:** `bug_report_handoff.md`, `Bug_report_April_20.md`, `progress_report_April_21.md`, `progress_report_April_22_10pm.md`, `progress_report_April_24_llm_resiliency_full_refactor_of_llm_steps.md`, Step 1/2/5 progress reports.

---

## Fixed Bugs

### F1 — T2 data normalization wiring (f-string variant unused)

- **Symptom:** Query "films shot on market street" returned 23 films instead of 29; six rows with "Market St." variant were missed.
- **Fixed:** April 17–19 session.
- **Where:** `normalize_query` (Step 1) and data load. Street-suffix normalizer applied on both query and `Locations` column.
- **How:** Returned `normalized` instead of `' '.join(words)` — one-line fix that had been wired to the wrong variable.

### F2 — T8 runtime IR access (invariant 22)

- **Symptom:** Spatial queries threw `KeyError: 'predicate'` when summary strings tried to read predicate values from `task_results` at runtime.
- **Fixed:** April 18–19 session.
- **Where:** `code_generation_v2.md`, added as invariant 22 (v2.1).
- **How:** Hard invariant forbidding IR values from being read at runtime for summary strings; must be inlined as literals during code generation.

### F3 — `execute_code` silent-success detection gap

- **Symptom:** T5 was reported as `✓ SUCCESS` with an error summary attached; harness didn't notice the execution had internally failed.
- **Fixed:** April 18–19 session.
- **Where:** Pipeline harness, `execute_code`.
- **How:** Added `internal_error` check — if `metadata.error` is set on the returned dict, mark the pipeline run as failed.

### F4 — T2 f-string literal-newline syntax error (invariant 21)

- **Symptom:** Generated code produced `SyntaxError: unterminated f-string literal` when f-strings contained literal newlines.
- **Fixed:** April 18–19 session.
- **Where:** `code_generation_v2.md`, added as invariant 21 (v2.1).
- **How:** Hard invariant forbidding literal newlines inside string literals; requires `\n` escape sequence instead.

### F5 — B1: T5 double-conversion on rank tasks

- **Symptom:** Rank tasks threw `AttributeError: 'dict' object has no attribute 'to_dict'`. Generated code applied `.to_dict()` twice — once at storage into `task_results`, once when reading it back into the outer `result`.
- **Fixed:** April 20 session.
- **Where:** `code_generation_v2.2.md`, added as invariant 23.
- **How:** Hard invariant forbidding additional type conversions (`.to_dict()`, `.tolist()`, `.to_json()`, `dict(...)`, `list(...)`) on values already stored in `task_results[...]['result']`. Conversion happens exactly once, at point of storage. Executor-level coercion was considered and rejected — the `AttributeError` fires inside the generated function's try/except, so the executor never sees a result to coerce; prompt-level fix was the only viable path. Verification: T5 ran clean on first test post-fix, and has passed on every run since.

### F6 — Step 4 bare-array envelope mismatch

- **Symptom:** Every Step 4 call silently fell back to null predicates because the validator couldn't find the expected `{"tasks": [...]}` wrapper. Tests "passed" because the codegen LLM reverse-engineered predicates from natural-language `source` text — the architectural anti-pattern the refactor was supposed to eliminate.
- **Fixed:** April 20 session.
- **Where:** `extract_filters` in the pipeline harness (four-line fix).
- **How:** Added a `isinstance(result, list)` check after `json.loads`; wraps bare arrays into `{"tasks": result}` before validation runs. `gemini-3.1-flash-lite-preview` returns Step 4 responses as bare arrays where earlier models wrapped by convention. Verification: actor-expansion post-processor now reaches T3, geocoding resolver now reaches T8 with coordinates populated.

### F7 — Step 3 missing-log diagnostic (not a bug)

- **Symptom:** Step 3 raw-response files were missing for most tests while Step 4 and Step 6 logged consistently. Suspected logging bug.
- **Fixed:** April 20 session.
- **Where:** `decompose_query` in the pipeline harness.
- **How:** Not a bug — `decompose_query` short-circuits via `MULTI_INTENT_PATTERNS` regex check and doesn't call Gemini for single-intent queries. Added a one-line diagnostic print that surfaces which pattern matched when the LLM path is taken. Still in use today.

### F8 — Execution-harness logging regression

- **Symptom:** Execution logs were unreliable across runs — sometimes written, sometimes not, depending on where the failure occurred.
- **Fixed:** April 21 session.
- **Where:** `execute_code` in the execution harness.
- **How:** Moved logging out of the generated code into the execution harness itself. New helpers `_append_exec_log` and `_format_exec_log_entry` write timestamp, query, success flag, summary, metadata, serialized result data (truncated at 2k chars), and generated code — unconditionally, success or failure.

### F9 — I1: Silent null-predicate fallback on Step 4 API errors

- **Symptom:** Step 4 catches exceptions (503, 429, etc.) and returns `predicate: null`. Downstream cannot distinguish "legitimate no-filter query" from "Step 4 crashed." T3 April 19 evidence: 503 → `predicate: null` → codegen returned all 337 films → pipeline reported `✓ SUCCESS` with the wrong answer.
- **Fixed:** April 22 evening.
- **Where:** `llm_resilience.py` (new standalone module), `call_gemini_safely` adapter, refactored `extract_filters`.
- **How:** Built shared LLM resilience layer with structured exception classification (`GeminiInfraError`, `GeminiQuotaPerMinuteError`, `GeminiQuotaDailyError`, `GeminiClientError`, `GeminiUnknownError`); retry policy with exponential backoff and jitter for 503/timeout (3 attempts), server-directed retry for per-minute 429s (capped at 90s), no retry for daily quota or 4xx. Silent null-predicate fallback removed from `extract_filters`; replaced with the `{ok, result, error}` envelope pattern. Verification: T11 (April 22 late-evening) cleanly short-circuited on a structured 503 — first live evidence of the new behavior.

### F10 — I1 (Step 3 variant): Silent single-task fallback on Step 3 API errors

- **Symptom:** Step 3 caught any exception (including 503) and returned `make_fallback(query)` — a single-task `retrieve` plan. On two-intent queries like "films on larkin street and how many are there," the `count` task silently disappeared. T18/T19 April 22 evidence: Step 3 503 → fallback dropped the count → pipeline reported `✓ SUCCESS` while only answering half the user's question.
- **Fixed:** April 24.
- **Where:** Refactored `decompose_query` cell in `pipeline_e2e_testing_post_llm_resiliency.ipynb`.
- **How:** Replaced bare `call_gemini` with `call_gemini_safely(stage="step3")`. `make_fallback` removed from the LLM path (function deleted from the notebook entirely after validation window). Added structured `parse` and `validation` failure kinds. Verification: T18/T19 passed cleanly across three independent test sessions with correct two-task `retrieve → count` plans intact.

### F11 — I1 (Step 6 variant): Raw-error-dict dump and no retry on Step 6 API errors

- **Symptom:** Step 6 caught exceptions via bare `except Exception` and stringified the raw error dict into the user-facing message. No retry. April 24 afternoon evidence: during a real Gemini infra outage, T1/T2/T4 all hit 503 on Step 6 and surfaced as `Code generation failed: 503 UNAVAILABLE. {'error': {'code': 503, ...}}` — raw, unretried, unstructured. Same outage saw refactored Step 4 retry three times and surface cleanly.
- **Fixed:** April 24.
- **Where:** Refactored `generate_code` cell in `pipeline_e2e_testing_post_llm_resiliency.ipynb`.
- **How:** Replaced bare `call_gemini` with `call_gemini_safely(stage="step6")`. Structured `parse` and `validation` failure kinds. Preserved the regex-based JSON-extraction fallback for markdown-fenced responses (legitimate LLM-quirk recovery, not a silent-success mechanism). Verification: 20/20 on first end-to-end test run with all three refactors in place; T20, which 503'd in an earlier run, passed cleanly.

### F12 — I2: Gemini JSON envelope malformation

- **Symptom:** `json.JSONDecodeError: Unterminated string` on occasional Step 4 responses. Entirely a model-output quality issue, not prompt-fixable. T3 April 19 run 2 only.
- **Fixed:** April 22 (Step 4), April 24 (Steps 3, 6).
- **Where:** All three envelope-aware step functions.
- **How:** Subsumed by the LLM resilience envelope. Malformed JSON now surfaces as `kind: "parse"` structured failure with raw-response logging for post-mortem. Deliberately one-shot (not retried) — policy is honest surfaced failure rather than optimistic regeneration.

### F13 — I3: Free-tier daily quota exhaustion

- **Symptom:** `429 RESOURCE_EXHAUSTED` with `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`. Affected multiple April 18–19 runs.
- **Fixed:** April 22 (Step 4), April 24 (Steps 3, 6).
- **Where:** `llm_resilience.py`, specifically the retry policy in `call_gemini_with_retry`.
- **How:** Subsumed by the LLM resilience envelope. Daily-quota 429s are distinguished from per-minute 429s by parsing `quotaId`; daily → no retry, raises `GeminiQuotaDailyError` immediately with user-facing hint "Daily quota exhausted. Try again tomorrow or upgrade the API plan." Per-minute → obey server's `retryDelay` + 3s buffer.

---

## Pending Bugs / Open Items

### B3 — Step 3 misclassifies `rank` queries as `retrieve`

- **Severity:** Low. Produces correct answers today.
- **Signature:** Queries like "top 5 directors with the most films" and "actors who appeared in the most films in the 90s" get `kind: "retrieve"` from Step 3 instead of `kind: "rank"`.
- **Why it's low severity:** Step 6 reads the natural-language `source` text ("top 5", "most films"), ignores the IR's stated `kind`, and writes ranking logic. Output is correct.
- **Why it matters anyway:** The invariant "Step 3 `kind` is authoritative" is violated on every rank query. Costs: (a) Step 6's correct behavior is coincidental, depending on the codegen LLM overriding the IR — will break if the prompt is ever tightened to enforce IR fidelity; (b) telemetry keyed on `kind` will undercount rank queries; (c) any future pipeline component that trusts the IR (caching layer, router, validator) will make wrong decisions on rank queries.
- **Affected tests:** T5, T10 — consistently across all runs.
- **Proposed fix:** Step 3 prompt enrichment with clearer rank-detection rules (trigger phrases: "top N", "most", "least", "ranked by", "highest", "lowest").

### B4 — Step 5 metric-vs-location disambiguation over-fires

- **Severity:** Low. Edge case documented in Step 5 progress report.
- **Signature:** Query "where are the most filming locations" has both a location signal ("where are") and a metric pattern ("most filming locations"). Metric suppression wins, resolving granularity to `film` — arguably wrong for a "where" query.
- **Why it's low severity:** Not observed in any T1–T20 test; emerged during Step 5 design review.
- **Proposed fix:** In Step 5 resolver, check whether location and metric patterns refer to the same text span before letting metric suppress location.

### OBS-1 — No visibility into silent retry successes

- **Type:** Observability gap, not a bug.
- **Signature:** When the resilience layer retries a 503 and succeeds on attempt 2 or 3, the success envelope returns `{"ok": True, "text": "...", "error": None}` with no indication that retries happened. This is intentional ("invisible on success path") but loses useful telemetry.
- **Proposed enhancement:** Surface `attempts` on success envelopes so dashboards can count silent-retry-recovery events. Small cross-cutting change touching all three step functions plus the test-harness printout.

### LIMIT-1 — Query normalizer has no word-merger

- **Type:** Known limitation, documented in `query_normalizer_progress_report.md`.
- **Signature:** Queries with split words ("int he" → "in the") are not repaired by Step 1. Currently handled by downstream LLM tolerance.
- **Why it's a limitation not a bug:** Downstream steps have been robust to this so far. Worth fixing if a real query fails because of it.

### LIMIT-2 — Multi-task test coverage for lite-preview is limited

- **Type:** Test coverage gap, carried forward from April 20.
- **Signature:** `gemini-3.1-flash-lite-preview` was validated on T1–T10 (single-task) at April 20, extended to T11–T20 (Phase 2, multi-task) at April 21. The April 24 variance runs added further confidence, but nested / deeply-dependent queries (3+ tasks with interdependencies) remain unexplored.
- **Why it matters:** Each new task-shape class stresses the Step 3 prompt in new ways. A Phase 3 test design would be the natural next coverage expansion.

---

## Reclassified — Policy, Not Bug

### B2 — `==` → `contains` translation on string fields

- **Original classification:** Bug. Step 4 emitted `op: "=="` but codegen translated to `str.contains(value, case=False)` instead of equality.
- **Reclassified:** April 21, after reading `code_generation_v2.2.md` line 476 which documents this as intentional design.
- **Rationale:** Dirty source data — casing variance, whitespace, comma-joined multi-value Director cells. T14 (Michel Brezis in a multi-director cell) succeeds *only* because of this policy. Strict equality would silently regress T14-class queries.
- **Known limitation:** Will produce false positives on substring collisions (hypothetical "the film called the rock" matching a "rockstar" title). None observed in current dataset.
- **If ever fixed:** Must be additive. Add a new IR operator (e.g., `exact`) and route linguistically-strict phrasings ("the film *called* X," "titled exactly X") to it. Do not change `==` semantics.
- **Priority:** Deferred indefinitely. Revisit only if a real query produces a user-visible wrong answer traceable to this policy.

---

## Summary

| Category | Count |
|---|---|
| Bugs fixed | 13 (F1–F13) |
| Pending open items | 4 (B3, B4, OBS-1, LIMIT-1, LIMIT-2 — note B4 and OBS-1 are low-severity; LIMIT items are acknowledged gaps) |
| Policy reclassifications | 1 (B2) |

**Current state:** Pipeline is shippable. All silent-wrong-answer classes are closed (F9, F10, F11). All three LLM-touching steps (3, 4, 6) share the uniform resilience envelope. No high- or medium-severity bugs remain open. Remaining items are contract-integrity improvements, observability enhancements, and test coverage expansion.
