# Phase 3 Open Items & Forward-Looking Notes

**Date**: April 26, 2026
**Context**: companion document to `phase_3_progress_report_April_26.md` and `query_normalizer_changelog_April_26.md`. Captures items observed during Phase 3 work that are not blocking but warrant attention before the next major iteration.

---

## Normalizer — areas that could benefit from further work

### N-1: Phrase pre-pass for known multi-word locations

**Observation:** During the Phase 3 normalizer fixes, three separate bugs all traced to the same root cause: the cluster extractor has no awareness of multi-word locations as semantic units. Adding `bridge` to `DOMAIN_WORDS` split `golden gate bridge` into `[golden gate]` cluster + `bridge` skip, exposing the smaller cluster to a false match. Removing `san francisco` from city stripping left `san francisco` as a cluster that matched `San Francisco Bay`. The `is_unjustified_expansion` guard now closes both at the matching layer, but the underlying architectural issue remains: clusters are extracted *first*, then matched, with no opportunity for multi-word phrases to be recognized as units before clustering.

**Suggested approach:** A phrase pre-pass that runs *before* cluster extraction. For each n-gram in the query (n = 2, 3, 4), check whether it matches a known Locations value at high ratio (≥0.95, near-exact). If yes, mark that span as already-resolved and exclude it from cluster extraction entirely. The cluster extractor would then only run over un-resolved spans.

This would mean `golden gate bridge` would be recognized as a unit on first pass, `Golden Gate Bridge` would be substituted (or left unchanged if already exact), and the cluster extractor would never see those three words. The same logic would protect `port of san francisco`, `union square`, `coit tower`, and any other multi-word location.

**Cost:** moderate. Requires loading Locations as a sorted set at normalize-time (already happens for fuzzy matching, no new I/O), and an n-gram scan over the query (cheap). Estimated +5–10ms per query, well within latency budget.

**When to do it:** before the next major test phase, or whenever a real query surfaces a new bug in this class. The current `is_unjustified_expansion` guard should hold for the queries observed so far, but it's defensive — the pre-pass would be preventive.

---

### N-2: Short-cluster cutoff floor

**Observation:** The original `port` → `Bud Cort` and `pier` → `Guy Pierce` corruptions were caused by short single-word content clusters fuzzy-matching against name-column values at the default 0.75 cutoff. The current Fix 1 adds these specific words to `DOMAIN_WORDS`, but the structural vulnerability remains: any 4–5 character common English noun whose suffix happens to overlap a name in the database can produce the same class of corruption. `cab` → `Cabaret`, `bay` → `Baywatch`, `rock` → `The Rock`, etc.

**Suggested approach:** In `fuzzy_match_cluster`, lift the cutoff for short single-word clusters. Specifically: if `' ' not in cluster_text and len(cluster_text) <= 5`, set `cutoff = max(cutoff, 0.90)` for that match attempt. Apply the same lift to the partial-name path lower in the function.

This rejects `port`/`Bud Cort` (ratio ~0.75) and `pier`/`Guy Pierce` (ratio ~0.77) while still accepting genuine high-ratio matches like `coit`/`Coit` (ratio 1.0).

**Cost:** trivial. ~3 lines of code in one function.

**Tradeoff:** marginal loss of typo-correction power on legitimate short typos (e.g., `meyrs` → `Meyer` at ratio ~0.80 would be rejected). For person names, this is probably fine — short typos are rare and full-name matches via the partial-name path remain robust at length ≥6.

**When to do it:** straightforward to ship alongside N-1 or independently. Cheap insurance against future surprises.

---

### N-3: Re-validate the 73-test internal normalizer suite

**Observation:** The April 7 report documents 73 internal normalizer tests passing. Three structural changes have been made since then (April 26 fixes). The expansion guard in particular is conservative, but it's worth confirming none of the legitimate-correction tests regress.

**Suggested approach:** rerun the existing test suite from the original normalizer development notebook, against the post-April-26 normalizer. Investigate any failures.

**Cost:** ~5 minutes of execution, plus inspection time for any failures.

**When to do it:** before declaring the normalizer stable for the next phase.

---

### N-4: User disambiguation surfacing (deferred from April 7)

**Observation:** The original April 7 report flagged this as a future enhancement. Phase 3 surfaces a new motivation: when the normalizer rejects an unjustified expansion (Fix 3) or rejects a low-ratio short-cluster match (N-2), the query passes through unchanged. If the user *did* mean an entity Claude knows about but is rejecting out of caution, no signal currently surfaces this. Adding a "did you mean" branch — even just a logged hint — would help post-mortem debugging on real-world queries.

**Suggested approach:** When a candidate match is found but rejected by `is_unjustified_expansion` or a future short-cluster floor, log it as a "suppressed_match" alongside the corrections list. Step 4 ignores it; downstream observability uses it.

**Cost:** small. One additional list in the normalize_query return value.

---

## Compare kind — under-specified output contract

### Observation from T33

T33 ("films shot at golden gate bridge and films shot at port of san francisco and compare them") produced this Step 6 output:
```python
{
    'golden_gate_bridge_only': [...],
    'port_of_sf_only': [...],
    'both': [...],
    'total_unique_films': N
}
```

This is a sensible set-comparison shape. It is also entirely Step 6's invention — neither the IR nor the code-generation prompt specifies what `compare` should produce.

### Why this works today and won't always

The T33 query asked for set comparison ("compare them" between two retrieve results). Step 6 chose set-difference semantics, which fits. But `compare` queries can take many shapes:

- Set comparison: "compare these two film sets" → the T33 shape is right
- Attribute comparison: "compare the years of these films" → wants distributions, ranges, summary stats
- Temporal comparison: "compare 1985 films to 2015 films" → wants per-period metrics
- Cross-cutting comparison: "compare directors who filmed at Golden Gate Bridge vs Pier 39" → wants overlap and distinctiveness on a third dimension

Each of these is a legitimate `compare` query. Step 6's current behavior is to infer from context, which works on T33 but is not contract-bound.

### Suggested approach

Two paths, in increasing order of investment:

**Light path — document and observe.** Add a section to the Step 6 prompt explicitly listing the four compare shapes above and giving Step 6 guidance on how to choose between them based on the t3 source phrase. This is a prompt-engineering fix; it does not change the IR contract. Risk: same as any prompt-only fix — non-deterministic, can drift across model versions.

**Structural path — add a `compare_kind` field to the IR.** Step 4 (or Step 5) inspects the t3 source phrase and emits one of `set_compare`, `attribute_compare`, `temporal_compare`, `cross_compare`. Step 6 reads it and generates the corresponding code shape deterministically.

Either path requires more compare queries to be exercised before the right shape is clear. Phase 3 has a single compare test (T33) and it landed on the set-comparison case. A future test phase that includes 3–4 compare queries with varied semantics would surface whether the inference is robust or fragile.

### When to do this

Not blocking. The current behavior is correct on T33 and will likely be correct on similar set-comparison queries. The structural fix becomes worth doing once you have evidence — from real-world queries or a future Phase 4 — that compare ambiguity produces wrong-shape outputs.

### Telemetry to add now

Cheap and useful: when Step 6 generates a compare task, log the inferred shape (`set_compare` etc.) alongside the IR. This costs nothing and gives you data for the eventual decision.

---

## Test-harness observation

The Phase 3 Run 1 first attempts produced false-success readings — the suite summary said 8/8 passing while three of those tests had normalizer-corrupted inputs producing coincidentally plausible answers. The harness's `success` flag is end-to-end pipeline completion, not semantic correctness.

This is acceptable for now (a fully automated semantic check is non-trivial), but worth a small enhancement: when `corrections` is non-empty and the corrected query differs materially from the original (e.g., a multi-word location was rewritten), surface a `requires_review` flag in the per-test output. The reader can then know which "successes" warrant manual eyeballing.

This would have caught all three Run 1 false successes at glance time rather than requiring careful printout reading.

---

## Summary

| Category | Item | Severity | Cost |
|---|---|---|---|
| Normalizer | N-1: Phrase pre-pass | Defensive → preventive | Moderate |
| Normalizer | N-2: Short-cluster cutoff floor | Hardening | Trivial |
| Normalizer | N-3: Re-validate 73-test suite | Confidence | 5 min |
| Normalizer | N-4: Suppressed-match surfacing | Observability | Small |
| Compare | Document shapes in Step 6 prompt (light path) | Contract | Small |
| Compare | Add `compare_kind` to IR (structural path) | Contract | Moderate |
| Compare | Log inferred shape as telemetry now | Observability | Trivial |
| Test harness | `requires_review` flag for normalizer-corrected queries | Observability | Small |

None are blocking. All would improve robustness or observability for the next phase.
