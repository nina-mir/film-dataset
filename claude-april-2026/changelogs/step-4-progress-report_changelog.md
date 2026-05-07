# Filter Extractor — Development Report

**Date**: April 10, 2026
**Status**: Step 4 of 5-step preprocessing pipeline refactoring — complete
**Environment**: Google Colab (standalone development, ready for integration)

---

## What Was Built

An LLM-based filter extractor that takes each decomposed task from Step 3 and attaches the smallest predicate tree defining which rows in the GeoDataFrame are relevant. It is the first schema-aware step in the pipeline and the second LLM-based step overall.

## How It Works

### Core principle

For each task, Step 4 answers one question: **what must be true of a row for this task to consider it relevant?** It extracts only row constraints. It does not encode ranking, grouping, projections, comparison behavior, or response shape.

### Input

The task plan from Step 3 — an array of tasks with `id`, `kind`, `source`, and optionally `dependsOn`.

### Output

The same task array with a `predicate` field attached to each task. The predicate is a recursive boolean tree or `null`.

```json
{
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films by alfred hitchcock from the 1950s on sutter st",
      "predicate": {
        "logic": "AND",
        "clauses": [
          {"field": "Director", "op": "==", "value": "alfred hitchcock", "type": "attribute"},
          {"field": "Year", "op": "between", "value": [1950, 1959], "type": "attribute"},
          {"field": "Locations", "op": "contains", "value": "sutter st", "type": "attribute"}
        ]
      }
    }
  ]
}
```

### Predicate tree format

Replaced the old `{filters, filter_logic}` flat format with a recursive `{logic, clauses}` tree. This handles flat and nested boolean logic (OR inside AND, etc.) with one structure, and makes actor expansion trivial — splice in an OR node.

### Actor virtual field

The LLM emits `"field": "Actor"` for general actor/starring references. A deterministic post-processor expands this to `Actor_1 OR Actor_2 OR Actor_3`. The LLM never emits Actor_1/2/3 directly unless the source explicitly says "lead actor."

## Key Design Decisions

- **Constraint vs. output dimension.** The prompt's most important rule teaches the LLM to distinguish between row constraints and the thing being asked about. "Films by Hitchcock" → Director is a constraint. "Which directors filmed on Geary St" → Director is the output dimension, not a constraint. "Top 5 directors with the most filming locations in 1982" → only Year is a constraint. This is the single biggest source of subtle bugs in the old monolithic prompt.
- **Predicate tree over flat format.** The old `filters + filter_logic` format was awkward for OR-inside-AND. The recursive tree is actually simpler — one structure for all cases — and composes cleanly with actor expansion.
- **Predicates attach to tasks.** Each task carries its own predicate, preserving the DAG structure from Step 3. No reassembly needed downstream.
- **Dependency context without filter copying.** When a task has `dependsOn`, the LLM receives parent task source text for resolving references like "there" and "those films." But it never copies parent filters into the child predicate — execution inheritance happens later.
- **Null predicates are valid.** Compare tasks, purely referential dependent tasks, clarify tasks, and open-ended rank tasks all get `predicate: null`. This is not an error.
- **Vague spatial → Locations contains.** Only explicit distance/radius language (e.g., "within 1 mile of") triggers `geometry` + `within_distance`. Vague words like "near", "around", "at" use `Locations contains`. This avoids fake precision with the current point-geometry data.
- **Preserve normalized values.** The prompt's input guarantees section states that all values arrive normalized and lowercase from Step 1. The LLM is instructed not to re-case, expand names, or invent fuller forms. This keeps the boundary clean between normalization (Step 1) and extraction (Step 4).
- **Strict actor expansion.** The post-processor raises TypeError/ValueError on malformed input rather than silently passing through. This surfaces upstream bugs early.

## Test Results

**17 total tests across multiple categories:**

| Category | Tests | Result |
|----------|-------|--------|
| Simple single-field constraint | 1 | ✅ |
| Multi-constraint AND | 1 | ✅ |
| OR logic | 1 | ✅ |
| Constraint vs. output dimension | 3 | ✅ |
| Actor virtual field | 1 | ✅ |
| Spatial (explicit radius) | 1 | ✅ |
| Spatial (vague → Locations) | 1 | ✅ |
| Dependent tasks | 2 | ✅ |
| Compare → null | 1 | ✅ |
| No filters → null | 1 | ✅ |
| Year comparison (after/before) | 1 | ✅ |
| Title search | 1 | ✅ |
| Writer field | 1 | ✅ |
| Preserve lowercase values | 1 | ✅ |

### Actor expansion post-processor tests (deterministic, no LLM)

| Test | Result |
|------|--------|
| Basic Actor → Actor_1/2/3 OR expansion | ✅ |
| Nested OR/AND with Actor inside | ✅ |
| None and non-Actor leaf pass-through | ✅ |
| Malformed input raises errors | ✅ |

### Key test cases

| Input | Expected | Result |
|-------|----------|--------|
| "films directed by alfred hitchcock" | Director == | ✅ |
| "films by alfred hitchcock from the 1950s on sutter st" | Director + Year between + Locations | ✅ |
| "films by alfred hitchcock or francis ford coppola on mission st" | OR node inside AND | ✅ |
| "top 5 directors with the most filming locations in 1982" | Year only, Director NOT a filter | ✅ |
| "which directors filmed on geary st" | Locations only, Director NOT a filter | ✅ |
| "films with clint eastwood on geary st" | Actor (virtual) + Locations | ✅ |
| "films within 1 mile of coit tower" | geometry + within_distance | ✅ |
| "films near golden gate bridge" | Locations contains, NOT geometry | ✅ |
| "films shot on valencia st" + "how many are there" | t1 has filter, t2 is null | ✅ |
| "films shot on pacific avenue" + "why is vertigo associated with that area" | t2 has Title only, no parent copy | ✅ |
| "actors who appeared in the most films in the 90s" | Year between only, Actor NOT a filter | ✅ |
| "films by steven spielberg" | value stays lowercase "steven spielberg" | ✅ |

## Prompt Design

- Input guarantees section establishing that normalization already happened
- Schema with dtypes and meanings, plus virtual Actor field
- Capabilities section listing what the system can actually execute
- "Most important rule" section with 3 worked examples of constraint vs. output dimension
- Recursive predicate tree format with allowed ops table
- 8 field mapping rules
- Dependency rules (3 rules for handling dependsOn)
- Per-task-kind guidance (6 kinds)
- 9 few-shot examples
- 12 strict rules
- ~4,200 characters total

## Allowed ops (v1)

| op | use |
|----|-----|
| `==` | exact match on resolved person, title, or single year |
| `contains` | partial text match (Locations, Title, Fun_Facts) |
| `between` | year range or decade |
| `>` `<` `>=` `<=` | year comparisons |
| `within_distance` | explicit distance/radius |

## Allowed fields

`Title`, `Year`, `Locations`, `Fun_Facts`, `Director`, `Writer`, `Actor` (virtual), `geometry`

## Validation

Every LLM response is validated before use:
- Top-level `tasks` array present
- Task count matches input
- All input task IDs present in output
- No duplicate IDs
- Required keys preserved (`id`, `kind`, `source`)
- `source` and `dependsOn` not modified from input
- Valid `kind` values
- Predicate structure: recursive validation of logic nodes and leaf clauses
- Valid fields, ops, and types at every leaf
- Spatial clauses require `geometry` field, `spatial` type, and `{reference_place, distance, unit}` value
- `between` requires 2-element list

If validation fails, the system falls back to all tasks with null predicates — graceful degradation, no crash.

## Architecture Note: NLP Planner

With the predicate tree IR now carrying structured tasks, per-task predicates, and (after Step 5) granularity flags, the NLP Planner (Stage 2 of the old pipeline) may no longer be necessary. The code generator can consume the IR directly. This will be tested when the code generation prompt is rewritten. If the code generator produces accurate results without the English-language plan, the NLP planner will be dropped — reducing total LLM calls to 3 (decomposer + filter extractor + code generator) instead of 4.

## Performance Notes

- LLM path: ~1-2s per call (Gemini 2.5 Flash)
- Free-tier rate limit: 10 RPM — test suite uses 8s delay between LLM calls

## Files

- `filter_extractor_dev.ipynb` — Colab notebook with prompt, extraction function, validation, actor expansion, and test suite

## Integration Path

```python
# In src/pandas_script.py → preprocess_query()
from src.filter_extractor import extract_filters, expand_actors_in_result

def preprocess_query(self, user_query):
    # Step 1: Normalize
    norm_result = normalize_query(user_query, self.known_values)
    cleaned = norm_result['normalized']

    # Step 2: Safety Gate
    gate = safety_check(cleaned)
    if not gate['safe']:
        return {'error': True, 'message': gate['message'],
                'requested_operation': gate['blocked_by']}

    # Step 3: Task Decomposer
    task_plan = decompose_query(cleaned)

    # Step 4: Filter Extractor
    filter_result = extract_filters(task_plan)
    filter_result = expand_actors_in_result(filter_result)

    # Step 5: Granularity / Dedup Resolver (next step)...
    ...
```

The prompt goes into `instructions/filter_extractor.md` and gets loaded by `SystemInstructions`.

## Next Step

**Step 5: Granularity / Dedup Resolver** — rule-based (no LLM). Examines the task plan and attaches `{"granularity": "film" | "location", "dedup": true | false}` to the IR. After Step 5, the full IR is ready for the code generator.


## Changelog

### v1.1 (April 21, 2026)

**Allowed Ops — added `is_null` and `is_not_null`**

- Two unary operators added to the predicate grammar. Both emit no `value` key in the leaf clause.
- v1 scope limited to `Director` and `Writer`. Other string fields deferred until a real query motivates extension.
- New field mapping rule 9: absence language ("no listed director," "without a director," "missing director," "unknown director," and the same forms for writer) → `is_null` on the corresponding field. Ambiguous phrasings like "films with no X" where X is a person/title/location stay on `==` or `contains`.
- New few-shot example for `no listed director`.
- New strict rule 13: unary ops emit no `value` key; v1 scope is Director and Writer.

**Validator**

- `VALID_OPS` extended with `is_null`, `is_not_null`.
- New sets `UNARY_OPS` and `NULL_CAPABLE_FIELDS`.
- `_validate_predicate` now rejects unary ops on non-null-capable fields and rejects any leaf with `op in UNARY_OPS` that carries a `value` key. This closes the contract hole T16 exposed (predicate shape `{op: "==", value: null}` was structurally valid but semantically wrong).

**Motivation**

T16 ("films with no listed director") previously worked only because Step 6 was generous with a malformed `{op: "==", value: null}` leaf. Step 4 now emits a well-formed unary predicate and the validator enforces the shape.

Here's the changelog entry. Drop-in ready — adjust the date format and version bump if your existing changelog uses different conventions.

---

## [Phase B] — 2026-04-29

### v1.2

### Schema documentation update for 2026 dataset swap

Updated the shared schema reference in the Step 4 (Filter Extractor) prompt to reflect the new canonical dataset (`sf_film_2026_04_24_data.gpkg`, 2,208 rows × 14 columns). Documentation-only change — no behavioral change to filter extraction in this phase. Note: Step 6 (Code Generator) reads the same schema string, so this edit applies to both steps.

### Changed

- **Schema column list expanded** from 10 columns to 14, adding the four new columns introduced by SFgov's December 2024 dataset update and surfaced in the April 2026 conversion: `Production_Company (str)`, `Distributor (str)`, `Neighborhood (str)`, `Supervisor_District (Int64)`.
- **`Year` dtype annotation corrected** from `int64` to `Int64` (pandas nullable integer extension dtype). Reflects actual dtype after the read-time cast applied at notebook load. Same correction applied to `Supervisor_District`.
- **Schema annotation added** clarifying that `Neighborhood` and `Supervisor_District` are documented but **not yet active filter fields** in v1. Prevents the LLM from emitting predicates against them before Phase D enables them deliberately.
- **Rule 9 (`is_null` scope) tightened** to explicitly exclude `Production_Company`, `Distributor`, `Neighborhood`, and `Supervisor_District` from null-capable fields. Necessary because the expanded schema now visibly contains additional text columns the LLM might otherwise guess could take `is_null`. v1 null-capable fields remain Director and Writer only.
- **Rule 9 redundancy removed.** Consolidated two adjacent statements of "v1 supports Director and Writer only" into a single statement combined with the new exclusion list.

### Added

- **Inline comment on `VALID_FIELDS` constant** noting that `Neighborhood` and `Supervisor_District` are intentionally excluded from the active filter set until Phase D, with cross-references to `dataset_swap_2026.md` and `Post_data_swap_list_of_actions.md`. Prevents accidental "fixes" by future contributors.

### Not changed (intentional, Phase B is documentation-only)

- `VALID_FIELDS` runtime guard — still excludes the new columns. Phase D will revisit.
- No few-shot examples added for `Neighborhood`. Match semantics (`==` vs `contains`) deferred to open-issues; pre-committing via a few-shot would prejudge the decision before Phase E (normalizer touches) provides the necessary signal.
- Rules 1–12 (extraction logic) untouched.
- Existing few-shot examples untouched.

### Rationale

This is Phase B of the post-dataset-swap action plan documented in `Post_data_swap_list_of_actions.md`. Phase B is intentionally scoped to schema honesty — making the prompt accurately describe the data — without enabling any new behavior. Phase C (re-run T1–T34 regression suite against the new dataset) needs the prompt's filter-emission behavior held constant to be a clean regression gate; introducing Neighborhood support now would contaminate that signal.

### References

- `dataset_swap_2026.md` — full record of the data swap and accepted trade-offs
- `Post_data_swap_list_of_actions.md` — five-phase rollout plan (this entry implements Phase B)
- `phase_3_open_items_April_26.md` — where the deferred Neighborhood match-semantics question is tracked

