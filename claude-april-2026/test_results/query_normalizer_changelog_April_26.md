# Query Normalizer — Changelog

Running changelog of normalizer fixes since the original April 7 implementation. Reverse-chronological by date.

---

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
