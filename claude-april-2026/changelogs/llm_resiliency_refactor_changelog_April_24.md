# LLM Resiliency Refactor — Changelog

Running changelog of the LLM resilience envelope work. Reverse-chronological by date; within a date, grouped by component.

---

## April 24, 2026 — Steps 3 and 6 refactor

### `decompose_query` (Step 3, `pipeline_e2e_testing_with_llm_resiliency.ipynb`)

- Replaced bare `call_gemini` with `call_gemini_safely(stage="step3")`.
- Return type changed: now always returns `{"ok": bool, "result": dict | None, "error": dict | None}`. Deterministic short-circuit path (no multi-intent match) returns `{"ok": True, "result": {"tasks": [...]}, "error": None}` without calling the LLM.
- Added content-validation failure kinds: `parse` (JSON decode failure), `validation` (schema check via `validate_task_plan` failed). Neither is retried.
- Added raw-response and rejected-payload logging on failure (first 500 chars) for post-mortem.
- **Removed from the LLM path:** the `make_fallback(query)` call on any exception. This was the silent single-task `retrieve` fallback that dropped the `count` intent on T18/T19 when Step 3 hit a 503.
- `make_fallback` function definition commented out in source (not deleted — rollback safety during the validation window).
- Old version preserved as commented block at bottom of cell for diffing.

### `generate_code` (Step 6)

- Replaced bare `call_gemini` with `call_gemini_safely(stage="step6")`.
- Return type changed: now always returns `{"ok": bool, "result": dict | None, "error": dict | None}`. On success, `result` is `{"code": str, "explanation": str}`.
- Replaced generic `except Exception` with structured classification from the resilience layer.
- Added content-validation failure kinds:
  - `parse` — JSON decode failure after the regex-extraction recovery attempt also fails
  - `validation` — JSON decoded but `code` field is empty or missing
- **Preserved:** the regex-based JSON-extraction fallback (`re.search(r'\{.*\}', ...)`) for recovering from markdown-fenced responses. This is not a silent-success path — if extraction fails, a structured `parse` envelope is returned.
- Old version preserved as commented block at bottom of cell.

### `run_preprocessing_pipeline` (orchestrator, Steps 1–5)

- Added envelope unwrap for Step 3: `decompose_envelope["result"]` extracted on `ok=True`; short-circuit on `ok=False` with `failed_stage: 'step3'`.
- Removed the outdated comment "NOTE: Step 3 still uses the legacy fallback path."
- No other changes; Step 4 handling (shipped April 22) untouched; Steps 1/2/5 unchanged.

### `run_full_pipeline` (orchestrator, end-to-end)

- Added envelope unwrap for Step 6: `codegen_envelope["result"]` extracted on `ok=True`; short-circuit on `ok=False` with `failed_stage: 'step6'`.
- Step 6 failure shape stored on `pipeline_result['ir']` (not `pipeline_result['codegen']`) so the existing test-harness `failed_stage` branching catches Step 6 uniformly.
- Upstream IR preserved on `pipeline_result['ir']['preprocessing_ir']` for post-mortem on Step 6 failures.
- Printout grew `step3` and `step6` branches alongside the existing `step4` branch.
- Kind-specific user-facing hints refactored into a shared helper `_print_kind_hint(kind, err)`:
  - `infra` → "The model service is temporarily unavailable. Try again shortly."
  - `quota_per_minute` → "Try again in about ~N seconds." (N derived from `retry_after_s + 5`)
  - `quota_daily` → "Daily quota exhausted. Try again tomorrow or upgrade the API plan."
  - `parse` / `validation` / `client_error` / `unknown` → no hint (structured line above is self-explanatory)

### `run_test_suite` (test harness)

- Failure summary now branches uniformly on `failed_stage ∈ {'step3', 'step4', 'step6'}`. Each prints `→ Step N <kind> (status=<code>, attempts=<n>)`.
- Removed the legacy `elif codegen.get('error'):` branch (no longer reachable after the Step 6 refactor — structured failures live on `ir['stage_error']`).
- `step2` (safety gate) branch preserved.
- Fallback execution-error branch preserved for codegen-success-but-execution-failure cases.

---

## April 22, 2026 — Step 4 refactor + shared resilience layer (baseline)

### `llm_resilience.py` (new standalone module)

- Structured exceptions: `GeminiInfraError`, `GeminiQuotaPerMinuteError`, `GeminiQuotaDailyError`, `GeminiClientError`, `GeminiUnknownError`. Each carries `status_code`, `retry_after_s`, `attempts`, `model`, `raw_details`.
- `call_gemini_once` — single-shot call with classification; raises structured exceptions, never returns silent fallback.
- `call_gemini_with_retry` — retry policy:
  - 503 / timeout / connection → exponential backoff with jitter, max 3 attempts
  - 429 per-minute → obey server's `retryDelay` + 3s buffer, capped at 90s, max 3 attempts
  - 429 daily quota → no retry, raise immediately
  - 4xx other → no retry, raise immediately
- `attempts` counts total tries, not just retries.
- Coverage: 30 unit tests against a mock provider, all passing in ~4ms. No real network, no real `time.sleep`.

### `call_gemini_safely` (notebook integration adapter)

- Thin wrapper bridging the existing `call_gemini` to the retry layer.
- Returns the uniform envelope `{"ok": bool, "text": str | None, "error": dict | None}`.
- Preserves existing `_save_raw_response` post-mortem plumbing on success.

### `extract_filters` (Step 4)

- Replaced silent null-predicate fallback with envelope-aware error handling.
- Returns `{"ok", "result", "error"}` envelope.
- Content-validation kinds: `parse`, `validation`. Not retried.
- Removed the pattern where `predicate: null` was returned on any exception, which had let codegen return all 337 rows as if no filter had been requested.

### `run_preprocessing_pipeline` and `run_full_pipeline` (orchestrator, initial envelope wiring)

- Step 4 envelope unwrap added; short-circuit on `ok=False` with `failed_stage: 'step4'`.
- Failure printout: kind, status_code, attempts, kind-specific user-facing hint.
- Existing `if isinstance(ir, dict) and ir.get('error')` check recognizes the new failure shape without modification.

### `run_test_suite` (test harness, initial envelope wiring)

- Summary correctly handles `pipeline_result['codegen'] is None` on Step 4 short-circuit.
- Distinguished Step 4 structured failures from Step 6 legacy failures from execution failures.

---

## Validation history

| Date | Session | Scope | Result | Key finding |
|---|---|---|---|---|
| Apr 22 | Evening | Step 4 refactor baseline | 19/20 + 1 honest 503 | T11 cleanly short-circuited on structured 503 — first live evidence of the envelope working |
| Apr 24 | Morning | Step 3 refactor, first pass | 20/20 | T18, T19 passed with two-task `retrieve → count` plans intact — silent-fallback class closed |
| Apr 24 | Afternoon | Step 3 refactor, variance | 1/10 (infra outage) | Unplanned field test. Step 4 retried three times on every 503; Step 6 (unrefactored) surfaced raw dicts. Contrast motivated same-day Step 6 refactor. |
| Apr 24 | Evening | Step 3 refactor, variance re-run | 20/20 | Byte-level variance stable: structural decisions identical across runs, minor comment drift. |
| Apr 24 | Late evening | Steps 3 + 4 + 6 refactor, end-to-end | 20/20 | First clean run with full envelope in place. T20 (which 503'd in Step 6 in the morning run) passed cleanly. |

---

## Files

**Refactored today:**

- `pipeline_e2e_testing_with_llm_resiliency.ipynb` — cells for `decompose_query`, `generate_code`, `run_preprocessing_pipeline`, `run_full_pipeline`, `run_test_suite`.

**Shipped April 22 (unchanged today):**

- `llm_resilience.py` — standalone module.
- Notebook integration cells for `call_gemini_safely` and the Gemini provider adapter.

**Related documentation:**

- `progress_report_April_24_llm_resiliency_full_refactor_of_llm_steps.md` — this refactor's architecture and behavior documentation.
- `progress_report_April_22_10pm.md` — Step 4 baseline refactor.
- `bug_report_handoff.md` — bug/issue inventory; I1 (Step 4 variant) resolved April 22; I1-step3 resolved April 24.
