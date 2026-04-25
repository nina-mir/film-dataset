# Bug Report — End-to-End Pipeline Testing

**Date**: April 19, 2026
**Status**: Handoff doc for new chat thread
**Context**: Three runs of the T1–T10 test suite (April 17, 18, 19) against the 5-step preprocessing IR + Step 6 codegen pipeline.

---

## Latest Run Results (April 19)

**9/10 passed, 1/10 failed** — but the score is misleading. Real state is **8 genuinely correct + 1 silent failure + 1 deterministic bug**.

| Test | Outcome | Notes |
|------|---------|-------|
| T1 | ✓ Pass | Correct — 4 Hitchcock films |
| T2 | ✓ Pass | Normalizer working end-to-end — 29 films on Market St |
| T3 | ✗ **Silent failure** (reported success) | Step 4 503 → null-fallback → returned all 337 films, not Sean Penn's |
| T4 | ✓ Pass | 39 films in the 80s |
| T5 | ✗ Fail (reproducible) | `AttributeError: 'dict' object has no attribute 'to_dict'` |
| T6 | ✓ Pass | 4 films from 1985 |
| T7 | ✓ Pass | 1 Hitchcock film in the 1950s (Vertigo) |
| T8 | ✓ Pass | 189 films within 1 mi of Coit Tower, invariant 22 held |
| T9 | ✓ Pass | 16 Vertigo locations |
| T10 | ✓ Pass | First real pass — Robin Williams top at 8 films in 90s |

---

## Fixed Bugs

### F1. T2 data normalization wiring (f-string variant unused)
- **Status**: Fixed in Step 1 (`normalize_query`) and data load.
- **Fix**: Street suffix normalizer applied on both query and `Locations` column. Was returning the un-normalized string from `normalize_query`; one-line fix to return `normalized` instead of `' '.join(words)`.
- **Verification**: T2 now returns 29 films with "market street" query (was 23 previously; missing 6 rows with "Market St." variant).

### F2. T8 runtime IR access (invariant 22)
- **Status**: Fixed in `code_generation_v2.md` as invariant 22 (v2.1).
- **Fix**: Added hard invariant: values from IR in summary strings must be inlined as literals, not read from `task_results` at runtime.
- **Verification**: T8 across runs 2 and 3 produces `f"...within 1 mile of Coit Tower."` — literal, not lookup. No more `KeyError: 'predicate'`.

### F3. `execute_code` silent-success detection gap
- **Status**: Fixed in the pipeline harness.
- **Fix**: Added `internal_error` check — if `metadata.error` is set on the returned dict, mark pipeline as failed instead of success.
- **Verification**: T5 failure is now correctly flagged as `✗ FAILED` (previously reported `✓ SUCCESS` with error summary).

### F4. T2 f-string literal-newline syntax error (invariant 21)
- **Status**: Fixed in `code_generation_v2.md` as invariant 21 (v2.1).
- **Fix**: Added hard invariant forbidding literal newlines in string literals; require `\n` escape instead.
- **Verification**: T2 run 2 and 3 no longer produce the `SyntaxError: unterminated f-string literal`.

---
## B2 Status — April 21, 2026

**Reclassification: policy, not bug.**

`code_generation_v2.2.md` line 476 documents string `==` → guarded `str.contains(...)` translation as an intentional design choice, justified by dirty data in the source columns (casing, whitespace, formatting variance; comma-joined multi-value cells in Director).

T11–T20 run confirmed this is working as designed:
- T14 returned Michel Brezis from a multi-director cell — only reachable via `contains`.
- T12 and T15 passed on non-colliding substrings; the policy introduces no false positives on the current dataset.

**Known limitation.** The policy will produce false positives on queries where the user's intent is strict equality and the dataset contains substring collisions (hypothetical "the film called the rock" matching a "rockstar" title). None observed in current data.

**If ever fixed, the fix is additive.** Do not change `==` behavior. Add a new IR operator for strict equality (e.g., `exact`) and route linguistically-strict phrasings ("the film *called* X," "titled exactly X") to it. Changing `==` would silently regress T14-class queries where permissive matching is doing useful work.

**Priority.** Deferred indefinitely. Revisit only if a real query produces a user-visible wrong answer traceable to this policy.
---

## Reproducible Bugs (deterministic, next to fix)

### B1. T5 double-conversion on rank tasks
- **Severity**: High (consistent failure on rank tasks)
- **Type**: Prompt / codegen pattern bug
- **Signature**: `AttributeError: 'dict' object has no attribute 'to_dict'`
- **Root cause**: Codegen stores `top_directors.to_dict()` in `task_results["t1"]["result"]["ranking"]` (pandas Series → dict). Then reads it back as `final_ranking` and calls `.to_dict()` on it again in the outer `result['data']`. The second conversion fails because the value is already a dict.
- **Evidence of determinism**: T5 generated code is **byte-identical** between run 2 (April 18) and run 3 (April 19). At `temperature=0` with identical IR, Gemini produces the same output.
- **Proposed fix**: Two new prompt invariants in Section B of `code_generation_v2.md`:
  - Invariant 23: `data` field must always be a list of dicts for retrieve tasks, scalar for count, dict for rank. No `to_json()` strings.
  - Invariant 24: Once a value is stored in `task_results[...]['result']`, do not apply additional `.to_dict()`, `.tolist()`, or `.to_json()` to it when assembling the outer `result`.


### B2. `==` → `contains` operator swap on string fields
- **Severity**: Medium (produces correct answers on current data, but will fail on substring collisions)
- **Type**: Prompt / codegen translation bug
- **Signature**: IR says `op: "=="`, generated code uses `str.contains(value, case=False)` instead of equality.
- **Affected tests**: T1 (Director), T7 (Director clause), T9 (Title) — consistently across runs
- **Why it's silent**: No substring collisions exist in the current dataset ("Alfred Hitchcock", "Sean Penn", "Vertigo" have no longer matching names). Will misfire on real queries where substring collisions exist ("Sean Penny" matched by `contains("sean penn")`).
- **Proposed fix**: This is the deferred **item 3** from the working plan. Requires Step 4 prompt enhancement to distinguish intent (named-entity `==` vs substring-search `contains`) based on linguistic cues:
  - "films by X", "films titled X" → `==`
  - "films whose title contains X", "with the word X" → `contains`
  - Locations field has special default: `contains` unless user explicitly says "exactly"

### B3. Step 3 `rank` misclassified as `retrieve`
- **Severity**: Low (codegen improvises correctly)
- **Type**: Step 3 prompt contract violation
- **Signature**: Queries like "top 5 directors", "actors who appeared in the most films" get `kind: "retrieve"` instead of `kind: "rank"`.
- **Affected tests**: T5, T10 — consistently
- **Why it's silent**: Codegen LLM reads the `source` text ("top 5", "most films"), ignores the IR kind, and writes rank logic anyway. Output is correct but the IR contract is violated.
- **Proposed fix**: Step 3 prompt enrichment with clearer rank-detection rules. Low urgency since codegen covers for it, but worth fixing for long-term contract integrity.

---

## LLM-Issue / Infra-Limitation Bugs (not your code)

### >I1 — RESOLVED April 22, 2026. Structured error handling + retry wrapper shipped. Silent null-predicate fallback removed. See progress_report_April_22_10pm.md for details and live evidence (T11 cleanly short-circuited on 503). Follow-up: same bug class still present in Step 3 (I1-step3) and Step 6 (I1-step6, softer variant — fails loudly but inconsistently).

### I1. Step 4 silent null-predicate fallback on API errors
- **Severity**: **Critical** (produces wrong answers that look right)
- **Type**: Pipeline design flaw + upstream API instability
- **Signature**: Step 4 filter extractor hits 503 or 429, catches the exception, returns `predicate: null` as fallback. Downstream can't distinguish "legitimate no-filter IR" from "Step 4 crashed."
- **Latest evidence**: T3 April 19 — query "films with sean penn" → 503 → `predicate: null` → codegen returned all 337 films → pipeline marked `✓ SUCCESS`. Comment in generated code even acknowledges the tension: *"The natural language query 'films with sean penn' suggests a filter, but the provided IR's predicate is authoritative."*
- **Across three runs**: T3 failed differently every time. Run 1: OR expansion worked (no API error). Run 2: JSON envelope broke (Gemini output quality). Run 3: 503 → silent wrong answer. Only stable property is that something goes wrong.
- **Proposed fix**: This is **item 6** from the working plan — build a retry/backoff wrapper for LLM calls:
  - 503 → silent retry with exponential backoff (2–3 attempts)
  - 429 per-minute → surface to user with retry delay from response payload
  - 429 daily-quota exhausted → clear message, no retry
  - Remove the `predicate: null` fallback entirely. On exhausted retries, return a structured failure (`{"error": "extractor_unavailable", "step": 4, "retry_after": N}`) and let the orchestrator short-circuit.
  - Consider adding `predicate_confidence: "extracted" | "fallback"` to future-proof the distinction if silent fallback is ever truly needed.

### I2. Gemini JSON envelope malformation
- **Severity**: Medium (blocks codegen on affected runs)
- **Type**: Pure model output quality
- **Signature**: `json.JSONDecodeError: Unterminated string starting at: line 2 column 11`
- **Affected test**: T3 run 2 only. Run 1 and run 3 produced valid JSON for the same IR.
- **Root cause**: Model emitted an unterminated string inside its JSON response envelope. Likely an unescaped quote inside the `"code"` field's string value. Entirely a Gemini output quality issue, not something prompt-fixable.
- **Proposed mitigation**: Not fixable in prompt. Best handled by the same retry wrapper as I1 — if `json.loads` on the response fails, regenerate once. This converts a flaky 2/3 pass rate into ~95%+ without needing the model to be better.

### I3. Free-tier daily quota exhaustion
- **Severity**: Infra limitation, not a code bug
- **Type**: Gemini free tier (`generate_content_free_tier_requests`, limit 20/day)
- **Signature**: `429 RESOURCE_EXHAUSTED`, `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`
- **Affected runs**: Run 1 T10 (cascade), run 2 T10. Not hit in run 3.
- **Mitigation**: Distinguish daily-quota from per-minute throttle by parsing `quotaId` in the retry wrapper. Per-minute → retry after `retryDelay`. Daily → error message suggesting upgrade or tomorrow, no retry.

---

## Priority Order for Next Session

1. **I1 — LLM retry wrapper + remove silent null-fallback.** Highest impact. Eliminates silent-wrong-answer category entirely. Turns T3 into either correct answer or honest "service unavailable."

2. **B1 — Two-invariant prompt edit (shape + re-conversion).** Smallest effort-to-impact ratio. Fixes T5 permanently. ~20 min of prompt work.

3. **B2 — Step 4 intent-based operator selection.** Biggest prompt engineering job. Addresses the silent ==/contains swap that will bite real user queries. Deferred intentionally.

4. **B3 — Step 3 rank detection.** Low urgency, nice-to-have. Safe to leave until after B1 and B2.

---

## Run-Over-Run Determinism Notes

Useful signal for future debugging:

- **Gemini at `temperature=0` is mostly deterministic per-IR.** T1, T6, T7 generated code byte-identical between runs 2 and 3. T9 had only cosmetic variation (comment wording, import placement).
- **T5 byte-identical across runs 2 and 3** — confirms it's a prompt-level pattern bug, not variance.
- **T3 was unstable because its upstream (Step 4) was unstable** — variance came from the API, not from Gemini output choice.
- **Implication**: For reproducing bugs in the new chat thread, rerunning is usually safe. For truly flaky cases, the instability is almost always infrastructure (503/429), not the model itself.

---

## Relevant Files

- `code_generation_v2.md` — prompt, updated through v2.1 (invariants 21, 22 added)
- `step-6-code-gen-progress-report_changelog.md` — changelog for v2.1
- `code_gen_result_April_19.log` — full log of run 3
- `screen_printout_april_19.txt` — summary output of run 3
- `April_19_gen_code_for_T1_to_T10_tests.json` — generated code per test from run 3
- `APRIL_18_full_tests_gen_code_for_T1_to_T10_tests__1_.json` — run 2 generated code (for diff comparisons)
- as of now we do not have access to the full response objet from the llm API but it will be produced for future test runs.