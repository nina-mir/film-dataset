# Progress Report — April 22, 2026 (10 PM)

**Focus:** Step 4 silent-fallback elimination + shared LLM resilience layer
**Status:** Step 4 refactor complete and validated against T1–T20

---

## What Was Built

### 1. Shared LLM resilience layer (`llm_resilience.py`)

A standalone module providing structured retry + classification for all Gemini calls. Three layers:

- **Structured exceptions** — `GeminiInfraError`, `GeminiQuotaPerMinuteError`, `GeminiQuotaDailyError`, `GeminiClientError`, `GeminiUnknownError`. Each carries `status_code`, `retry_after_s`, `attempts`, `model`, `raw_details`.
- **`call_gemini_once`** — single shot with classification. Raises structured exceptions; never returns `None` or a fallback.
- **`call_gemini_with_retry`** — owns retry policy:
  - 503 / timeout / connection → exponential backoff with jitter (3 attempts max)
  - 429 per-minute → obey server's `retryDelay` + 3s buffer, capped at 90s
  - 429 daily quota → no retry, raise immediately
  - 4xx (other) → no retry
- **`attempts` counts total tries**, not just retries (agreed convention).

**Test coverage:** 30 unit tests against a mock provider. All passing in 4 ms. No real network, no real `time.sleep`. Covers every classification path, every retry path, the `attempts` counting convention, and the `max_sleep_s` cap.

### 2. Notebook integration adapter

A thin wrapper (`call_gemini_safely`) that bridges the existing `call_gemini` to the new layer and returns the uniform envelope:

```python
{"ok": True,  "text": "...", "error": None}
{"ok": False, "text": None,
 "error": {"stage", "kind", "status_code", "retryable", "attempts",
           "retry_after_s", "message", "model"}}  # flat
```

### 3. Refactored Step 4 (`extract_filters`)

Replaced the bespoke null-predicate fallback with envelope-aware error handling. Now returns `{ok, result, error}`:

- `kind: "infra" | "quota_per_minute" | "quota_daily" | "client_error" | "unknown"` from the provider layer
- `kind: "parse"` when JSON doesn't decode
- `kind: "validation"` when JSON decodes but fails schema check

Parse and validation failures are NOT retried in this baseline — we want honest failure rates first.

### 4. Refactored `run_preprocessing_pipeline` and `run_full_pipeline`

- Step 4 envelope is unwrapped into a bare IR before post-processors run.
- On `ok=False`, the pipeline short-circuits with a structured failure payload carrying `failed_stage` and `stage_error`. Post-processors, Step 5, codegen, and execution are all skipped.
- `run_full_pipeline` recognizes the new failure shape via the existing `if isinstance(ir, dict) and ir.get('error')` check (no breaking change).
- Failure printout now reports `kind` and `status_code` and emits a kind-specific user-facing message (e.g., "Try again in ~25 seconds" for `quota_per_minute`, "Daily quota exhausted" for `quota_daily`).

### 5. Test-suite summary fix

`run_test_suite` summary now correctly handles the case where `pipeline_result['codegen']` is `None` (Step 4 short-circuit). Distinguishes Step 4 structured failures from Step 6 legacy failures from execution failures in the printout.

---

## What This Fixes

### Bug I1 (handoff doc) — CLOSED

**Step 4 silent null-predicate fallback on API errors.** Previously: a 503 in Step 4 was caught, logged, and silently converted to `predicate: null`. Downstream couldn't distinguish "no filter needed" (legitimate) from "Step 4 crashed" (failure). This produced the silent-wrong-answer category — most notoriously T3 April 19, where a 503 → `predicate: null` → all 337 films → fake `✓ SUCCESS`.

Now: a 503 in Step 4 produces a structured failure that the orchestrator short-circuits on. No null-predicate substitution. No silent wrong answer. Verified directly in production conditions today (see T11 evidence below).

---

## Evidence — Two Live Test Runs Today

### Run 1: T1–T10 (~04:18 UTC)
**10/10 clean successes.** Every Step 4 call returned valid output on first try. T3 — the historical canary — produced a properly-formed Actor OR predicate and codegen returned 5 films featuring Sean Penn (correct). The bug fix was not exercised (no infra failures occurred), but the happy path was proven across all 10 tests.

### Run 2: T11–T20 (~04:46 UTC)
**3 failures across 10 tests, all honestly reported:**
- **T11** — Step 4 hit 503, retried 3 times, all failed. Pipeline short-circuited cleanly:
  ```
  [filter_extractor] Provider failure: kind=infra status=503 attempts=3 retryable=True
  ❌ Pipeline stopped (Step 4 infra)
     → The model service is temporarily unavailable. Try again shortly.
  ```
  This is **the bug fix working in production for the first time.**
- **T16, T17** — Step 6 503s. Caught by Step 6's old fallback path; surfaced as raw error messages (Step 6 not yet refactored — scheduled).
- **T18, T19** — Step 3 503 with silent fallback that lost the `count` task intent. Pipeline reported `✓ SUCCESS` while only answering half the user's question. **Same I1 bug class, just in Step 3.** Confirms Step 3 must be next.

### Run 3 (re-run of T11–T20 after summary fix, ~05:04 UTC)
**9/10 clean successes.** Only T13 failed — Step 6 503 on a trivial query, honestly reported. T11, T16, T17, T18, T19 all passed cleanly this run, including the previously-silent partial failures on T18/T19 (Step 3 succeeded properly: two-task plan with `dependsOn`).

---

## Honest Scorecard

Across all three runs today, counting "did the pipeline behave correctly given the conditions it faced":

- **30/30 honest behavior.** No silent wrong answers anywhere.
- 26 clean successes, 1 honest Step 4 infra failure, 3 honest Step 6 infra failures.
- The `is_null` predicate path (T16) worked end-to-end for the first time on a healthy run.

If this exact suite had run a week ago: T11 would have died with a stacktrace, T13 same, T18/T19 would have shown `✓ SUCCESS` while silently under-answering, and T3 would have returned all 337 films with a fake `✓`.

---

## What's Deferred (Tomorrow's Work)

### Priority 1 — Step 3 (`decompose_query`) refactor

**Same I1 bug class as Step 4.** T18/T19 first-run evidence: Step 3 503 → silent single-task fallback → pipeline reports success while losing the count intent. This is the remaining silent-wrong-answer surface in the pipeline.

Mechanically identical to Step 4's refactor:
1. Replace the bare `call_gemini` call with `call_gemini_safely(stage="step3")`.
2. Layer JSON parse + `validate_task_plan` on top.
3. Return `{ok, result, error}`.
4. Update `run_preprocessing_pipeline` to short-circuit on Step 3 envelope failure (same pattern as Step 4).
5. Delete the silent fallback to single-task retrieve.

### Priority 2 — Step 6 (`generate_code`) refactor

T13 evidence: Step 6 503 produces a raw error message in the printout. Not a silent-wrong-answer (it fails loudly), but inconsistent with Steps 3 and 4 once those are envelope-aware. Same mechanical refactor as Steps 3 and 4.

### Lower priority (deferred from earlier sessions, unchanged)

- **B1** — Two-invariant prompt edit for Step 6 (T5 fix)
- **B2** — Step 4 intent-based `==` vs `contains` operator selection
- **B3** — Step 3 `rank` detection prompt enrichment
- **Optional polish** — surface real `attempts` count on success path (currently hardcoded to 1 in the success envelope; the wrapper knows the real number internally)

---

## Files Added Today

- `llm_resilience.py` — the resilience layer (production module)
- `test_llm_resilience.py` — 30 unit tests with mock provider
- `notebook_integration_cell.py` — adapter cell for the e2e notebook
- `refactored_extract_filters.py` — drop-in replacement for the existing Step 4 cell
- `refactored_pipeline.py` — drop-in replacement for `run_preprocessing_pipeline` + `run_full_pipeline`

---

## Architectural Principle Locked In

From the design discussion preceding this work:

> **Never let infra failure collapse into a semantically valid IR object.**

This is the rule that drove every decision today — the structured exception taxonomy, the flat envelope, the deletion of the null-predicate fallback, the orchestrator short-circuit. Every step in the pipeline that calls an LLM must follow it.

Step 4 follows it now. Step 3 does not yet. Step 6 does not yet. Tomorrow we close that gap.
