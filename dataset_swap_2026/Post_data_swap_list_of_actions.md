# Five phases, smallest dependency first.

## Phase A — Data load and schema sanity. 

Get the CSV loading into the same shape your pipeline expects, with Neighborhood and Supervisor_District as new columns. Sanity-check by running a few existing queries that don't touch neighborhoods at all ("films directed by hitchcock," "films on market street"). If those pass against the new dataset, your load is clean and the rest of the pipeline doesn't know anything has changed yet. This phase should not require touching any prompts.


## Phase B — Schema documentation. 

Update the schema reference inside Step 4's prompt and Step 6's prompt to mention the two new columns. This is a no-op behaviorally — the LLM won't use Neighborhood until something in a query asks for it — but it makes the schema honest. Still no functional change to query handling.

## Phase C — Re-run the existing test suite. 

T1–T34 against the new dataset. This is the critical gate. If anything regresses, you want to know now, before adding new behavior. Most likely outcome: a small handful of tests need their expected counts updated (the dataset grew from 2,084 to 2,214 rows; some "how many films at Golden Gate Bridge" answers will change), but no semantic regressions. If you see semantic regressions, stop and investigate before going further.

## Phase D — Add neighborhood support to Step 4. 

Add Neighborhood to the allowed-fields list. Add 1–2 few-shot examples showing the pattern: "films in north beach" → Neighborhood == "North Beach" (note: == not contains, since neighborhood values are a closed vocabulary). Decide whether you want exact-match or contains-match semantics — I'd argue exact, given that SFgov uses a controlled vocabulary of ~40 neighborhood names. This is the first phase where new query shapes become possible.

## Phase E — Normalizer touches. 

Now you handle the multi-word neighborhood vocabulary. Two questions to answer first: are the neighborhood names already protected by your existing is_unjustified_expansion guard from the April 26 fixes, or do they need explicit handling? And does the cluster extractor split "north beach" or "russian hill" the way it used to split "golden gate bridge"? Test before changing. The N-1 phrase pre-pass from your open-items doc is the right tool if surgery is needed, but you may find the existing guards cover enough cases that you can defer N-1.

## Phase F — Test additions. 

Add T35–T40 (or whatever your numbering becomes) covering the new query shapes: single-task neighborhood retrieve, neighborhood + Year, neighborhood + Director (cross-field AND), neighborhood-based count, neighborhood + location-text (does "films in mission on valencia st" work the way you'd want — both clauses applied, or one redundant). Run them, fix anything that breaks, document.