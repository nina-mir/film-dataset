# Code Generation Prompt (v2) — Development Report

**Date**: April 16, 2026
**Status**: Prompt designed, ready for Colab testing
**Environment**: Will be tested in Google Colab with full pipeline (Steps 1–5 + Code Gen)

---

## What Was Built

A complete rewrite of `code_generation.md` aligned with the new 5-step preprocessing IR. The NLP Planner (old Stage 2) is dropped — the code generator consumes the IR directly, reducing LLM calls from 4 to 3.

## Key Architecture Decisions

- **Query-specific codegen.** The LLM sees the exact IR for this query in the prompt and generates hardcoded pandas code for it. It does not write a generic interpreter. Function signature stays `process_sf_film_query(gdf)`.
- **`matched_rows` / `text_view` separation.** Every task computes full filtered rows first (`matched_rows`), then derives a presentation view (`text_view`) from `response_granularity`. Map always uses `matched_rows`. Text answer always uses `text_view`.
- **IR is prompt context, not runtime input.** The IR is injected into the prompt via a `{ir_json}` placeholder. The generated code does not receive or parse the IR at runtime.
- **Upstream geocoding.** Spatial `within_distance` predicates arrive with `latitude`/`longitude` already resolved. A deterministic geocoding resolver (static landmark lookup) runs as a Step 4 post-processor, same slot as actor expansion.

## Prompt Structure

| Section | Job |
|---------|-----|
| A. Mission | What the code generator does and doesn't do |
| B. Hard Invariants | 20 non-negotiable rules (mask safety, no mutation, granularity, etc.) |
| C. Input Specification | GeoDataFrame schema, task IR schema, predicate schema, reference example, injected IR |
| D. Translation Cookbook | D1–D6: execution skeleton, attribute ops, spatial ops, anti-patterns, task kinds, dependencies |

## New Files Created

- `code_generation_v2.md` — the complete prompt (~1,500 lines)
- `geocoding_resolver.py` — Step 4 post-processor for spatial predicates
- `sf_landmarks.json` — static lookup with ~80 SF landmarks
- `geocoding_resolver_notes.md` — integration notes

## Testing Plan

**Phase 1 (single-task, first priority):**
1. Retrieve on string field (Director, Actor, Locations)
2. Count films
3. Count locations
4. Rank directors/actors
5. Spatial retrieve (within_distance)

**Phase 2 (multi-task, later):**
- Retrieve → count dependency
- Retrieve → retrieve → compare

## Pipeline After This Step

```
User Query
  → Step 1: Query Normalizer (rule-based)
  → Step 2: Safety Gate (rule-based)
  → Step 3: Task Decomposer (LLM)
  → Step 4: Filter Extractor (LLM)
      → Actor expansion (deterministic post-processor)
      → Geocoding resolver (deterministic post-processor)
  → Step 5: Presentation Resolver (rule-based)
  → Step 6: Code Generator (LLM) ← this step
  → Execution + Response
```

Three rule-based steps, three LLM steps. Full IR flows from Step 5 into the code generation prompt.

## Production Upgrade Path

- **Geocoding:** swap static lookup for live geocoder (geopy/Nominatim). Keep static file as fast-path cache.
- **Predicate execution:** once IR stabilizes, extract a deterministic `apply_predicate_tree()` helper. Shrinks the LLM's job to task-level logic only.
- **NLP Planner:** formally retired. Can be resurrected if code generator struggles without it (unlikely given IR richness).


## Changelog

### v2.1 (April 18, 2026)

**Section B — Hard Invariants**

- **Added invariant 21:** all string literals in generated code must be single-line.
  Forbids raw newline characters inside `'...'` or `"..."` (including f-strings).
  If a newline is needed, use the `\n` escape sequence.
  Fixes the T2 `SyntaxError: unterminated f-string literal` that occurred after
  JSON round-trip when the model emitted `\n` inside a multi-line summary string.

- **Added invariant 22:** all values from the IR that appear in summary strings or
  log messages must be inlined as string literals in the generated code.
  Forbids reading predicate values, field names, or spatial references from
  `task_results` at runtime — `task_results` stores `matched_rows`, `text_view`,
  and `result` only. Includes a wrong/right example pulled from T8's failure mode.
  Fixes the T8 `KeyError: 'predicate'` that occurred when the model tried to read
  `task_results['t1']['predicate']['value']['reference_place']` to build a
  summary string.

### v2.2 (April 19, 2026)

**Section B — Hard Invariants**

- **Added invariant 23:** forbids applying a second type conversion
  (`.to_dict()`, `.tolist()`, `.to_json()`, `dict(...)`, `list(...)`) to a
  value that has already been stored in `task_results[...]['result']` when
  assembling the outer `result` dictionary. Conversion happens exactly once,
  at point of storage; the outer assembly must assign the stored value
  directly. Includes a wrong/right example pulled from T5's failure mode.
  Fixes the T5 `AttributeError: 'dict' object has no attribute 'to_dict'`
  that occurred on rank tasks when the model stored `top_directors.to_dict()`
  in `task_results` and then called `.to_dict()` on the retrieved dict again
  in `result['data']`. Byte-identical across April 18 and April 19 runs at
  `temperature=0`, confirming it as a prompt-level pattern bug rather than
  model variance.

  Right — the schema change plus the `Year` dtype clarification is exactly the kind of edit that earns a minor version bump. v2.3 → v2.4.

Here's the changelog entry, parallel in structure to the Step 4 one so they read as a matched pair.


### v2.3 (April 21, 2026)   

**Section C3 — Predicate Schema**

- Leaf clause documentation updated: the `value` key is present for all operators except `is_null` and `is_not_null`, which are unary.
- Operators table extended with two rows: `is_null` (field absent or empty, Director/Writer only, no `value` key) and `is_not_null` (field present and non-empty, Director/Writer only, no `value` key).

**Section D2 — Attribute Predicate Translation**

- Added two new leaf op patterns, inserted after Actor OR expansion:
  - `is_null` on a string field: four-way absence mask (`isna()`, empty-after-strip, stringy-nulls `'none'`/`'nan'`/`'null'`), combined with `|`.
  - `is_not_null` on a string field: the complement — same four conditions negated and combined with `&`.
- Each pattern explicitly notes: no `value` key in the leaf; do not reference `.get('value')` or construct a value literal.
- D2 Summary bullet added covering the `is_null` / `is_not_null` pattern.

**Motivation**

Paired with Step 4 v1.1. Without this update, Step 4 would emit `is_null` and Step 6 would hit an unknown operator and fall back to broken code. Bundled to land same-day.

**Verification**

T16 re-run after both patches: Step 4 emits `{"field":"Director","op":"is_null","type":"attribute"}` with no `value` key. Codegen produces the four-way absence mask. Result returns the single film without a listed director, manually verified against the DB.


## v2.4 — 2026-04-29

### Schema documentation update for 2026 dataset swap

Updated Section C1 (GeoDataFrame Schema) to reflect the new canonical dataset (`sf_film_2026_04_24_data.gpkg`, 2,208 rows × 14 columns). Documentation-only change — no behavioral change to code generation in this phase. Companion to the matching Step 4 (Filter Extractor) update applied the same day; the two prompts share a schema reference and were updated together.

### Changed

- **Schema column list expanded** from 9 documented columns to 13, adding the four new columns introduced by SFgov's December 2024 dataset update: `Production_Company` (str), `Distributor` (str), `Neighborhood` (str), `Supervisor_District` (Int64).
- **`Year` dtype annotation corrected** from "string/numeric coerce-as-needed" framing to explicit `Int64` (pandas nullable integer extension dtype). The `pd.to_numeric(..., errors='coerce')` instruction is preserved and explicitly tied to numeric comparisons — `Int64` does not eliminate the need for coercion, only documents the underlying storage type.
- **Null-allowed annotations added** to `Neighborhood`, `Supervisor_District`, and `geometry`. The geometry annotation closes a small honesty gap: D3 has always handled null geometry via `valid_geom_mask`, but the schema did not previously state that geometry could be null. Now consistent with the cookbook's actual behavior.

### Added

- **v1 scope note** in Section C1 stating that `Production_Company`, `Distributor`, `Neighborhood`, and `Supervisor_District` are present in the GeoDataFrame but are not referenced by any predicate the upstream Filter Extractor will emit in v1. Prevents the LLM from generating speculative handling for these columns when an IR happens to mention a neighborhood name in a location string or a production company in a title-like context.

### Not changed (intentional, Phase B is documentation-only)

- **Section C3 (Allowed fields after post-processing).** The list — `Title, Year, Locations, Fun_Facts, Director, Writer, Actor_1, Actor_2, Actor_3, geometry` — remains correct for v1 and is intentionally not expanded. Predicate-schema scope and dataframe-schema scope are different lists; the dataframe contains more than the IR can target.
- **Allowed operators table.** Untouched.
- **D1–D6 cookbook patterns.** Untouched. No new query shapes are enabled by Phase B, so no new translation patterns are required.
- **Section B hard invariants.** Untouched.

### Rationale

Phase B of the post-dataset-swap action plan documented in `Post_data_swap_list_of_actions.md`. Phase B is intentionally scoped to schema honesty without enabling new behavior. Phase C (re-run T1–T34 regression suite against the new dataset) needs the prompt's code-generation behavior held constant to be a clean regression gate; introducing Neighborhood handling now would contaminate that signal. The Step 4 and Step 6 prompts share a schema reference; updating one without the other would create a documentation drift that subsequent phases would have to reconcile.

### Phase C watch list

The `Year` dtype change from inferred-as-float64 to canonical `Int64` is the most likely source of regression noise in Phase C. Three places to watch:

- `pd.to_numeric(gdf_copy['Year'], errors='coerce')` — works on `Int64`, returns `float64`. Cookbook patterns are unaffected.
- `int(year)` on individual row values (used in the D5 retrieve-with-grouping example) — works on `Int64` values, requires the `pd.notna(year)` guard already in place.
- Direct equality without coercion (e.g., `gdf_copy['Year'] == 1985`) — returns a nullable `BooleanArray` rather than a plain bool Series. Generated code following the cookbook always coerces first, so this should not surface; if it does, the cookbook's coercion rule has been bypassed.

If a Phase C regression traces to `Year` handling, this is where to look.

### References

- `dataset_swap_2026.md` — full record of the data swap and accepted trade-offs
- `Post_data_swap_list_of_actions.md` — five-phase rollout plan (this entry implements Phase B)
- Step 4 changelog, same date — matching update to the shared schema reference

---
