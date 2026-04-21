I'll search the project knowledge first to understand the context of what you've been testing.Now I have full context. You've passed T1–T10 honestly, and you're brainstorming Phase 2. Let me think through what you've proposed before answering, because some of these queries are genuinely interesting test cases and a few hide subtle issues.

A few honest reactions to your candidates first:

**"Locations for the Matrix"** — single retrieve, location granularity, `Title contains "matrix"`. This is essentially T9 with a different title. Useful only if you want a regression check, not as new coverage. Skip or fold in.

**"Films by Danny Glover"** — this is the *real* T3. T3 currently uses Sean Penn and tests OR-expansion across Actor_1/2/3. Danny Glover does the same job but with a different name — again, regression-flavored. Unless you want to stress fuzzy-matching ("Danny Glover" vs "Daniel Glover"), it's a duplicate of T3.

**"All locations on Folsom Street"** — this one is interesting and *not* a duplicate of T2. T2 is film-granularity ("films shot on Market Street"). "All locations on Folsom" is **location granularity** with the same predicate shape. Good test — it stresses Step 5 (granularity resolver) on an axis you haven't probed. Keep.

**"Films with the most locations per decade"** — you flagged this yourself: **this is not single-task.** It's a group-by-decade + rank-within-group, which is a nested aggregation. That belongs in Phase 2 multi-task / nested. Move it.

**"Films with 'milk' in the title"** — single retrieve, `Title contains "milk"`. Looks innocent but it's actually probing something T9 doesn't: T9 asks for *locations of a specific film*, which routes to location-granularity. "Films with milk in the title" should route to **film-granularity**. Same predicate operator, different granularity decision. That's a real test. Keep.

**"Films with titles that have the least number of vowels"** — and here's the question you should sit with: *is this in scope at all?* It requires the system to invent a derived attribute (`vowel_count(Title)`) that doesn't exist as a column and isn't a documented virtual field like `Actor`. Your Step 4 prompt explicitly forbids schema leakage and your IR has no concept of computed columns. This isn't weird-but-valid; it's **out-of-distribution**. The honest test isn't "can the pipeline answer it" — it's "does the pipeline degrade gracefully when asked something its IR cannot express." Worth including, but as a **negative test** with the expected outcome being a clean clarify or a principled refusal, not a numeric answer.

---

Now to your real question — *what direction should Phase 2 take?* Here's how I'd frame the choice. You have roughly four orthogonal axes you haven't pressure-tested, and I'd pick **one** to go deep on rather than mixing weird queries from all four:

**Axis A — Granularity stress.** Same predicate, different granularity. Folsom locations, films-with-milk, "show me every address in the database where a Spielberg movie was shot." Tests Step 5 in isolation.

**Axis B — Predicate edge cases.** Negation ("films *not* by Hitchcock"), disjunction ("films by Hitchcock or Kubrick"), null/missing ("films with no listed director"), partial matches with collisions ("films with 'man' in the title" → tests the `==` vs `contains` bug B2 you already know about). This is where B2 will surface loudly.

**Axis C — Out-of-distribution / graceful degradation.** Vowel-counting, "the saddest film," "films I would like" — things the IR cannot express. Tests whether Step 2/3 refuse cleanly or whether downstream steps hallucinate.

**Axis D — Fuzzy/typo robustness.** "hichcock," "danny glober," "vertigoo." Tests Step 1's normalizer against the known_values list. You haven't really exercised this since the original T2 fix.

My recommendation: **do Axis B next.** Two reasons. First, it's still single-task, so you stay inside Phase 1 scope and don't conflate predicate complexity with multi-task complexity. Second, it will almost certainly trip B2 (the `==`→`contains` codegen bug you've already documented but deferred), and probably surface a new bug or two around negation that you haven't seen yet — which is exactly the value of a second round.

Save the genuinely weird stuff (Axis C) for a small dedicated "negative tests" suite of 3–4 cases, run separately, where the success criterion is *graceful refusal*, not correctness. Mixing them into a 10-test pass/fail suite muddies the signal.
