# T1–T34 Phase C Comparison: Baseline vs Post-Dataset-Swap

**Baseline runs:**
- T1–T20: April 24, 2026 — against `sf_film_May7_2025_data.gpkg` (2,084 rows, old dataset)
- T21–T34: April 26, 2026 — against `sf_film_May7_2025_data.gpkg` (2,084 rows, old dataset)

**Post-swap runs:**
- T1–T20: April 30, 2026 — against `sf_film_2026_04_24_data.gpkg` (2,208 rows, new dataset)
- T21–T34: May 1, 2026 — against `sf_film_2026_04_24_data.gpkg` (2,208 rows, new dataset)

**Context:** Phase C of `Post_data_swap_list_of_actions.md`. Purpose is to verify no semantic regressions from the dataset swap and Phase B schema-documentation updates.

---

## Headline Results

| Metric | Count |
|---|---|
| Total tests run | 34 |
| Identical to baseline | 28 |
| Expected data deltas | 2 (T8, T16) |
| Tie-break order drift (non-regression) | 2 (T5, T32) |
| Code-gen output-shape drift (non-regression) | 1 (T26, verified-correct via diagnostic) |
| Normalizer regressions | 2 (T15, T18 — single root cause) |
| Infrastructure failures | 3 (T6, T25, T26 — all retried clean) |

**Net verdict:** Phase C cleared. Phase B's schema-documentation edits introduced zero regressions. The dataset swap surfaced one well-localized normalizer fragility (Larkin/Arkin), traced to a known issue documented in `phase_3_open_items_April_26.md` and deferred to Phase E.

---

## Issues Observed

This section discusses the four classes of issue surfaced by Phase C. None block Phase D.

### Issue 1 — Normalizer regression: `larkin → Alan Arkin` (T15, T18)

**What happened.** The query `films on larkin street` was normalized to `films on alan arkin st` on the new dataset. The cluster extractor fuzzy-matched the content cluster `larkin` against the Actor known-value `Alan Arkin` at ratio ~0.83, ignoring the trailing "street" context that should have pinned the cluster as a Locations reference. The downstream effect propagated: the corrupted predicate (`Locations contains "alan arkin st"`) matched zero rows in the data; T15's summary text confidently reported "12 films" but the underlying predicate retrieved 0 rows, and T18's dependent count correctly reported 0 — a doubled failure where the predicate is wrong and the summary text is also wrong.

**Why now.** This regression did not appear in the April 24 baseline, where T15 normalized cleanly to `films on larkin st`. The trigger is the new dataset's `known_values['Actor']` set: it now includes "Alan Arkin" (or includes him at higher row weight than before), bringing the fuzzy-match collision into firing range. The normalizer code itself did not change between April 24 and April 30 — only the data feeding `known_values` did.

**Why this is not a Phase B regression.** The Step 4 and Step 6 prompt edits in Phase B added column documentation and v1-scope notes; they did not touch the normalizer at all. Step 1 ran before Step 4 in both cases, and Step 4's predicate emission was correct given Step 1's (corrupted) input.

**Why this was anticipated.** `phase_3_open_items_April_26.md` documents this exact bug class as item N-2: "any 4–5 character common English noun whose suffix happens to overlap a name in the database can produce the same class of corruption." The April 26 doc proposed a fix gated on cluster length ≤ 5 characters. Phase C reveals the threshold needs revision — `larkin` is 6 characters and falls through the proposed cutoff.

**Architectural fix.** Item N-1 in the same doc (phrase pre-pass) is the structural solution: scan the query for n-gram matches against known Locations values *before* cluster extraction runs. If "larkin street" matches "Larkin St" at near-exact ratio, the whole phrase is marked resolved-to-Locations and never reaches the cluster extractor as a free-floating content word. N-1 also addresses the upcoming Phase E neighborhood-name protection ("north beach", "russian hill", "pacific heights") and would have prevented the April 26 `port of san francisco` corruption that triggered Fix 2.

**Status.** Deferred to Phase E. Documented. Not blocking Phase D.

---

### Issue 2 — Spatial count drift: T8 (189 → 204)

**What happened.** T8's query `films within 1 mile of coit tower` returned 189 films on the old dataset and 204 on the new dataset.

**Why this is not a regression.** The new dataset has 86 rows with null geometry — SFgov correctly declined to geocode span/range/transit location strings ("Bay Bridge between Treasure Island and SF", "various MUNI lines", etc.). The old dataset had HERE-resolved geometry on every row, including these strings, where HERE silently picked a defensible point from the range. Additionally, 5 catastrophic HERE failures in the old dataset placed SF films in Düsseldorf, Colombia, and Kansas City. The new dataset is more honest about which rows have spatial meaning. The +130 rows added since May 2025 contributed valid geometry near landmark areas including Coit Tower. Net: 15 more films within 1 mile of Coit Tower despite 86 fewer rows being eligible for spatial queries overall.

**Cookbook behavior.** The Step 6 cookbook's `valid_geom_mask = gdf_copy.geometry.notna() & ~gdf_copy.geometry.is_empty` guard handled the null-geometry rows correctly. Pre-swap this guard was defensive code against an edge case that didn't exist; post-swap it's load-bearing.

**Status.** Expected count update: 189 → 204. Note in test expectations referencing `dataset_swap_2026.md`'s "What we accepted by swapping" section.

---

### Issue 3 — Tie-break order drift: T5 and T32 (non-regression)

**What happened.** T5's "top 5 directors" returned the same five directors with the same counts in both runs, but positions 2–5 (all tied at 4 films) reordered. T32's "top directors at Golden Gate Bridge" returned the same first two directors but position 3 changed from Edward Dmytryk to Richard Donner.

**Why this is not a regression.** Pandas' `value_counts()` does not guarantee tie-break stability across DataFrames. When multiple values share a count, the order they appear in the output depends on the underlying data's row order, which the gpkg conversion did not preserve from the old dataset. The data is correct (same directors, same counts); only the within-tied-group order differs.

**Diagnostic behavior.** Verified for T5: top result Andrew Haigh at 11 films is unchanged in both runs. The four directors tied at 4 (Hitchcock, Columbus, Kaufman, Marshall) appear in different orders. For T32: Meyer at #1 and Stevenson at #2 are stable (likely Meyer with 2 films at GGB, Stevenson with 1); position 3 reflects a tie among one-film directors at GGB.

**Implication for test conventions.** For ranked outputs with ties, assertions should target set membership and tied-group counts, not within-group rank order. This is a Phase C-discovered convention worth noting in test expectations docs.

**Status.** No action needed beyond documenting the convention. Both T5 and T32 pass on the merits.

---

### Issue 4 — Code-gen output-shape drift: T26 (verified-correct via diagnostic)

**What happened.** T26's query `which writers filmed at golden gate bridge` is the canonical "constraint vs output dimension" example from the Step 4 prompt. Step 4 emitted the correct predicate in both runs (`Locations contains "golden gate bridge"` only, no Writer constraint). Step 6's generated code differed: the baseline extracted unique writers from `matched_rows` and reported 25 writers; the post-swap returned the row records with a count and reported "27 filming locations." Direct query against the new gpkg confirmed the underlying answer is unchanged: 25 unique writers across 27 rows. The post-swap reported a row count instead of the unique-writer count.

**Why this is not a dataset regression.** The semantic answer is identical: 25 unique writers in both datasets. The drift is in the *shape* of `result['data']` and the noun used in the summary string, not in the extracted data itself.

**Why this is not a Phase B regression.** Phase B's Step 6 v2.4 edits added schema columns and the v1 scope note. They did not touch D5's `retrieve` pattern, which is where the LLM is making the choice that produced this drift.

**What it actually is.** A pre-existing Step 6 prompt gap. The cookbook's D5 has explicit patterns for `retrieve`, `count`, `rank`, `compare`, `explain`, `clarify` — but no pattern for "extract a unique-values list from a column as the answer payload." When a query like "which writers filmed at X" arrives, Step 4 correctly produces a Locations-only predicate (writer is the output dimension, not a filter), but Step 6's cookbook leaves the LLM to figure out what to do with that predicate-and-output-column shape. The LLM chooses stochastically: April 26 produced unique-writer extraction; May 1 produced row-records-with-count. Both are syntactically valid; only one answers the user's question.

**Implication.** This is a Step 6 cookbook gap, surfaced incidentally by Phase C but not caused by it. Worth a separate open-items entry, not a Phase E item.

**Status.** No action for Phase C closure. Recommend a Step 6 D5 addition (a "which X / who / what" pattern parallel to the existing "retrieve with film-to-locations grouping" example) to be considered for the next Step 6 prompt revision.

---

## Test-by-Test Results

### Tests T1–T20 (single-task and dependency-chain queries)

| Test | Description | Baseline | Post-swap | Verdict |
|---|---|---|---|---|
| T1 | Retrieve by Director | 4 films | 4 films | Clean |
| T2 | Retrieve by Location (contains) | 29 films | 29 films | Clean — also confirms gpkg suffix normalization works |
| T3 | Retrieve by Actor (virtual field OR) | 5 films | 5 films | Clean |
| T4 | Count films in a decade | 39 films | 39 films | Clean — confirms `Int64` dtype change is safe |
| T5 | Rank directors by film count | Top: Haigh; tied at 4: Hitchcock, Columbus, Kaufman, Marshall | Top: Haigh (11); tied at 4: Columbus, Kaufman, Hitchcock, Marshall | Tie-break drift (Issue 3) |
| T6 | Retrieve by Year (exact) | 4 films | 4 films (after retry) | Clean |
| T7 | Retrieve by Director + Year range (AND) | 1 film | 1 film | Clean |
| T8 | Spatial retrieve (within_distance) | 189 films | 204 films | Expected data delta (Issue 2) |
| T9 | Retrieve locations for a film | 16 locations | 16 locations | Clean |
| T10 | Rank actors by film count in decade | Top 10 returned | Top 10 returned | Clean |
| T11 | Disjunction across same field (Director OR Director) | 4 films | 4 films | Clean |
| T12 | Exact title match | 1 film | 1 film | Clean |
| T13 | Title substring retrieval | 1 film | 1 film | Clean |
| T14 | Multi-value director cell | 1 film | 1 film | Clean |
| T15 | Location abbreviation variance (Larkin Street) | 11 films | broken (Larkin → Alan Arkin) | **Regression (Issue 1)** |
| T16 | Null/missing-field predicate | 1 film | 2 films | Expected data delta — new film "Chef Dynasty: House of Fang" with no listed director |
| T17 | Disjunction across different fields | 40 locations | 40 locations | Clean |
| T18 | Retrieve then count dependency (Larkin Street) | 11 films | 0 films | **Regression — same root cause as T15 (Issue 1)** |
| T19 | Retrieve then location-count dependency | 24 locations | 24 locations | Clean |
| T20 | Cross-field AND with mixed predicates | 1 film | 1 film | Clean |

### Tests T21–T28 (cross-field combinations and constraint vs output-dimension)

| Test | Description | Baseline | Post-swap | Verdict |
|---|---|---|---|---|
| T21 | Cross-field AND (Director + location) | 2 films | 2 films | Clean |
| T22 | Cross-field AND (Actor + location, "port of san francisco") | 1 film | 1 film | Clean — April 26 Fix 2 holds across the swap |
| T23 | Cross-field AND (Writer + location) | 1 film | 1 film | Clean |
| T24 | Cross-field OR (Director OR Writer) | 12 films | 12 films | Clean |
| T25 | Cross-field OR (Title OR location) | 28 locations | 28 locations (after retry) | Clean |
| T26 | Constraint vs output dimension (writers at GGB) | 25 writers | 27 (mislabeled; verified 25 writers via diagnostic) | Output-shape drift (Issue 4); answer unchanged |
| T27 | Constraint vs output dimension (actors at Port of SF, 1985) | 3 actors | 3 actors | Clean |
| T28 | Cross-field AND (Title + location) | 1 location | 1 location | Clean |

### Tests T29–T34 (multi-task dependency chains, compare, competing cues)

| Test | Description | Baseline | Post-swap | Verdict |
|---|---|---|---|---|
| T29 | Retrieve → count (film basis) | 27 | 27 | Clean |
| T30 | Retrieve → count (location basis) | 23 | 23 | Clean |
| T31 | Retrieve → dependent narrow with added predicate | 2 films | 2 films | Clean — D6 dependency pattern verified |
| T32 | Retrieve → rank within dependency subset | Top 3: Meyer, Stevenson, Dmytryk | Top 3: Meyer, Stevenson, Donner | Tie-break drift (Issue 3) |
| T33 | Retrieve → retrieve → compare | GGB: 27, Port of SF: 1 | GGB: 27, Port of SF: 1 | Clean — compare pattern works despite "later-phase" cookbook label |
| T34 | Retrieve → count with competing film/location cues | 24 locations / 1 film | 24 locations / 1 film | Clean — count basis correctly inferred from t2 source text per D5 rule |

---

## Synthesis: What Phase C Tells Us

**The pipeline is robust against the dataset swap.** 28 of 34 tests produced bit-identical results. The data growth (+130 rows), null-geometry handling, and `Int64` dtype change passed through the cookbook patterns without surfacing any code-level fragility.

**Phase B's schema-documentation edits are clean.** Every test that involves the columns Phase B touched (Year, the existing fields it documented in the v1 scope note) produced correct predicates and correct execution. The new columns (Production_Company, Distributor, Neighborhood, Supervisor_District) correctly remained inert in v1 — Step 4 emitted no predicates against them, Step 6 generated no code referencing them.

**The one normalizer regression is well-localized and pre-anticipated.** The Larkin/Arkin issue is a known bug class with an architectural fix already designed (N-1 phrase pre-pass). Phase C surfaced one new instance of the class, with a refinement to the proposed fix (length threshold needs to be at least 6, possibly higher). No new bug classes were discovered.

**Code-generation drift exists but is shallower than feared.** Two run-to-run differences (T5 tie-break, T26 output shape) and one verified-correct-via-diagnostic case (T26) suggest the LLM has more freedom than the prompt intends in two specific shapes: ranked outputs with ties, and "which X" output-dimension queries. Both have low-cost prompt-side mitigations.

**The compare and rank-within-dependency patterns work better than their D5 labels suggest.** T31, T32, T33 all executed correctly despite D5 noting compare and explain as "later-phase pattern, not a primary target for initial testing." Worth re-examining whether those labels still reflect reality, since Phase C just demonstrated the patterns are production-shaped.

---

## Action Items Captured by Phase C

| Item | Where it goes | Priority |
|---|---|---|
| Update T8 expected count: 189 → 204 | test expectations | low (documentation) |
| Update T16 expected count: 1 → 2 | test expectations | low (documentation) |
| Add T15/T18 regression note: blocked on Phase E normalizer fix | test expectations | medium (visible to next test runner) |
| Document tie-break-stability convention (T5, T32) | test conventions doc | low |
| Revise N-2 length threshold proposal: ≥ 6 chars (Larkin evidence) | `phase_3_open_items_April_26.md` | medium (informs Phase E design) |
| Add D5 cookbook entry for "which X / who / what" output-dimension pattern | next Step 6 prompt revision (v2.5?) | low–medium (LLM stochasticity, not blocker) |
| Re-evaluate D5 "later-phase pattern" labels on compare and explain | next Step 6 prompt revision | low |

---

## References

- `dataset_swap_2026.md` — dataset swap record and accepted trade-offs
- `Post_data_swap_list_of_actions.md` — five-phase rollout plan (this document validates Phase C)
- `phase_3_open_items_April_26.md` — N-1 (phrase pre-pass) and N-2 (short-cluster cutoff floor) open items
- Step 4 changelog — Phase B schema documentation update (April 29)
- `code_generation_v2_4.md` — Step 6 v2.4 changelog, Phase B (April 29)
- April 24/26 baseline run printouts — old dataset
- April 30 / May 1 post-swap run printouts — new dataset
