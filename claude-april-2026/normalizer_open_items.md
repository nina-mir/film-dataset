# Normalizer Open Items — Status as of May 8, 2026 (updated)

## Recently shipped

### Today (May 8)

- ✅ **C-1a.1** (cross-street continuation locks): handles `<locked> and <street>`, `<locked> & <street>`, `<locked> between <street> and <street>`. Verified against 6 cross-street query shapes including 3-way chains.
- ✅ **DOMAIN_WORDS expansion**: added `television`, `tv`, `show`, `shows`, `series`, `episode`, `episodes`. Prevents media vocabulary from entering cluster extraction. Kills `films and television shows → films and barry levinson shows`.
- ✅ **`from <street> to <street>` standalone range trigger**: handles `films from larkin to polk` without making `from` a general Locations preposition (preserves year-range queries like `films from 1985`).

### Earlier this week

- ✅ N-1: phrase pre-pass + street-context pre-pass (suffix-anchored). May 6.
- ✅ F-1a: best-match selection in `fuzzy_match_cluster`, raw-ratio with exact-priority. May 6 (initial) + May 7 (revised scoring).
- ✅ C-1a: canonical SF streets vocabulary + preposition trigger. May 7.

T1–T34 all passed against the new gpkg (May 8 morning run). T15 and T18 now return correct counts (12 films) matching the post-swap baseline.

---

## Open items — queued for tomorrow (May 9)

### F-1b v1 — Hard column gating for strong cues
**Priority: high. Blocks declaring normalizer stable.**

Targeted normalizer testing (May 8) revealed that `fuzzy_match_cluster` still allows wrong-column matches under strong cues. Examples:

```
films directed by smith and jones
→ films directed by alexis smith and dean jones    (Actor, but cue says Director)

films starring tom and jerry
→ films starring tom and ken berry                 (partial-name path matches Berry surname)
```

`F-1a`'s best-match selection only resolves cross-column conflicts when one column has an exact match. When no column has an exact match, the matcher's column-priority tiebreaker fires, but it doesn't respect query intent. A user typing `directed by smith and jones` who gets actors back is getting the wrong column entirely.

**Spec for v1 (narrow scope):**

Hard column gating for four cue patterns:
- `directed by <cluster>` → `allowed_columns = ['Director']`
- `written by <cluster>` → `allowed_columns = ['Writer']`
- `starring <cluster>` → `allowed_columns = ['Actor']`
- `featuring <cluster>` → `allowed_columns = ['Actor']`

Implementation: `fuzzy_match_cluster` accepts `allowed_columns` parameter. Default (None) preserves all-column behavior. Cue inference happens in `normalize_query` before each cluster is matched: walk left from cluster start, check the previous N tokens against cue vocabulary.

**Deliberately deferred from v1:**
- `with` cue (ambiguous: `films with brad pitt` vs `films with great cinematography` vs `films with no listed director`).
- `on / at / near` Locations cues (already handled by C-1a's preposition trigger; redundant gating could conflict with phrase pre-pass for landmarks like `at coit tower`).
- Per-cluster cue inference for queries with multiple distinct intents (e.g. `films starring alan arkin filmed at coit tower`). v1 supports this naturally if cue detection is local to each cluster.

**Estimated work:** half day. Includes design note (~1 page), implementation, unit tests for the four cues, regression sweep against targeted tests.

**Open design questions to resolve in the design note:**
- Conflict handling when a cluster has cues on both sides.
- Fallback when a gated column has no candidates at all (return None vs. fall back to all columns).
- STOP_WORDS interaction (cue tokens like `by` and `with` may overlap with stop words; cue detection has to operate on the original word list, not the filtered one).

### Partial-name path tightening (revised N-2)
**Priority: medium. Better designed before threshold-tweaking.**

Bare single-word clusters that aren't covered by C-1a's preposition trigger or F-1b's column gating still hit the partial-name path in `fuzzy_match_cluster` and produce questionable corrections:

```
films from larkin to polk      (NOW FIXED via from-to trigger)
films starring tom and jerry    (jerry → Ken Berry — F-1b doesn't kill this since gating
                                 to Actor still runs partial-name search within Actor)
films featuring larkin           (larkin → Alan Arkin if cluster reaches matcher)
```

**The threshold-only fix is insufficient.** Pure ratio thresholds can't separate good cases from bad: `hithcok → hitchcock` (0.875) and `broadway → roday` (0.769) are 0.10 apart, so any cliff between them risks losing legitimate typo corrections. Length floors help but don't solve it (`larkin` at 6 chars, ratio 0.91 against `arkin`, passes any reasonable len + ratio rule).

**Structural alternatives worth designing:**
- Require near-prefix or near-suffix alignment (use `SequenceMatcher.get_matching_blocks` to check whether the longest match starts at position 0 of the shorter string or extends to the end).
- Require absolute character overlap above a floor, not just ratio.
- Combine: require either an exact last-name match OR (alignment AND ratio AND length).

**Estimated work:** one day for design + implementation + validation against the 73-test internal suite (which contains the legitimate typo cases this change must not regress).

**Why deferred behind F-1b:** F-1b reduces how often the partial-name path runs in practice (gating to specific person columns when cues exist). Knowing how much problem remains after F-1b lands would calibrate this work.

### N-3 — 73-test internal normalizer suite re-run
**Priority: medium. Due before declaring normalizer stable.**

Re-run the 73-test internal suite against the post-N-1/F-1a/C-1a/C-1a.1/F-1b normalizer. Confirms no legitimate corrections regressed and calibrates the partial-name path tightening. Should run after F-1b lands and before partial-name tightening, then again after tightening.

---

## Open items — lower priority

### D-1 — Locations dataset typo repair
**Priority: medium. Not a normalizer fix.**

Diagnostic from May 7 surfaced 11+ misspellings in Locations free-text: `larken`, `barlett`, `buchannan`, `chestnust`, `misison`, `shotweel`, `sporfford`, `tayor`, `mccollough`, `jenning`, `kearney`. Predicate substring-match coverage holes that no normalizer change can fix.

### F-2 — Locations cutoff calibration
**Priority: low.**

`FUZZY_CUTOFFS['Locations'] = 0.65` is uniquely loose. With F-1a's best-match selection, no longer catastrophic, but still produces low-quality fuzzy hits when no other column qualifies. Worth a calibration pass against the 73-test internal suite once F-1b ships.

### C-1b — Additional cross-street and location patterns
**Priority: low.**

Patterns not yet covered by C-1a / C-1a.1:
- `films at the corner of <street> and <street>` (no preposition before either street)
- `films at the <street>` (article between preposition and street defeats trigger b's adjacency requirement)
- `films <verb-ing> <street>` (no preposition, not a cue, e.g. `films featuring market`)
- Bidirectional cross-street: `<street> and <locked>` where the locked anchor appears second

None are blocking. Easy wins to consider first when picked up: article-skip in trigger b (`at the castro`), bidirectional extension in trigger c.

### D-2 — Data-repair workflow
**Priority: low.**

The May 7 derived-vs-canonical diagnostic is itself a reusable artifact. A documented pattern for using it across columns (Locations now, Neighborhood in Phase E) would prevent ad-hoc repairs from drifting in style.

---

## Suggested order for tomorrow

1. **F-1b v1 design note** (~30 min). Resolves the open design questions before coding.
2. **F-1b v1 implementation** (~half day). Hard column gating for `directed by`, `written by`, `starring`, `featuring`.
3. **Re-run targeted normalizer tests** to see what's still broken after F-1b.
4. **Decide whether partial-name path tightening is still urgent** based on results. If `tom and jerry → tom and ken berry` is the only remaining failure, partial-name tightening becomes the next item. If F-1b leaves more residual issues, scope out further before committing to partial-name work.
5. **N-3 re-run** after both ship.
6. **THEN T15/T18, then full T1–T34 re-run** to confirm nothing regressed.

Do not run e2e tests until all four targeted-test failures from May 8 are clean.






## Recently shipped

### Today (May 8)

- ✅ **C-1a.1** (cross-street continuation locks): handles `<locked> and <street>`, `<locked> & <street>`, `<locked> between <street> and <street>`. Verified against 6 cross-street query shapes including 3-way chains.
- ✅ **DOMAIN_WORDS expansion**: added `television`, `tv`, `show`, `shows`, `series`, `episode`, `episodes`. Prevents media vocabulary from entering cluster extraction. Kills `films and television shows → films and barry levinson shows`.
- ✅ **`from <street> to <street>` standalone range trigger**: handles `films from larkin to polk` without making `from` a general Locations preposition (preserves year-range queries like `films from 1985`).

### Earlier this week

- ✅ N-1: phrase pre-pass + street-context pre-pass (suffix-anchored). May 6.
- ✅ F-1a: best-match selection in `fuzzy_match_cluster`, raw-ratio with exact-priority. May 6 (initial) + May 7 (revised scoring).
- ✅ C-1a: canonical SF streets vocabulary + preposition trigger. May 7.

T1–T34 all passed against the new gpkg (May 8 morning run). T15 and T18 now return correct counts (12 films) matching the post-swap baseline.

---

## Open items — queued for tomorrow (May 9)

### F-1b v1 — Hard column gating for strong cues
**Priority: high. Blocks declaring normalizer stable.**

Targeted normalizer testing (May 8) revealed that `fuzzy_match_cluster` still allows wrong-column matches under strong cues. Examples:

```
films directed by smith and jones
→ films directed by alexis smith and dean jones    (Actor, but cue says Director)

films starring tom and jerry
→ films starring tom and ken berry                 (partial-name path matches Berry surname)
```

`F-1a`'s best-match selection only resolves cross-column conflicts when one column has an exact match. When no column has an exact match, the matcher's column-priority tiebreaker fires, but it doesn't respect query intent. A user typing `directed by smith and jones` who gets actors back is getting the wrong column entirely.

**Spec for v1 (narrow scope):**

Hard column gating for four cue patterns:
- `directed by <cluster>` → `allowed_columns = ['Director']`
- `written by <cluster>` → `allowed_columns = ['Writer']`
- `starring <cluster>` → `allowed_columns = ['Actor']`
- `featuring <cluster>` → `allowed_columns = ['Actor']`

Implementation: `fuzzy_match_cluster` accepts `allowed_columns` parameter. Default (None) preserves all-column behavior. Cue inference happens in `normalize_query` before each cluster is matched: walk left from cluster start, check the previous N tokens against cue vocabulary.

**Deliberately deferred from v1:**
- `with` cue (ambiguous: `films with brad pitt` vs `films with great cinematography` vs `films with no listed director`).
- `on / at / near` Locations cues (already handled by C-1a's preposition trigger; redundant gating could conflict with phrase pre-pass for landmarks like `at coit tower`).
- Per-cluster cue inference for queries with multiple distinct intents (e.g. `films starring alan arkin filmed at coit tower`). v1 supports this naturally if cue detection is local to each cluster.

**Estimated work:** half day. Includes design note (~1 page), implementation, unit tests for the four cues, regression sweep against targeted tests.

**Open design questions to resolve in the design note:**
- Conflict handling when a cluster has cues on both sides.
- Fallback when a gated column has no candidates at all (return None vs. fall back to all columns).
- STOP_WORDS interaction (cue tokens like `by` and `with` may overlap with stop words; cue detection has to operate on the original word list, not the filtered one).

### Partial-name path tightening (revised N-2)
**Priority: medium. Better designed before threshold-tweaking.**

Bare single-word clusters that aren't covered by C-1a's preposition trigger or F-1b's column gating still hit the partial-name path in `fuzzy_match_cluster` and produce questionable corrections:

```
films from larkin to polk      (NOW FIXED via from-to trigger)
films starring tom and jerry    (jerry → Ken Berry — F-1b doesn't kill this since gating
                                 to Actor still runs partial-name search within Actor)
films featuring larkin           (larkin → Alan Arkin if cluster reaches matcher)
```

**The threshold-only fix is insufficient.** Pure ratio thresholds can't separate good cases from bad: `hithcok → hitchcock` (0.875) and `broadway → roday` (0.769) are 0.10 apart, so any cliff between them risks losing legitimate typo corrections. Length floors help but don't solve it (`larkin` at 6 chars, ratio 0.91 against `arkin`, passes any reasonable len + ratio rule).

**Structural alternatives worth designing:**
- Require near-prefix or near-suffix alignment (use `SequenceMatcher.get_matching_blocks` to check whether the longest match starts at position 0 of the shorter string or extends to the end).
- Require absolute character overlap above a floor, not just ratio.
- Combine: require either an exact last-name match OR (alignment AND ratio AND length).

**Estimated work:** one day for design + implementation + validation against the 73-test internal suite (which contains the legitimate typo cases this change must not regress).

**Why deferred behind F-1b:** F-1b reduces how often the partial-name path runs in practice (gating to specific person columns when cues exist). Knowing how much problem remains after F-1b lands would calibrate this work.

### N-3 — 73-test internal normalizer suite re-run
**Priority: medium. Due before declaring normalizer stable.**

Re-run the 73-test internal suite against the post-N-1/F-1a/C-1a/C-1a.1/F-1b normalizer. Confirms no legitimate corrections regressed and calibrates the partial-name path tightening. Should run after F-1b lands and before partial-name tightening, then again after tightening.

---

## Open items — lower priority

### D-1 — Locations dataset typo repair
**Priority: medium. Not a normalizer fix.**

Diagnostic from May 7 surfaced 11+ misspellings in Locations free-text: `larken`, `barlett`, `buchannan`, `chestnust`, `misison`, `shotweel`, `sporfford`, `tayor`, `mccollough`, `jenning`, `kearney`. Predicate substring-match coverage holes that no normalizer change can fix.

### F-2 — Locations cutoff calibration
**Priority: low.**

`FUZZY_CUTOFFS['Locations'] = 0.65` is uniquely loose. With F-1a's best-match selection, no longer catastrophic, but still produces low-quality fuzzy hits when no other column qualifies. Worth a calibration pass against the 73-test internal suite once F-1b ships.

### C-1b — Additional cross-street and location patterns
**Priority: low.**

Patterns not yet covered by C-1a / C-1a.1:
- `films at the corner of <street> and <street>` (no preposition before either street)
- `films at the <street>` (article between preposition and street defeats trigger b's adjacency requirement)
- `films <verb-ing> <street>` (no preposition, not a cue, e.g. `films featuring market`)
- Bidirectional cross-street: `<street> and <locked>` where the locked anchor appears second

None are blocking. Easy wins to consider first when picked up: article-skip in trigger b (`at the castro`), bidirectional extension in trigger c.

### D-2 — Data-repair workflow
**Priority: low.**

The May 7 derived-vs-canonical diagnostic is itself a reusable artifact. A documented pattern for using it across columns (Locations now, Neighborhood in Phase E) would prevent ad-hoc repairs from drifting in style.

---

## Suggested order for tomorrow

1. **F-1b v1 design note** (~30 min). Resolves the open design questions before coding.
2. **F-1b v1 implementation** (~half day). Hard column gating for `directed by`, `written by`, `starring`, `featuring`.
3. **Re-run targeted normalizer tests** to see what's still broken after F-1b.
4. **Decide whether partial-name path tightening is still urgent** based on results. If `tom and jerry → tom and ken berry` is the only remaining failure, partial-name tightening becomes the next item. If F-1b leaves more residual issues, scope out further before committing to partial-name work.
5. **N-3 re-run** after both ship.
6. **THEN T15/T18, then full T1–T34 re-run** to confirm nothing regressed.

Do not run e2e tests until all four targeted-test failures from May 8 are clean.




# Normalizer Open Items — Status as of May 7, 2026




## Recently shipped (today)

- ✅ **N-1**: Phrase pre-pass (landmarks) + street-context pre-pass (suffix-anchored streets). May 6.
- ✅ **F-1a**: Best-match selection in `fuzzy_match_cluster`, raw-ratio with exact-priority and column-tiebreaker. May 6 (initial) + May 7 (revised scoring).
- ✅ **C-1a**: Canonical SF streets vocabulary + preposition trigger (`on/at/near + street n-gram`). May 7.

T15 and T18 pass against the new gpkg. T1–T34 regression sweep pending.

---

## Open items

### D-1 — Locations dataset typo repair
**Priority: medium. Not a normalizer fix.**

The C-1a diagnostic (canonical-vs-derived vocabulary comparison) surfaced 11+ misspellings in Locations free-text where street names are written incorrectly: `larken`, `barlett`, `buchannan`, `chestnust`, `misison`, `shotweel`, `sporfford`, `tayor`, `mccollough`, `jenning`, `kearney` (likely should be `kearny`).

These create predicate-substring-match coverage holes — a query for `films on bartlett` cannot match a row stored as `Barlett St`, even with C-1a in place. The fix is data repair, not normalizer changes.

**Scope to define:** Which spellings are confirmed typos vs. intentional variants. Whether to preserve raw values in a `Locations_raw` column. Whether this is a one-off repair or the start of a broader data-cleanliness sweep across columns. Whether Phase E's Neighborhood column should be inspected for the same class of issue before adding it.

### F-1b — Context-aware column gating
**Priority: low (was high before F-1a + C-1a shipped).**

Originally proposed as the architectural answer to cross-column fuzzy permissiveness. Spec: per-cluster intent inference based on cue words (`starring`, `featuring`, `directed by`, `written by`, `at`, `on`, etc.), routing each cluster to a subset of eligible columns.

Demoted because F-1a's best-match selection plus C-1a's preposition trigger collectively resolve the catastrophic cases. F-1b is now about precision in genuinely ambiguous clusters — where two columns score legitimately above their cutoffs and cue context would tip the right way. Real but no longer urgent.

**Open design questions for whenever this is picked up:**
- Per-cluster intent inference algorithm (walk left/right N tokens, check cue vocabulary).
- Conflict resolution when cluster is bracketed by conflicting cues.
- Fallback when no cue is detected (preserve current all-column matching).
- STOP_WORDS interaction (`with`, `at`, `on` are currently stop words; cue detection has to run before stop-word filtering or operate on the original word list).

A one-page design note is the prerequisite before any implementation.

### C-1b — Cross-street, ampersand, and broader location contexts
**Priority: low.**

C-1a's preposition trigger covers `on/at/near + street`. It does NOT cover:

- `films at <street> and <street>` (cross-street construction)
- `films on <street> & <street>` (ampersand)
- `films between <street> and <street>` (between construction)
- `films at the <street>` (article between preposition and street)
- `films <verb-ing> <street>` (no preposition, e.g., `films featuring market`)

The Locations data has many free-text rows in these forms (`California & Larkin`, `Bay St between Larkin and Hyde`, etc.), so users may eventually phrase queries this way. None blocking T15/T18 today.

**Easy wins to consider first when this is picked up:** ampersand/and constructions probably share infrastructure; the article skip (`at the castro`) is a one-line tweak to trigger b's adjacency check.

### F-2 — Locations cutoff calibration
**Priority: low.**

`FUZZY_CUTOFFS['Locations'] = 0.65` is uniquely loose among the column cutoffs (others are 0.75 or 0.80). The original rationale was that Locations values are long free-text strings, so short queries need a loose ratio to match.

With F-1a's best-match selection, the 0.65 cutoff is no longer catastrophic — wrong-column matches lose to right-column matches via raw-ratio comparison. But 0.65 may still produce spurious low-quality Locations matches in cases where no other column has a candidate. Worth a calibration pass against the 73-test internal normalizer suite.

### N-2 — Short-cluster cutoff floor
**Priority: very low (mostly subsumed).**

April 26 open item: bump the cluster-length floor for fuzzy matching to prevent short single-word clusters from matching person-column last names too aggressively.

Mostly subsumed by C-1a (which prevents `on larkin` from reaching the matcher at all) and F-1a (which prevents the catastrophic cross-column cases). Remaining gap: `films featuring larkin` — bare `larkin` with a person-cue preposition, no Locations preposition. Currently returns no correction (safe), but if any future test query produces a bad match here, N-2 is the principled backstop.

### N-3 — 73-test internal normalizer suite re-run
**Priority: medium, due before declaring normalizer stable.**

Re-run the 73-test internal suite (which the project already maintains) against the post-N-1/F-1a/C-1a normalizer. Confirms no legitimate corrections regressed and calibrates the new scoring. Pending T1–T34 pass first.

### D-2 — Data-repair workflow
**Priority: low.**

The D-1 diagnostic (compare derived vocabulary against canonical) is itself a reusable artifact for finding suspect tokens in any new column. A documented pattern for using it across columns (Locations now, Neighborhood in Phase E, Title if needed) would prevent ad-hoc repairs from drifting in style.

---

## Closed during this work

- **N-2 backstop urgency** — most cases now handled by N-1 + C-1a + F-1a.
- **F-1 (the umbrella)** — split into F-1a (shipped) and F-1b (deferred).
- **C-1 (the umbrella)** — split into C-1a (shipped) and C-1b (deferred).
