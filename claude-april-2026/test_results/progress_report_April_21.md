# Session Summary — April 21–22, 2026

**Context**: Follow-up to April 20 handoff (T1–T10 single-task suite passing legitimately). Goals for this session: Phase 2 test design, one targeted IR fix, housekeeping.

---

## Test Suite Expansion

### T11–T20 designed, run, and debriefed
Phase 2 focused on predicate edge cases and first multi-task probes.

| Test | Theme | Outcome |
|------|-------|---------|
| T11 | Same-field OR (Director OR Director) | Clean pass |
| T12 | Exact title match intent | Passed via B2 policy (contains) |
| T13 | Title substring retrieval | Passed, low-cardinality |
| T14 | Multi-value director cell | Passed — only reachable via contains |
| T15 | Location abbreviation variance | Passed but didn't stress variant handling |
| T16 | Null / missing-field predicate | Passed; exposed IR contract hole |
| T17 | Cross-field OR (Director OR Locations) | Clean pass — architectural milestone |
| T18 | Retrieve + count dependency (film granularity) | Clean pass |
| T19 | Retrieve + count dependency (location granularity) | Clean pass |
| T20 | Cross-field AND with mixed predicates | Clean pass |

**Headline results**: cross-field OR, cross-field AND, and first dependency-chain tests (T18/T19) all worked end-to-end. Step 4 emits proper predicate trees, Step 6 preserves them, execution succeeds.

### Phase 2 scorecard (honest)
- **Strong passes**: T11, T16, T17, T18, T19, T20
- **Good but less diagnostic**: T13, T15
- **Passed because of B2 policy, not correctness of intent**: T12, T14

---

## B2 Reclassified — Policy, Not Bug

While reading `code_generation_v2.2.md` to draft a Step 6 patch, discovered that string `==` → guarded `str.contains(...)` translation is **documented policy** (line 476), not a bug. Justified by dirty source data (casing, whitespace, multi-value comma-joined cells in Director).

**Implications**:
- T14 (Michel Brezis found in multi-director cell) works *because* of this policy, not despite it.
- Changing `==` behavior would silently regress T14-class queries.
- If ever fixed, fix must be **additive**: add a new operator (e.g., `exact`) for strict equality. Do not modify `==`.
- Priority: deferred indefinitely. Revisit only if a real query produces a user-visible wrong answer traceable to this policy.

A formal B2 status note was drafted for inclusion in project docs.

---

## IR Extension — `is_null` / `is_not_null`

**Motivation**: T16 ("films with no listed director") previously worked only because Step 6 was generous with a malformed `{op: "==", value: null}` leaf. Contract hole.

### Step 4 v1.1 changes
- Added `is_null` and `is_not_null` to allowed ops (unary, no `value` key).
- v1 scope: `Director` and `Writer` only.
- New field-mapping rule 9: absence language ("no listed director," "without a director," "missing director," "unknown director," same forms for writer).
- New strict rule 13 (unary shape enforcement).
- New few-shot example.
- Validator updated: `VALID_OPS` extended, new `UNARY_OPS` and `NULL_CAPABLE_FIELDS` sets, rejection of `value` key on unary ops, rejection of unary ops on non-null-capable fields.

### Step 6 v2.3 changes
- Section C3: operators table extended with two rows; leaf clause shape updated to note `value` is absent for unary ops.
- Section D2: added two cookbook entries (`is_null` mask and `is_not_null` mask), both using the four-way absence pattern (`isna()` | empty-after-strip | stringy-nulls).
- D2 Summary bullet added.

### Verification
T16 passed on both the Step-4-only change (Step 6 inferred the pattern correctly from general pandas idiom — nice surprise, documented as motivation rather than relied on) and the bundled Step 4 + Step 6 change. Manually verified against the DB: one film (Chef Dynasty: House of Fang, 2022).

T1–T20 regression run: all still pass, no new failures.

---

## Logging Regression — Fixed

**Discovery**: Execution logging was inconsistent across test runs. Turned out `code_gen_result.log` writes were baked into the **generated code itself** via a block in Section D1 of the codegen prompt. Model sometimes emitted the block, sometimes didn't. Worse, the write lived inside the generated function's `try` block — failures never logged.

**Fix**: Moved logging to the execution harness. New `_append_exec_log` and `_format_exec_log_entry` helpers in `execute_code`. Logs timestamp, query, success flag, summary, metadata, serialized result data (truncated at 2k chars), and generated code — unconditionally, regardless of success or failure.

**Next step**: Remove the filesystem-write block from Section D1 of the codegen prompt to prevent the model from duplicating the write. Grep project for other consumers of `code_gen_result.log` before removing.

---

## Known Open Issues (Unchanged from April 20)

### I1 — No LLM retry wrapper (urgent, deferred by user)
Most recent T1–T10 run hit 503s on T2 and T10. Step 4 fell back to null predicates silently; Step 6 reverse-engineered predicates from `source` text and produced correct answers by luck. Scoreline showed 10/10 but real score was 8/10 + 2 silent-recoveries. Same silent-failure pattern as the pre-F6 April 20 state. User choice to defer; revisit soon.

### Other carried-forward
- Negation operator — not in IR, no tests yet. Decision point before next test batch.
- `data` shape variance across task kinds — documented, not standardized.
- Bare-array response normalization shim in Step 4 — load-bearing, do not remove without reviewing.

---

## Next-Session Plan (User-Stated)

1. Decide on negation (add to IR, or test as expected-red).
2. Extend AND/OR coverage — 8–10 single-task tests, mixed field pairs, some nested.
3. Clarify scope of "map-oriented tests" before drafting.
4. Multi-task Phase 3 — retrieve+retrieve+compare, retrieve+rank, nested chains. Own batch, own session.
5. Out-of-distribution sidecar suite — low priority, graceful-refusal grading.
6. I1 (LLM retry wrapper) — will need to land before map/multi-task work if 503s continue.

---

## Files Changed This Session

- Step 4 filter extractor prompt (`is_null`/`is_not_null` added)
- Step 4 validator (`UNARY_OPS`, `NULL_CAPABLE_FIELDS`, new rejection rules)
- `code_generation_v2.2.md` → v2.3 (C3 operators table, D2 cookbook entries, D2 summary)
- `execute_code` in pipeline harness (`_append_exec_log`, `_format_exec_log_entry` helpers)
- Changelogs: Step 4 v1.1, Step 6 v2.3
- B2 status reclassification note (policy, not bug)

---

Drop this into project resources as-is, or edit as needed. The next thread should start by deciding on negation — that's the gating decision for the next test batch.