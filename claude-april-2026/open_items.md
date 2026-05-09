# Open Items that need to be explored without any ordering 

### As a consequence of dataset_swap_2026
- It is worth flagging that "films in district 5" is a query shape that's now possible and currently unhandled. Track it in your open-items doc if it isn't already.

> The same thing applies to Neiughrborhoods, Production_company and Distributor!!

- Neighborhood match semantics (== vs contains) — defer until Phase E. Decision depends on whether the normalizer reliably canonicalizes neighborhood names from user queries; if yes, exact is cleaner given SFgov's closed ~40-value vocabulary; if normalization is unreliable, contains is more forgiving. Test cluster extractor behavior on "north beach", "russian hill", "pacific heights", "castro upper market" before deciding.

## Larkin street issue

- Update phase_3_open_items_April_26.md — note that N-2's 5-char length threshold is too low (Larkin = 6 chars), add Larkin as a documented case

### Why T15 reported success

T15's summary says Found 12 films filmed on Larkin Street. The summary string is the LLM's free-text wording — it saw that the source text was "alan arkin st" but apparently looked at the original-original query intent and wrote about Larkin Street. The actual count in result['data'] is 12, and the actual rows that were retrieved came from Locations contains "alan arkin st". There is no street called "Alan Arkin St" in San Francisco. The 12 matches are almost certainly false — possibly hitting "Arkin" appearances in some other location string by accident, possibly hitting nothing at all and the count is wrong somewhere upstream.
Worth verifying directly. Run this against your gpkg:

```python
df[gdf['Locations'].astype(str).str.contains('alan arkin st', case=False, na=False)]
```

I'd bet you get 0 rows, in which case the "12" in the T15 summary is coming from somewhere unexpected and the test is doubly broken — wrong query and wrong reported count. Or you get 12 rows where "arkin st" appears as a coincidental substring of something legitimate, in which case the query is wrong and the count is technically true but meaningless.
T18, by contrast, told the truth: 0 films. The dependent count task correctly reported what its (broken) parent retrieved.
What this means for Phase C
This is not a regression from the dataset swap. The cluster extractor's fuzzy-matching behavior would have done the same thing on the old dataset — "larkin" was always going to look more like "Alan Arkin" than like any director or any title in the database. The bug pre-existed; the test just didn't catch it before, or caught it and was filed as a known issue somewhere I don't see.
Worth a quick check: does this appear in phase_3_open_items_April_26.md or any earlier known-issues doc? Let me look.Searched project for “larkin Arkin fuzzy match cluster extractor street name”Searched project for “larkin Arkin fuzzy match cluster extractor street name”Found it. This is N-2 from your April 26 open-items doc, and the prediction in that doc named the exact mechanism that just bit you:

any 4–5 character common English noun whose suffix happens to overlap a name in the database can produce the same class of corruption.

larkin is six characters, but the failure mode is identical: a content-word cluster, dominantly a name-suffix shape (-arkin overlapping with Arkin), matching at ratio ~0.83 against Alan Arkin because the cluster extractor doesn't have a way to know that the trailing word "street" rules out the name interpretation.
The April 23 run of T15 (the "before" comparison from T11-T20_APRIL_22_10PM_run1_printout.txt and the more recent April 23 trace) shows larkin street normalizing cleanly to larkin st with no fuzzy-match correction. Something changed between April 23 and April 30. Three candidates:
Possibility 1: known_values changed. When you swapped to the new dataset, known_values for the Actor column changed too. The new dataset may include "Alan Arkin" where the old one didn't, or may include him in more rows, raising his fuzzy-match weight. This is the most likely explanation, and it's testable: 'Alan Arkin' in known_values['Actor'] against the new gpkg vs the old one.
Possibility 2: a tweak to the normalizer crept in. Less likely given everything else passed identically, but worth a glance at git history on query_normalizer.py (or wherever the cluster extractor lives) since April 23.
Possibility 3: stochastic LLM behavior in some upstream step. Unlikely — the normalizer is rule-based, not LLM-based, per the design notes. So this almost certainly isn't it.
The first one is my strong bet. The new dataset added films and presumably actors, and Alan Arkin is the kind of mid-profile actor likely to appear in SFgov updates from 2024–2026 ("Argo," "Going in Style," "The Kominsky Method" — though the latter is a series). Worth confirming.
What this means for Phase C and what to do about it
This is a regression introduced by the dataset swap, but not a regression caused by the schema-doc edits in Phase B. It's caused by known_values changing, which is downstream of the data swap itself. So Phase B's prompt edits are clean; the trouble is the cluster extractor's interaction with the new dataset's known-values set.
The N-2 fix from your April 26 open-items doc would resolve this exactly:

if ' ' not in cluster_text and len(cluster_text) <= 5, set cutoff = max(cutoff, 0.90) for that match attempt.

But "larkin" is 6 characters, so that specific cutoff wouldn't catch it as written. Two adjustments to consider:

Bump the length threshold to 6 or 7. The reasoning in the open-items doc was "4–5 character common English nouns," but larkin shows the failure mode reaches further. The tradeoff (rejecting some legitimate short typos like meyrs → Meyer) gets steeper at 6+ characters but isn't catastrophic — partial-name matching on full last names still works.
Or do N-1 instead/as well — the phrase pre-pass that recognizes "larkin street" as a unit before clustering. That's the more architecturally correct fix and also future-proofs against the neighborhood-name issues you'll hit in Phase E.

Honestly, given that you're heading into Phase E anyway, N-1 is the better investment. It solves Larkin Street and protects "north beach," "russian hill," "pacific heights" before Phase D enables Neighborhood as a filter field. Two birds, one well-designed stone.
Recommendation
For Phase C closure: don't fix this now, but document it explicitly as a Phase C-discovered regression so it doesn't get forgotten. The Phase B prompt changes are not at fault, and stopping Phase C to fix the normalizer would conflate two separate workstreams. T15 and T18 should be marked as "regressions, traced to N-2/N-1, deferred to Phase E."
Specifically I'd:

Run the diagnostic to confirm the known_values['Actor'] hypothesis: check whether "Alan Arkin" is in the new dataset's actor columns and was absent (or rarer) in the old one. This tells you whether the regression is data-driven or normalizer-drift.
Mark T15 and T18 as regressed in your test expectations file. They're broken, the cause is known, the fix is queued for Phase E.
Continue with T21–T34. If the Larkin Street issue is the only one of its kind in the remaining tests, Phase C is "done with one known regression." If T21–T34 surfaces more cluster-extractor regressions, you may want to escalate N-1 to Phase D-prerequisite work rather than letting it slide to Phase E.
Update phase_3_open_items_April_26.md with a note that N-2's length threshold needs revision based on Phase C evidence — the 5-char limit was an undershoot.

The "boooo" reaction is fully warranted, but the silver lining is real: Phase C did its job. It caught a regression that would have shipped to users otherwise. That's exactly what a regression gate is for.


## For Step 6 open issues (or whichever doc tracks code-gen quality):

**noticed in T26 re-run**

Step 6 lacks an explicit pattern in D5 for "which X" / "who" / "what" output-dimension queries — i.e., when the predicate filters rows but the answer payload is a unique list of values from a specific column (writers, directors, actors, titles, etc.). When this pattern arises, the LLM stochastically chooses between (a) extracting unique values from the relevant column, or (b) returning records with a row count. Both are syntactically valid, but only (a) answers the user's question. Add a few-shot in D5 covering this pattern, parallel to the existing "retrieve with film-to-locations grouping" example. Surfaced by T26 on May 1, 2026.


## L-1 (Locations semantics) — that tracks the question of whether substring-match should be widened to bare-token form for streets. That item gets debated separately, with its own test queries and its own decision record. It probably belongs in Phase E alongside the Neighborhood work, since both are "how should the predicate layer reason about location references" questions.

## D-1: Locations dataset typo repair. Scope: the 11 obvious typos from the diagnostic, plus a manual review of Category 2/3 to identify the 5–10 streets that might be canonical-list gaps. Separate document, separate diff, separate review.

## D-2: Locations data-repair workflow. Scope: a documented pattern for finding and fixing typos in Locations (and later Neighborhood). The diagnostic you just ran is half of this — finding suspect tokens by comparing derived-vs-canonical. The other half is the actual repair: how to write the corrections back into the gpkg, whether to preserve raw, whether to track provenance.

## both D-1 and D-2 are based on the following conversation on May-7-2026

```
You're absolutely right, and the diagnostic is more revealing than either of us probably expected. Let me tell you what I see in this output, because it's worth being explicit before talking about repair.

## Three categories in those 66 tokens

**Category 1 — Misspellings in the dataset.** These are the ones you'd want to repair:

- `larken` (should be `larkin`)
- `barlett` (should be `bartlett`)
- `buchannan` (should be `buchanan`)
- `chestnust` (should be `chestnut`)
- `misison` (should be `mission`)
- `shotweel` (should be `shotwell`)
- `sporfford` (should be `spofford`)
- `tayor` (should be `taylor`)
- `mccollough` (should be `mccullough`)
- `jenning` (probably should be `jennings`)
- `kearney` (likely should be `kearny` — SF spells it without the 'e')

That's 11 confirmed-or-likely typos. The fact that the regex extracted them at all means each one appears in Locations free-text in `<token> <suffix>` form at least once — meaning real rows in your gpkg have misspelled street names embedded in their address strings. `films on bartlett street` won't match a row that says `Barlett St` because predicate substring-match is exact, not fuzzy. Real coverage holes.

**Category 2 — Multi-word street fragments captured as single tokens.** These are streets the canonical list correctly stores as multi-word, but the regex pulled out only the last token:

- `chavez` (from `Cesar Chavez St` → regex grabs `chavez st`, indexes `chavez`)
- `ness` (from `Van Ness Ave` → indexes `ness`)
- `haro` and `deharo` (from `De Haro St` → both forms extracted depending on tokenization)
- `jacinto` (from `San Jacinto Way`)
- `bruno` (from `San Bruno Ave`)
- `jose` (from `San Jose Ave`)
- `fernando` (from `San Fernando Way` or similar)
- `kerouac` (from `Jack Kerouac Alley`)
- `toklas` (from `Alice B Toklas Lane`)
- `goodlett` (from `Dr Carlton B Goodlett Pl`)
- `bayshore` (from `Bay Shore Blvd` — though canonical may store this as two words)
- `francois` (from `St Francois Pl` or similar)
- `germain` (from a saint-named street)
- `hallidie` (probably `Hallidie Plaza` or similar)
- `gavin`, `gate`, `milk`, `mays` (probably from compound names)

These aren't list-coverage failures — the streets *are* in the canonical list, just as multi-word entries. The regex was just too coarse to know that.

**Category 3 — Non-street artifacts.** The regex caught these because they appear before street-suffix words in Locations free-text, but they aren't street names:

- `embarcadero` (it's `The Embarcadero` — the leading article makes the regex extract just `embarcadero`, but `Embarcadero` is itself the street name — so this might actually be Category 2, depending on canonical-list convention)
- `island`, `point`, `peaks`, `view`, `heights`, `bridges`, `gate` (geographic feature words, often part of compound names)
- `fisherman's`, `mel's` (possessive-form fragments of landmark names: `Fisherman's Wharf`, `Mel's Diner`)
- `ferry`, `frontage`, `private`, `old`, `center`, `marathon`, `maritime`, `ramada`, `westin`, `nations`, `seventh`, `love` (compound name fragments — `Ferry Building`, `Old Mason`, `Maritime Plaza`, etc.)
- `o'farrell` (probably `O'Farrell Street`, which IS in the canonical list — the apostrophe normalization differs between sources)
- `adams`, `ana`, `alco`, `bannam`, `collingswood`, `conzelman`, `ferrera`, `herman`, `honda`, `louis`, `mar`, `rowland`, `shelley` (could be real streets the canonical list missed — these are worth specifically checking against the canonical source)

## What this tells you about the data

Two real problems, and they're separate workstreams:

**Problem 1 — Dataset has misspellings** (Category 1). 11+ typos in Locations free-text. These cause real coverage holes that no amount of normalizer work will fix, because the predicate layer does exact substring matching. A user querying `bartlett` cannot hit a row stored as `Barlett`. **The fix is repair the data, not the normalizer.**

**Problem 2 — Canonical list may have gaps** (parts of Category 2 and 3). Some of those tokens might be real streets the canonical source missed. Worth a manual review against your canonical source — but this is likely 5–10 streets, not 60.

## What this tells you about C-1a

C-1a was always going to ship with canonical-only, but the diagnostic now gives that decision additional weight. Here's why:

**Your idea of unioning derived with canonical would have spread the misspellings into the protective vocabulary.** With `larken` in the unioned vocabulary, a query for `films on larken` would lock the misspelled token. Predicate substring-match would then look for `larken` in Locations and hit the misspelled rows — but miss the correctly-spelled ones. You'd be encoding the dataset's typos into the query layer, making the bug invisible to users (the query "succeeds" by hitting bad data) and harder to fix later.

**Canonical-only is correct on principle, and the diagnostic confirms it.** Canonical-only keeps the typos out of the lock vocabulary. A user querying `films on bartlett` will:

- Lock `bartlett` (it IS in the canonical list as the correct spelling).
- Predicate substring-match for `bartlett` in Locations.
- Miss the rows stored as `Barlett` (incorrect spelling), hit the rows stored as `Bartlett` (correct spelling).
- Return fewer results than ideal — but the right rows.

This is the right failure mode. The user gets a correct-but-incomplete answer, and the missing rows are diagnosable as a *data* problem, not a *normalizer* problem.

## My honest take on what to do

**Ship C-1a as designed (canonical-only), don't touch the dataset yet.** Reasoning:

1. **C-1a is a normalizer fix; data repair is a separate workstream.** Conflating them produces a single PR that's hard to review and impossible to roll back independently. If C-1a turns out to have a bug, you don't want to revert the data fixes. If a data fix turns out to be wrong (misspelling we corrected was actually intentional, or a different city's `Barlett`), you don't want to revert C-1a.

2. **The data repair is its own thinking exercise.** Eleven likely typos look obvious from the diagnostic, but each one needs a decision: is the canonical spelling the right canonical spelling? Are there multiple rows affected? Should the original be preserved in a `Locations_raw` column? Is this fix one-off or is there a broader data-cleanliness sweep needed? Worth its own document and its own diff.

3. **Phase E is going to surface more of this.** When you add Neighborhood, you'll discover misspellings there too. Better to design a small data-repair workflow now and use it consistently across columns than to scramble fix Locations now and re-scramble for Neighborhood later.

4. **e2e tests can run with the typos still present.** T15 and T18 don't depend on the misspelled rows specifically — they depend on the larkin-related cluster behavior, which C-1a fixes. The misspellings produce a coverage hole that affects total row counts but doesn't depend on cluster extraction or fuzzy matching.

**My suggested sequencing:**

1. **Apply C-1a as patched.** Run the test queries. Confirm Alan Arkin still resolves and `films on van ness`, `films on larkin`, etc. all lock correctly.
2. **Run T15/T18.** If they pass against the new gpkg, ship N-1 + F-1a + C-1a as a coordinated bundle.
3. **Run T1–T34.** Confirm no regressions.
4. **Open a new item — call it D-1: Locations dataset typo repair.** Scope: the 11 obvious typos from the diagnostic, plus a manual review of Category 2/3 to identify the 5–10 streets that might be canonical-list gaps. Separate document, separate diff, separate review.
5. **Open a related item — D-2: Locations data-repair workflow.** Scope: a documented pattern for finding and fixing typos in Locations (and later Neighborhood). The diagnostic you just ran is half of this — finding suspect tokens by comparing derived-vs-canonical. The other half is the actual repair: how to write the corrections back into the gpkg, whether to preserve raw, whether to track provenance.

The diagnostic itself is now a reusable artifact. Save it somewhere. It's the kind of small tool that earns its keep every time the dataset changes.

Want to proceed with C-1a now and file D-1 as a new open item, or do you want to look at the data-repair question more carefully before running the patches?
```