These are good Phase 2 tests. They are not redundant with T1–T10, and several of them hit exactly the weaknesses your own April 20 notes say are still open.

Big picture: T11–T20 are much better as a **bug-exposure suite** than as a pure “did the happy path still work?” suite. That is the right move now, because your April 20 run established that the single-task baseline is real and that Step 4 is now actually feeding structured predicates into codegen again, instead of the generator reverse-engineering from `source` text.  

A few project-source takeaways first:

* Your April 20 handoff says the main carried-forward issue is **B2**: Step 4 now emits string-field `==` correctly, but Step 6 still translates string `==` as `str.contains(...)` for fields like `Director` and `Title`. That means substring-collision tests are exactly what you should add next. 
* The changelog and prompt confirm the intended IR supports `AND`, `OR`, `between`, numeric comparisons, spatial predicates, and dependency patterns, but there is **no explicit NOT / negation operator** in the allowed predicate schema as shown here. 
* Your handoff also says multi-task and nested queries with lite-preview are still untested, so cross-field OR and anything that pushes decomposition harder is valuable now. 
* The April 20 printout shows T1–T10 genuinely passed after the validator fix, so Phase 2 can now focus on capability edges rather than re-proving the basics. 

My assessment of each:

**T11: Negation on Director**
Very useful, but this is more of a **spec-gap test** than just a bug test. Right now the prompt excerpt you shared only documents `AND` and `OR` logic nodes plus leaf operators like `==`, `contains`, `between`, comparisons, and `within_distance`; it does not document a NOT form. 
So T11 is excellent, but I would mark it as **expected to fail until negation is formally added to the IR schema and codegen cookbook**.

**T12: Disjunction across same field**
Strong test. This is a clean next step from T7’s AND case and directly checks whether Step 4 builds OR trees and Step 6 preserves them. Since your handoff says OR trees were already seen for actor expansion, this is a very natural generalization. 

**T13: “milk in the title”**
Excellent. This is one of your best tests because it directly targets B2. Your current codegen prompt literally shows string `==` on `Title`/`Director` implemented with `str.contains(...)`, which is the behavior you already flagged as wrong.  
This should stay.

**T14: “the film called the rock”**
Also excellent, and probably the sharpest B2 test in the set because it checks the inverse failure mode: exact title match should not behave like substring match. This one is high value.

**T15: Multi-value field requires contains, not ==**
Very smart. This catches the opposite edge from T14: sometimes exact equality is too strict because the dataset may store comma-joined multi-director values. I like this because it forces you to define the semantics of `Director ==` more carefully at the execution layer.
That said, I would rename the expectation a little. Right now it says “Director contains 'jennifer morrison'.” That may be correct operationally, but conceptually it blurs the difference between IR `==` and execution strategy. I’d phrase it as: “IR probably emits `Director == 'jennifer morrison'`, but execution must still match multi-value person fields safely.”

**T16: Jones Street abbreviation variance**
Very good real-data robustness test. It checks normalizer + extractor + execution together, not just codegen. Since your earlier single-task suite already validated a straightforward `Locations contains "market st"` path, this is a useful harder variant. 
I would keep it.

**T17: Negation + range**
Good, but same caveat as T11: unless negation exists in the IR spec, this is really a future-capability test. The `between` half is already covered by T4/T7, so the novelty here is almost entirely NOT. 
I’d keep it, but classify it as “stretch / expected-red until NOT lands.”

**T18: Null / missing-field predicate**
Very useful. This probes something your current prompt excerpt does not clearly expose as a first-class operator. The prompt talks a lot about guarding against nulls and stringy-null values in execution, but not about expressing `IS NULL` as a predicate. 
So again: great test, but partly a schema question. I would keep it because null handling is core to dirty datasets like this one.

**T19: OR across different fields**
Very strong. This is probably the best “architecture honesty” test in the batch, because it checks whether Step 4 emits a proper cross-field OR tree and whether Step 6 preserves it instead of collapsing back into source-text heuristics. That matters a lot given the issue you just fixed with null-predicate fallback masking architectural problems. 

**T20: word ‘the’ in the title**
Good idea, but I would not put this in the first Phase 2 batch. It is high-cardinality, noisy to inspect, and the expected behavior is harder to verify by eye. It also partly overlaps with T13/T14 on the substring-collision theme.
I would move this to a later “stress / precision audit” batch.

My recommendation:

Keep as the core Phase 2 set:

* T12
* T13
* T14
* T15
* T16
* T18
* T19

Keep, but mark as **expected-red / future-spec**:

* T11
* T17

Defer:

* T20

If you want a tighter Phase 2 that stays mostly single-task and maximally diagnostic, I’d make it:

* OR same field
* exact-vs-contains title
* inverse exact-vs-contains title
* multi-value director cell
* location abbreviation normalization
* null-field retrieval
* cross-field OR

That set is cleaner because it mostly avoids tests that depend on a not-yet-documented NOT operator, while still hammering the most important open bug, B2. 

One more thing I noticed from your sources: your prompt currently documents only `AND` and `OR` logic nodes, and the dependency pattern is explicitly described as later-phase multi-task work.   So if you want the next suite to stay scoped and interpretable, I would label these as:

* **Phase 2A: harder single-task semantics** → T12–T16, T18, T19
* **Phase 2B: new schema features** → T11, T17
* **Phase 2C: stress / ambiguity / high-cardinality** → T20

And yes, I looked at the project sources you pointed to: the April 20 printout confirms the 10/10 run and shows where the old null-predicate fallback had been happening, the bug report explains the validator fix and the still-open B2 issue, and the prompt/changelog confirm what the current IR and codegen are actually designed to support.   

My bottom-line view: **good test batch, but split it into “should pass now” versus “requires new IR/operator support.”** That will make the results much more interpretable. If you want, I’ll turn these into a cleaned-up `PHASE_2_TESTS` list with status labels and a recommended run order.
