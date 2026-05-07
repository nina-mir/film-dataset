# Query Normalizer — Changelog

Running changelog of normalizer fixes since the original April 7 implementation. Reverse-chronological by date.

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
