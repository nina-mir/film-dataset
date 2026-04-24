# Progress Report — April 24, 2026

## Full LLM Resiliency Refactor of All LLM-Touching Steps

**Focus:** Completing the LLM resiliency envelope across every remaining LLM-touching step (Step 3 Task Decomposer, Step 6 Code Generator) after the Step 4 baseline shipped on April 22.
**Status:** All three LLM steps (3, 4, 6) now share a uniform resilience envelope. Proven against T1–T20 across four test sessions today, including one unplanned field test during a real Gemini infra outage.

---

## Why This Was Needed

Before today, the pipeline had **three LLM-touching steps with three different failure behaviors.** The April 22 Step 4 refactor closed the most critical gap (silent null-predicate fallback on 503, producing confident wrong answers). Steps 3 and 6 still had their original ad-hoc error handling.

The afternoon test run on April 24 made the inconsistency dramatically visible in a single printout. Gemini 3.1 Flash Lite Preview went into a sustained 503 episode during variance testing. On the *same* run, from the *same* outage, three different user experiences emerged:

- **Step 4 (refactored on April 22):** T5–T10 all hit 503. The resilience layer retried three times per query, classified each failure as `kind=infra, status=503, retryable=True, attempts=3`, and short-circuited with a clean user-facing message — "The model service is temporarily unavailable. Try again shortly." No silent fallback IR. No fake success.
- **Step 6 (unrefactored):** T1, T2, T4 hit 503. Each died on the first attempt — no retry. The error surfaced as a raw stringified Python dict: `Code generation failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently...`. Messy, unstructured, unretrieved.
- **Step 3 (unrefactored on April 22):** Would have silently fallen back to a single-task `retrieve` plan on any 503, producing confidently wrong IR. Didn't happen to trigger in this particular outage, but the silent-fallback code path was still present in the module.

Same underlying infra event; three different user experiences. That inconsistency was the case for extending the envelope to Steps 3 and 6.

A second consideration was the T18 and T19 silent-fallback class documented in `bug_report_handoff.md` (item I1, Step 3 variant). These queries — "films on larkin street and how many are there" and "show filming locations for time after time and how many locations are there" — decompose into a two-task `retrieve → count` plan with a `dependsOn` chain. On any Step 3 LLM failure, the old `make_fallback` path dropped the `count` intent entirely and returned a single-task `retrieve` plan. The pipeline then produced a list of films without counting them, and reported `✓ SUCCESS`. The user asked two questions and got one answer, with no indication anything went wrong. This is the exact concrete user-harm pattern the envelope was designed to prevent.

---

## Architecture

The resilience layer is a three-tier stack. Today's work did not change the bottom two tiers — it extended the top tier (per-step error handling) to cover every LLM-touching step.

### Tier 1 — Structured provider layer (`llm_resilience.py`, shipped April 22)

A standalone module providing classification, retry, and backoff for Gemini calls. Unchanged today.

- **Structured exceptions.** `GeminiInfraError`, `GeminiQuotaPerMinuteError`, `GeminiQuotaDailyError`, `GeminiClientError`, `GeminiUnknownError`. Each carries `status_code`, `retry_after_s`, `attempts`, `model`, `raw_details`.
- **`call_gemini_once`** — single shot with classification. Raises structured exceptions; never returns `None` or a silent fallback.
- **`call_gemini_with_retry`** — owns retry policy:
  - 503 / timeout / connection → exponential backoff with jitter, 3 attempts max
  - 429 per-minute → obey server's `retryDelay` + 3s buffer, capped at 90s
  - 429 daily quota → no retry, raise immediately
  - 4xx (other) → no retry, raise immediately
- **`attempts` counts total tries**, not just retries (agreed convention).

### Tier 2 — Notebook integration adapter (`call_gemini_safely`, shipped April 22)

A thin wrapper that bridges the notebook's existing `call_gemini` to the retry layer and returns a uniform success/failure envelope:

```python
# success
{"ok": True,  "text": "...", "error": None}

# failure (flat, no nesting)
{"ok": False, "text": None,
 "error": {"stage", "kind", "status_code", "retryable", "attempts",
           "retry_after_s", "message", "model"}}
```

The adapter preserves the existing `_save_raw_response` post-mortem plumbing, so every successful LLM call still writes its raw response to Google Drive as before. This was important: the existing post-mortem trail remained intact across the refactor.

### Tier 3 — Per-step envelope (today's work: Steps 3, 4, 6)

Every LLM-touching step function now returns a uniform envelope:

```python
# success — per-step result shape
{"ok": True, "result": <step-specific payload>, "error": None}

# failure — structured, honest
{"ok": False, "result": None,
 "error": {flat dict: stage, kind, status_code, retryable, attempts,
           retry_after_s, message, model}}
```

On top of the five provider-layer failure `kinds` inherited from `call_gemini_safely` (`infra`, `quota_per_minute`, `quota_daily`, `client_error`, `unknown`), each step adds its own content-validation `kinds`:

- **Step 3** (`decompose_query`): `parse` (JSON didn't decode), `validation` (schema check via `validate_task_plan` failed).
- **Step 4** (`extract_filters`): `parse`, `validation` (schema check failed).
- **Step 6** (`generate_code`): `parse` (JSON didn't decode, including after the regex-extraction fallback attempt), `validation` (JSON decoded but the `code` field is empty or missing).

Content-validation failures are **not** retried. The baseline policy is honest failure rates first; retry can be layered on later if real-world data justifies it.

The orchestrator (`run_preprocessing_pipeline` + `run_full_pipeline`) unwraps each envelope. On `ok=True`, it extracts `result` and continues. On `ok=False`, it short-circuits immediately with a structured failure payload: `{error: True, failed_stage: 'stepN', stage_error: <flat envelope>, message: str}`. Downstream stages, post-processors, and execution are all skipped. The test harness summary branches on `failed_stage` and prints `Step N <kind> (status=..., attempts=...)` uniformly.

### What the envelope explicitly replaced

Three ad-hoc error-handling patterns are gone from the pipeline:

1. **Step 3's `make_fallback(query)`** — silently returned a single-task `retrieve` plan on any exception. Removed (commented for now, pending deletion after validation window). This was the code path behind the T18/T19 silent-wrong-answer class.
2. **Step 4's silent null-predicate fallback** — set `predicate: null` on any exception, letting codegen return all 337 films as if no filter had been requested. Removed April 22.
3. **Step 6's bare `except Exception` with stringified dict.** Replaced today with structured classification. The regex-based JSON-extraction recovery path (for when Gemini wraps its response in markdown fences) is **preserved** — this was always a legitimate recovery from a known LLM output quirk, not a silent-success fallback. The distinction matters: preserving useful recovery logic is different from eliminating silent failure.

---

## How a 503 Now Behaves in Any Step

**Scenario:** Gemini returns HTTP 503 on the LLM call inside any of Steps 3, 4, or 6.

1. **Provider layer sees the 503.** `call_gemini_once` classifies the exception, raises `GeminiInfraError(status_code=503, retryable=True)`.
2. **Retry layer catches it.** `call_gemini_with_retry` sleeps with exponential backoff + jitter and tries again. Up to three attempts total.
3. **Outcome depends on what happens during the retries.** Two possibilities:
   - **A transient — service recovers on retry 2 or 3.** The retry layer gets a successful response. From the caller's perspective, the call succeeded silently. The only trace that retry happened at all is the `attempts` field on the envelope (not visible on success; the success envelope doesn't surface attempt count). The user sees a slightly slower but otherwise normal response.
   - **A sustained outage — all three attempts fail.** The retry layer re-raises the `GeminiInfraError`. The adapter catches it and builds the structured failure envelope: `{"ok": False, "error": {"stage": "stepN", "kind": "infra", "status_code": 503, "retryable": True, "attempts": 3, "retry_after_s": null, ...}}`.
4. **Step function short-circuits on `ok=False`.** No content-level processing. No attempt to salvage. Returns the envelope to the orchestrator.
5. **Orchestrator prints the structured failure:**
   ```
   [step_name] Provider failure: kind=infra status=503 attempts=3 retryable=True

   ❌ Pipeline stopped (Step N infra): Step N failed: infra (status=503, attempts=3)
      → The model service is temporarily unavailable. Try again shortly.
   ```
6. **Test-harness summary mirrors this:** `✗ TN: <test name>` → `→ Step N infra (status=503, attempts=3)`.

**What doesn't happen:** no fake `✓ SUCCESS`. No empty-filter IR passed to downstream. No raw Python dict stringified into the user's face. No burning of the `dependsOn` chain in Step 3.

This behavior was field-tested this afternoon during the infra outage. Step 4 calls on T5–T10 all showed `attempts=3` before surfacing as structured infra failures, exactly as the design specifies.

---

## How a Malformed JSON in Step 3 or Step 4 Now Behaves

**Scenario:** The Gemini LLM call returns HTTP 200 but the response body is not valid JSON. This happens occasionally even at `temperature=0` — unterminated strings, unescaped quotes, truncation.

1. **Provider layer returns success.** `call_gemini_safely` returns `{"ok": True, "text": "<malformed body>", "error": None}`.
2. **Step function attempts `json.loads`.** Fails with `json.JSONDecodeError`.
3. **Step function builds a structured `parse` failure envelope** (not retried — no point retrying a syntactically-broken response from a deterministic model; the same response would come back).
   ```python
   {"ok": False, "result": None,
    "error": {"stage": "step3" | "step4",
              "kind": "parse",
              "status_code": None,
              "retryable": False,
              "attempts": 1,
              "retry_after_s": None,
              "message": "JSONDecodeError: <exception detail>",
              "model": MODEL_NAME}}
   ```
4. **Step function also prints a debugging preamble** before returning — the first 500 characters of the raw response get logged so the failure can be post-mortemed against the saved raw-response JSON file on Google Drive.
5. **Orchestrator short-circuits.** Same printout shape as the 503 case, but the kind is `parse`:
   ```
   [decomposer / filter_extractor] JSON parse failure: <details>
   [decomposer / filter_extractor] Raw response (first 500 chars): ...

   ❌ Pipeline stopped (Step N parse): Step N failed: parse (status=None, attempts=1)
   ```

No hint message follows (parse failures don't get the "try again shortly" suggestion — they're not transient). The user sees an honest "something went wrong with the model's response" signal rather than a silent fallback producing wrong data.

**Separately — schema-valid-JSON-but-wrong-shape (the `validation` kind).** If JSON decodes but `validate_task_plan` (Step 3) or the filter-schema check (Step 4) rejects the structure, the flow is identical except `kind` is `validation` and `message` describes what the schema rejected. Rejected payloads are also logged for post-mortem.

---

## How Malformed Code from Step 6 Now Behaves

Step 6 has two distinct content-failure modes. Both get the envelope treatment.

**Scenario A — Gemini returns unparseable JSON.**

Very similar to the Step 3/4 parse case, with one twist: Step 6 has always had a defensive regex-extraction fallback to handle the case where the model wraps its JSON response in ```json … ``` markdown fences. This fallback is **preserved** in the refactored version. Flow:

1. Try `json.loads(response_text)`. If it succeeds, proceed to validation.
2. If it fails, try `re.search(r'\{.*\}', response_text, re.DOTALL)` to extract a JSON-looking block. If found, attempt `json.loads` on that. If it succeeds, proceed.
3. If both fail, return a `kind: "parse"` envelope with an appropriate message (`"no JSON object found in response"` or `"JSONDecodeError after extraction: ..."`).

The key point: the regex fallback is recovery from a known LLM output quirk, not a silent-success mechanism. If it can't recover a valid JSON object, it surfaces the parse failure honestly rather than fabricating a success.

**Scenario B — Gemini returns valid JSON but the `code` field is empty or missing.**

The LLM sometimes returns `{"code": "", "explanation": "…"}` when it encounters an IR it can't translate (a malformed predicate, an unsupported task kind, etc.). The old code treated this as a soft error with a generic message. The refactored version returns a `kind: "validation"` envelope:

```python
{"ok": False, "result": None,
 "error": {"stage": "step6",
           "kind": "validation",
           "status_code": None,
           "retryable": False,
           "attempts": 1,
           "retry_after_s": None,
           "message": "LLM returned empty `code` field",
           "model": MODEL_NAME}}
```

The orchestrator short-circuits and reports `Step 6 validation`. Execution is skipped (obviously — there's no code to execute).

**What doesn't happen:** the old behavior of returning `{'error': True, 'message': 'LLM returned empty code field', 'raw': '...'}` and relying on callers to check `.get('error')` is gone. The envelope is uniform with the rest of the pipeline now.

---

## Validation Summary

Four T1–T20 sessions today against `sf_film_May7_2025_data.gpkg`, MODEL_NAME = `gemini-3.1-flash-lite-preview`, dataset = 337 films (1,618 location rows):

| Session | Scope | Outcome | Signal |
|---|---|---|---|
| Morning, ~04:07 UTC | Step 3 refactor only | 20/20 | First pass confirmation |
| Afternoon, ~05:07 UTC | Step 3 refactor, variance probe | 1/10 on T1–T10 | **Unplanned field test.** Gemini infra outage. T1/T2/T4 hit Step 6 503 (unrefactored) → raw error dumps, no retry. T5–T10 hit Step 4 503 (refactored) → three-retry behavior, structured failures, clean user-facing message. The contrast in a single printout was the clearest motivation for finishing Step 6. |
| Evening, ~18:57 UTC | Step 3 refactor, variance re-run | 20/20 | Second clean pass. Byte-level variance analysis: structural decisions identical, minor comment drift (healthy). |
| Late evening, ~20:53 UTC | All three refactors (3, 4, 6) | 20/20 | First end-to-end validation with the full resiliency envelope in place. T20 — which 503'd on Step 6 in the morning run — passed cleanly. |

**Key findings:**

- **Silent-fallback classes closed.** The T18/T19 silent-wrong-answer pattern (documented as I1-step3 in `bug_report_handoff.md`) is gone. Both queries passed cleanly in three independent sessions with correct two-task `retrieve → count` plans and `dependsOn` intact. The Step 4 variant of this class was already closed on April 22; the Step 6 variant (which is a softer "fails loudly but inconsistently" case) is now symmetric with the other two.
- **Retry layer works under real adverse conditions.** The afternoon outage produced field evidence of `attempts=3` behavior on Step 4. Some retries may have absorbed transient 503s silently on other runs; no way to know from the logs unless we want to surface `attempts` on success (a design question for later).
- **LLM variance is healthy.** At `temperature=0`, Gemini 3.1 Flash Lite Preview produces byte-identical Step 4 predicates across runs and byte-identical or lightly comment-drifted Step 6 code. Structural decisions are stable; stochasticity appears only in comment wording and variable names. This is the right kind of variance for a production pipeline.
- **Existing post-mortem plumbing is intact.** Raw response JSON files continued to be saved throughout the refactor (visible in every [Step N] block as `Successfully saved to .../raw_responses/...json`). No infrastructure for debugging was lost.

---

## What Is and Is Not Done

**Done:**

- Steps 3, 4, and 6 all share the uniform envelope (`{ok, result, error}`).
- Orchestrator short-circuits on `ok=False` from any LLM step with a structured, kind-specific failure message.
- Test harness summary treats all three steps uniformly.
- The Step 3 `make_fallback` silent path is removed from the LLM path (commented in the source for rollback safety during validation window — pending outright deletion).
- Step 6's regex-extraction recovery for markdown-fenced JSON is preserved.

**Deferred (not done today, not regressed):**

- **B1** — T5 rank task `to_dict()` double-conversion. Two prompt invariants still pending in `code_generation_v2.md`. The bug is still visible in every T5 run (pipeline succeeds because codegen improvises from the `source` text, but the IR contract is violated).
- **B2** — Documented as *policy, not bug* in `bug_report_handoff.md` as of April 21. The `==` → `contains` translation is intentional design to handle dirty data (casing variance, comma-joined multi-value Director cells). Revisit only if a real query produces a user-visible wrong answer.
- **B3** — Step 3 rank detection (queries like "top 5 directors" get `kind: "retrieve"` instead of `kind: "rank"`). Low urgency; Step 6 correctly improvises from `source` text. Nice-to-have contract-integrity fix.
- **Multi-intent pattern enrichment** — the "either X or Y" phrase in T17 does not trigger `MULTI_INTENT_PATTERNS`, so T17 always short-circuits Step 3. Current Step 4 handles the disjunction correctly via cross-field OR, so this produces correct answers; worth tracking as a prompt-enrichment candidate if the pattern library is ever revisited.

**Intentionally not addressed:**

- Surfacing `attempts` on success envelopes (would give visibility into silent-retry-recovery events but changes the success-payload shape across all three steps).
- Content-validation retry policy (parse and validation failures are one-shot; could be given a single retry at higher temperature if empirical data justifies it).
- Step 6 envelope-aware codegen regeneration on `kind: "parse"` or `kind: "validation"` (could try once with a re-prompt that includes the rejected output as context; not warranted yet).

---

## Files Changed

See the companion changelog: `llm_resiliency_refactor_changelog_April_24.md`.
