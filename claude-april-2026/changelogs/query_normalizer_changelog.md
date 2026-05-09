# Query Normalizer — Changelog







Running changelog of normalizer fixes since the original April 7 implementation. Reverse-chronological by date.


# Normalizer Changelog — F-1a (revised) + C-1a — May 7, 2026

Append both entries to `query_normalizer_changelog_April_26.md` in reverse-chronological order (newest at top).

---

## May 7, 2026 — C-1a: Canonical SF streets vocabulary + preposition trigger

Promoted bare-token street query handling from "deferred" to "shipped before e2e" after diagnostic work showed `films on larkin`, `films on market`, and `films on polk` are normal user phrasing rather than edge cases.

### Origin

N-1 (May 6) shipped a street-context pre-pass with a single trigger: `<street-token> <street-suffix>`. That handles `films on larkin street` but leaves `films on larkin` (no explicit suffix) broken — `larkin` falls through to fuzzy matching against Actor at the partial-name path and resolves to `Alan Arkin`.

The original deferral logic was that bare-token street queries needed cross-street/preposition context inference, which was too speculative without data on real query shapes. Reviewer feedback and direct user confirmation that `films on <street>` is normal phrasing reversed that judgment.

### Design changes from the deferred C-1 spec

**1. Vocabulary source changed from regex extraction to canonical SF streets list.**

The N-1 implementation built `street_token_index` by scanning Locations free-text with a regex (`<token> <street-suffix>`). That produced 319 tokens — incidental coverage tied to dataset shape. Replaced with a canonical SF streets list (`sf_street_names.txt`, 2,459 entries: 2,052 single-token + 407 multi-token) loaded via CSV reader.

Rationale: the canonical list is authoritative, dataset-shape-independent, and includes streets that never appear in `<token> <suffix>` form anywhere in Locations free-text (cross-street-only references, address-prefix references, etc.).

**2. Vocabulary structure changed from `set[str]` to `dict[int, set[str]]`.**

Single-token-only vocabulary cannot match multi-word street names (`van ness`, `cesar chavez`, `south van ness`, `martin luther king jr`). Restructured as an n-gram index keyed by word count over `STREET_NAME_NGRAM_RANGE = (1, 4)`. Entries with word count >4 are dropped — the canonical list contains 3 entries with 5+ words, all freeway-ramp metadata (`HWY 1 TO HWY 101 SOUTHBOUND`) that no user query will reference.

**3. Second trigger added: `<location-preposition> <street-name n-gram>`.**

Existing N-1 trigger `(a)` `<street-name n-gram> <street-suffix>` retained.

New trigger `(b)` fires when `words[i-1]` is in `LOCATION_PREPOSITIONS = {'on', 'at', 'near'}` and a canonical street n-gram starts at index `i`. Locks only the street n-gram, not the preposition. Longest-match-wins on the n-gram (so `films near south van ness` locks the 3-gram rather than the 2-gram `van ness` starting one token later).

Both triggers run sequentially; suffix trigger first. A query like `films on larkin street` hits the suffix trigger and locks `[larkin, street]`; the preposition trigger then walks past the protected span without re-firing.

`LOCATION_PREPOSITIONS` deliberately excludes `in` (collides with neighborhoods, districts, broader areas — Phase E territory) and `around` (weak Locations cue, deferable to v1.1 if needed).

**4. No substitution — span-lock only.**

Per reviewer guidance: bare-token street queries should NOT canonicalize to suffix form (`larkin → larkin st`). The Locations data is free-text with many bare-token Larkin references (`California at Larkin`, `Beach and Larkin`, `Larkin between Beach and Bay`). Predicate-level `Locations contains "larkin"` matches more rows than `Locations contains "larkin st"` would. Trigger (b) protects the span without rewriting.

Trigger (a) still applies suffix canonicalization at the trailing `normalize_street_suffixes` call, since that's a separate pass.

**5. Lock log enriched.**

Added fields to span_lock entries: `rule` (`'suffix'` or `'preposition'`), `street_source` (`'canonical_sf_streets'`), `matched_street` (the canonical n-gram), and `preposition` (only for trigger b). Preserves existing `source: 'span_lock'` tag.

### Implementation

- New constant `LOCATION_PREPOSITIONS`.
- New constant `CANONICAL_STREETS_PATH`.
- `_build_street_token_index` deleted; replaced by `_build_street_name_index` (canonical-list loader).
- `_STREET_TOKEN_PATTERN` regex deleted (dead code).
- `street_context_prepass` rewritten with two triggers and `_match_street_ngram` helper.
- `normalize_query` updated to pass `street_name_index` (renamed from `street_token_index`).

### Index sizes against new gpkg

```
Phrase index: {2: 140, 3: 352, 4: 254}
Street name index: {1: 2052, 2: 392, 3: 74, 4: 25}  total: 2543
```

### Validation results

23-query normalizer test set covering:

- Preposition trigger on single-token streets (larkin, market, polk, sutter, treat, 19th)
- Preposition trigger on multi-token streets (van ness, south van ness, cesar chavez)
- Preposition variants (`on`, `at`, `near`)
- Person-cue rejection (`films starring polk`, `films featuring larkin`, `films starring market`)
- F-1a regression (`films starring alan arkin`)
- N-1 suffix-trigger regression (`films on larkin street`)
- Mixed cases (`films on van ness avenue` → falls into phrase pre-pass via `Van Ness Ave` Locations entry)
- Phrase pre-pass regression (coit tower, golden gate bridge, union square, port of san francisco, the castro)

All 23 produce expected behavior. Notable observation: `films at the castro` resolves via phrase pre-pass exact-match against `'The Castro'` Locations entry, not via the preposition trigger (the `the` between `at` and `castro` defeats trigger b's adjacency requirement). Correct outcome via a different mechanism.

### e2e validation

T15 (`films on larkin street`): 12 films returned. Matches pre-swap baseline.
T18 (`films on larkin street and how many are there`): 12 films + count. Matches pre-swap baseline.

### Diagnostic finding (filed as D-1)

A one-time diagnostic comparing the deprecated derived vocabulary against the canonical list surfaced 11+ misspellings in Locations free-text: `larken`, `barlett`, `buchannan`, `chestnust`, `misison`, `shotweel`, `sporfford`, `tayor`, `mccollough`, `jenning`, `kearney`. These produce data-coverage holes (predicate substring-match cannot find correctly-spelled queries against misspelled rows) but are independent of normalizer behavior. Filed as **D-1: Locations dataset typo repair**.

### Severity

Real fix. Bare-token street queries with location prepositions now route correctly to predicate-level Locations matching. Multi-word street support is structural (any future canonical-list addition is automatically covered). Vocabulary is no longer dataset-shape-dependent.

### Files changed

- `pipeline_e2e_may_2026_normalization_upgrades.ipynb`:
  - Pre-pass cell (post-`fuzzy_match_cluster`): full body replacement.
  - `normalize_query` cell: variable rename `street_token_index` → `street_name_index`.

---

## May 7, 2026 — F-1a revised: raw-ratio scoring with exact-match priority

Replaces the normalized-ratio scoring in F-1a (May 6) with raw-ratio + exact-match priority + column-tiebreaker. Same architectural goal (best-match selection across columns), more conservative scoring math.

### Origin

F-1a (May 6) introduced best-match selection in `fuzzy_match_cluster` to fix the catastrophic `films starring alan arkin → Beach and Larkin` regression discovered during N-1 Layer 3 testing. Initial implementation used normalized ratio:

```python
normalized = (raw - cutoff) / (1.0 - cutoff)
```

This made matches across columns directly comparable despite different cutoffs (Locations 0.65, person columns 0.75, Title 0.80). Resolved Alan Arkin because raw 1.0 wins under any scoring.

### Why revised

Reviewer flagged a real failure mode: normalized scoring can let a lower raw similarity in Locations beat a higher raw similarity in Actor.

Worked example:
- Actor raw 0.80 → normalized `(0.80 - 0.75) / 0.25` = 0.20
- Locations raw 0.78 → normalized `(0.78 - 0.65) / 0.35` = 0.371
- Under normalization, Locations wins. Under raw ratio, Actor wins.

Locations would systematically win boundary cases purely because its lower cutoff floor compresses its normalized range. That's the opposite bias from what's wanted (Locations is the column most likely to over-admit candidates due to its long free-text values).

### Design

New scoring rule, in priority order:

1. **Exact match wins.** `raw >= 0.999` is treated as exact and beats any non-exact match regardless of column.
2. **Highest raw ratio wins** among non-exact matches above each column's cutoff.
3. **Column priority breaks ties.** Order: Actor (0), Director (1), Writer (2), Title (3), Locations (4). Lower index wins. Locations last because its loose cutoff makes it most likely to over-admit.

Implementation uses tuple comparison `(is_exact, raw, -col_pri)` so larger tuple under `>` wins.

### Trade-off accepted

Raw-ratio comparison gives a slight structural advantage to columns with lower cutoffs (more candidates qualify in the first place). This is weaker than normalized-ratio's compounding bias and is mitigated by column priority breaking ratio ties in Actor's favor when multiple columns score legitimately.

### Validation

`films starring alan arkin` test case:
- Actor: `alan arkin` exact match → raw 1.0 → `is_exact=True`, score `(True, 1.0, -0)`.
- Locations: `alan arkin` ≈ `Beach and Larkin` → raw ~0.67 → `is_exact=False`, score `(False, 0.67, -4)`.
- Best: Actor. Returns `('Alan Arkin', 'Actor', 'alan arkin')`. ✓

23-query test set produces no regressions vs the original F-1a result on Alan Arkin or any other query.

### Severity

Same as F-1a (catastrophic regression unblocker), with safer math. The scoring now degrades gracefully in boundary cases rather than systematically favoring the loosest-cutoff column.

### Files changed

- `pipeline_e2e_may_2026_normalization_upgrades.ipynb`:
  - `fuzzy_match_cluster` cell: scoring logic replacement (function shape unchanged).

### Open follow-up

A 20–30 case audit of cross-column scoring decisions was suggested by the reviewer to validate the new rule against a broader set of queries. Deferred to F-1b design work, where it can be combined with cue-gating evaluation.




---
## May 6, 2026 — N-1: Phrase pre-pass + street-context pre-pass for Locations

Implemented the long-standing N-1 open item from the April 26 phase-3 work, with substantive design changes from the original spec after diagnostic work on the new (post-swap) Locations data.

### Origin

Phase C (April 24, dataset swap) revealed that T15 and T18 regressed against the new gpkg. The query `films on larkin street` resolved to `films on alan arkin st`: the cluster extractor stripped `street` (DOMAIN_WORDS), produced a bare `larkin` single-word cluster, and the fuzzy matcher accepted `larkin` ≈ `arkin` at ratio ~0.83 against Actor at the 0.75 cutoff.

The April 26 open-items doc proposed N-1 as a phrase pre-pass: scan 2–4-grams against known multi-word `Locations` values before cluster extraction, lock matched spans against fuzzy correction.

### Design change after diagnostic work

Initial implementation followed the spec literally — exact-canonical and near-exact (≥0.95) matching of query n-grams against full Locations values. Diagnostic on the new data revealed the spec's core assumption was wrong for street references:

```
known_values['Locations'] containing "larkin":
'724 Larkin St', '945 Larkin St', '2632 Larkin St at Lombard',
'Bay St between Larkin and Hyde', 'California at Larkin',
'Larkin between Beach and Bay', 'The Magazine at 920 Larkin',
... (34 rows total, none of which are 'Larkin St' as a clean phrase)
```

Streets in this dataset are stored as embedded fragments inside free-text descriptions (`724 Larkin St`, `California at Larkin`, `Larkin & Hyde St`), not as standalone canonical values. A 2-gram phrase pre-pass for `larkin st` finds no full-string match because the index has no `larkin st` entry — only `724 larkin st`, `945 larkin st`, etc. Spec-compliant N-1 would not have fixed the originating bug.

Landmarks, in contrast, *do* appear as clean values:
'Coit Tower', 'Golden Gate Bridge', 'Port of San Francisco', 'Union Square'

So the data is bimodal: phrase pre-pass works for landmarks; streets need a different mechanism.

### What was implemented

Two complementary subpasses, both run before cluster extraction, both populating a shared `protected` index set passed to a modified `extract_content_clusters(words, protected_indices=...)`.

**Subpass 1 — `phrase_prepass`** (landmarks). Scans 2-, 3-, 4-grams in the query against an index of `Locations` values that are themselves ≥2 words, suffix-canonicalized at index build time. Exact-canonical fast path before `difflib.get_close_matches` at cutoff 0.95. Longest-match-wins, left-to-right, non-overlapping. Same-length matches only (length-changing matches fail at 0.95 cutoff anyway). On match: substitute canonical form if different from input, lock span. Logs `source: 'phrase_prepass'` (rewrite) or `source: 'phrase_prepass_exact'` (no rewrite, span-locked only — added during testing for observability).

**Subpass 2 — `street_context_prepass`** (streets). Walks single tokens. If a token appears in an extracted street-token vocabulary AND is immediately followed by a street-suffix word (`street`/`st`/`avenue`/`ave`/`boulevard`/`blvd`/...), lock the token+suffix span. No substitution — original tokens preserved for downstream suffix canonicalization and predicate-level substring matching. Logs `source: 'span_lock'`. v1 fires only on the suffix-immediately-following rule; preposition (`on larkin`), cross-street (`larkin and hyde`), and ampersand (`larkin & hyde`) contexts deferred to C-1.

Street-token vocabulary built once at known-values build time by regex extraction over `Locations` free-text: tokens immediately preceding a street-suffix word, with `STOP_WORDS`/`DOMAIN_WORDS`/numeric tokens/length-≤2 tokens filtered out. Resulting set: 319 tokens.

### Index sizes against new gpkg

Phrase index: {2: 140, 3: 352, 4: 254}
Street tokens: 319

### Validation results

Layer 1 (index sanity, 6 asserts): pass.

Layer 2 (originating bug + 6 landmark/street queries): all 7 normalize correctly.
- `films on larkin street` → `films on larkin st` with `span_lock`. Originating bug fixed.
- `films on geary street`, `films on hyde street` — same pattern, span-locked.
- `coit tower`, `golden gate bridge`, `port of san francisco`, `union square` — all phrase-pre-pass-locked. Diagnostic confirmed `protected = {2,3}` or `{2,3,4}` and `clusters = []` (cluster extractor sees nothing).

Layer 3 (regression sweep, 9 queries): 8 of 9 unaffected. One catastrophic pre-existing bug surfaced (see "Bug discovered during validation" below).

### Files changed

- `pipeline_e2e_testing_post_llm_resiliency_dataset_swap.ipynb`:
  - Added new cell after `fuzzy_match_cluster` containing `_build_phrase_prepass_index`, `_build_street_token_index`, `phrase_prepass`, `street_context_prepass`, plus index-build trailer.
  - Modified `extract_content_clusters` to accept `protected_indices=None` parameter.
  - Modified `normalize_query` to call both subpasses before cluster extraction; merged corrections lists; added `source: 'fuzzy_cluster'` tag to the existing cluster-correction dict for uniform observability.

### Severity

Real fix, not patch. The cluster extractor never sees protected spans as free-floating content tokens, so the bug class (street/landmark phrases hijacked by person/title fuzzy matching) is structurally prevented for the cases the two subpasses cover. Bare-token street references without suffix (`films on larkin`) are not yet covered — deferred to C-1.


## April 26, 2026 — Three fixes surfaced by Phase 3 e2e tests

Three distinct bugs in `normalize_query` and its helpers were exposed by Phase 3 test queries (T21–T28). All three involved the normalizer corrupting valid input before Step 4 saw it. Each is documented below with cause, fix, and severity classification.

### Fix 1 — `DOMAIN_WORDS` expansion for SF location-type vocabulary

**Symptom:** Single-word common nouns that appear as location-type modifiers in the dataset (`port`, `pier`, `bridge`, `hotel`, etc.) were entering the cluster extractor as content words. When isolated as short single-word clusters, they fuzzy-matched against unrelated database values — most damagingly, `port` → `Bud Cort` (Actor) and `pier` → `Guy Pierce` (Actor) at ratio ~0.75.

**Cause:** `DOMAIN_WORDS` originally covered film-vocabulary terms (`film`, `directed`, `location`, `decade`) but did not include the geographic type-words that appear as modifiers in SF location names. Without these in `DOMAIN_WORDS`, they became unprotected short content clusters.

**Fix:** Expanded `DOMAIN_WORDS` to include:
```
'port','pier','bridge','hotel','street','avenue','boulevard',
'square','park','tower','hill','wharf','cross','bay','beach',
'museum','cable','car','terminal','station','school','hospital',
'building','house'
```

**Side effect noted, then resolved by Fix 3:** Adding `bridge` initially split `golden gate bridge` into `[golden gate]` cluster + `bridge` skip. The 2-word cluster `golden gate` then matched `Golden Gate Park` at ratio 0.71, producing the corrupted phrase `golden gate park bridge`. Fix 3 closed this regression structurally; the expansion remains valid.

**Severity:** symptomatic fix. Closes the immediate bugs but does not prevent future common-noun-vs-name collisions. Future-proof solution lives in Fix 3.

---

### Fix 2 — Removed unprefixed `CITY_PATTERNS` regexes

**Symptom:** The query `port of san francisco` was being rewritten to `port of` mid-pipeline, producing a meaningless `Locations contains "port of"` predicate that substring-matched against unrelated location strings. T22 and T27 produced wrong-but-coincidentally-plausible answers as a result.

**Cause:** `CITY_PATTERNS` contained six regex patterns. Four were prefixed (`in san francisco`, `in sf`, `in the city`, `in california`) and only fired when the geographic qualifier was acting as a query scope. Two were unprefixed (`san francisco`, `sf`) and stripped these tokens *anywhere* in the query — including mid-phrase, where they were part of legitimate multi-word location names.

**Fix:** Deleted the two unprefixed patterns:
```python
# REMOVED:
re.compile(r'\bsan\s+francisco\b', re.I),
re.compile(r'\bsf\b', re.I),
```

The four prefixed patterns handle the common scope-qualifier constructions users actually write (`films in san francisco`, `films in sf`). Bare `san francisco` mid-query is overwhelmingly part of a location name in this dataset, not a scope qualifier.

**Tradeoff accepted:** queries like `films san francisco` (no `in`) will no longer have the city term stripped. This phrasing is rare; if it becomes a problem, a more sophisticated stripper that checks against known multi-word locations before stripping would be the right next step.

**Severity:** structural fix. Eliminates the entire class of "city pattern strips part of a location name" bugs.

---

### Fix 3 — `is_unjustified_expansion` guard in `fuzzy_match_cluster`

**Symptom:** After Fix 1 and Fix 2, T22 and T27 were still producing wrong answers — `port of san francisco` was being rewritten to `port of san francisco bay`. Cluster `san francisco` was matching against `San Francisco Bay` (a Locations value) at high ratio, and the matched value displaced the cluster, *expanding* the phrase by appending `bay`.

**Cause:** `fuzzy_match_cluster` accepted any difflib match above the column cutoff without checking whether the match was *strictly longer* than the cluster and contained the cluster as a verbatim word-bounded prefix or suffix. This meant any cluster that happened to be a prefix of a longer database value would be expanded, regardless of user intent.

This same bug class produced earlier regressions in this session: `golden gate` → `Golden Gate Park` (verbatim 2-word prefix of a 3-word location), and motivated the original DOMAIN_WORDS patch attempt.

**Fix:** Added a guard function and consultation point in `fuzzy_match_cluster`:
```python
def is_unjustified_expansion(cluster_text, matched_value):
    """Reject matches that just append words to a verbatim cluster."""
    cluster_lower = cluster_text.lower().strip()
    matched_lower = matched_value.lower().strip()
    if cluster_lower == matched_lower:
        return False  # exact match, fine
    if matched_lower.startswith(cluster_lower + ' '):
        return True   # "san francisco" → "san francisco bay" — reject
    if matched_lower.endswith(' ' + cluster_lower):
        return True   # "the bridge" → "golden gate bridge" — reject
    return False
```

Called immediately before `return (matches[0], col, cluster_text)` in `fuzzy_match_cluster`. If the guard returns `True`, the candidate is rejected and the loop falls through to the next column or returns no match.

**What is preserved:** Genuine typo corrections still work. `golden gate brige` (typo) → `Golden Gate Bridge` is allowed because the cluster is *not* a verbatim prefix — the typo `brige` breaks the equality check. Only verbatim-word-bounded expansions are rejected.

**Severity:** structural fix. Closes the durable class of "cluster matches a longer database value that contains the cluster as a prefix or suffix" bugs. Eliminates an entire family of false corrections that no list-membership patch could fully prevent.

---

### Order of application

The three fixes were applied sequentially across four Phase 3 Run 1 attempts:

1. Initial run (Fix 0, no patches): 4/8 actually correct under suite summary's 8/8 surface success — three "false success" tests where normalizer corruption coincidentally produced plausible answers.
2. After Fix 1 alone: revealed Fix 2 and Fix 3 conditions (the city-stripper and the expansion-class bugs).
3. After Fix 1 + Fix 2: revealed Fix 3 alone (the san-francisco-bay expansion).
4. After Fix 1 + Fix 2 + Fix 3: 8/8 genuinely correct.

Run 2 (T29–T34) passed 6/6 on the first attempt with all three fixes in place.

---

### Files touched

- `pipeline_e2e_testing_post_llm_resiliency.ipynb`
  - `DOMAIN_WORDS` cell — additions
  - `CITY_PATTERNS` cell — two regex deletions
  - `fuzzy_match_cluster` function — new helper `is_unjustified_expansion` and one consultation point

### Reclassification of prior limitation

`LIMIT-1` from `bug_handoff_April_24_consolidated.md` (query normalizer has no word-merger) is unaffected by these fixes. It remains an acknowledged limitation.

The earlier Phase 2 statement that the normalizer "currently passes 73 of 74 internal tests" should be re-validated against the post-April-26 normalizer to confirm none of the legitimate-correction tests regressed under Fix 3's expansion guard. Likely fine — the guard is conservative and only blocks verbatim prefix/suffix expansions — but worth a clean run.
