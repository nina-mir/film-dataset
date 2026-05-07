Labels now match the log cleanly. I went through all ten. Here's what I found, test by test.

**T1 (Hitchcock director) — the failure is a repetition loop.** The generated body is literally just the opening comment `# ── Task t1 ──` followed by ~600 consecutive `─` characters and then the file ends. No code was emitted after the banner. The `try:` on line 26 has no body, which is why the validator reported "expected except or finally block." The LLM got stuck in a token-repetition loop on the box-drawing character and hit max_output_tokens before writing any logic. I strongly suspect the null predicate (fallback from the 503) is the trigger — with the predicate gone, the prompt has fewer anchors, and Gemini drifted into drawing the divider forever. Removing the decorative `─` characters from your skeleton example in the prompt (or replacing with plain `#` dashes) would likely prevent this.

**T2 (market street) — the f-string breaks on a real newline.** Line 62 reads `f" For example: {', '.join(sample_titles[:-1])}, and {sample_titles[-1]}.` and then an actual newline character sits inside the string before the closing quote on line 63. Python single-quoted f-strings can't contain literal newlines. The mechanism is the JSON round-trip: the model emitted `\n` as an escape inside its JSON response, `json.loads` correctly decoded that to a real newline, and now the code text has a raw newline inside a string literal. The predicate logic itself is fine — `str.contains('market street', case=False)` is the right translation of `op: contains`. Fix is in the prompt: forbid embedded newlines in string literals, or instruct the model to use explicit `\\n` / triple-quoted strings for multi-line output.

**T3 (Sean Penn) — passes but silently swaps the operator.** IR says `op: "=="` with value `"sean penn"`. Generated code uses `str.contains('sean penn', case=False)` across the three actor columns. The OR expansion is correct, the row result is correct (5 films), but the predicate was translated as substring-match, not equality. Works here because no "Sean Penny" exists in the data. This is a category-level bug I'll come back to below.

**T4 (count in the 80s) — clean.** `pd.to_numeric(gdf_copy['Year'], errors='coerce').between(1980, 1989, inclusive='both')` is the right translation. Dedupes to film level before counting, which matches "how many films." The 39 result looks plausible; hand-verify to be sure.

**T5 (top 5 directors) — passes, but the IR is wrong and the codegen is covering for it.** The Task Decomposer labeled this `kind: "retrieve"`, not `kind: "rank"`. The codegen LLM read the `source` text "top 5 directors with the most films," ignored the IR kind, and wrote a rank operation anyway. The output is correct but the IR contract is violated — you have a Step 3 bug hiding behind a Step 6 win. Also, line 31 `t1_matched_rows = gdf_copy` is an aliasing, not a copy — no harm here because nothing mutates it, but the hard invariants mention immutability.

**T6 (films from 1985) — clean.** `== 1985` on coerced numeric is the right translation of `op: "=="` on Year.

**T7 (Hitchcock + 1950s AND) — passes with the same operator swap as T3.** Director clause is `str.contains('alfred hitchcock', case=False)` instead of equality. Year clause is correct `.between(1950, 1959)`. AND combination is structurally right. One stylistic note: T7 layers `.notna() & .strip().ne('') & ~.isin(['none','nan','null']) & .contains(...)` while T3 uses a compact `.astype(str).apply(...)`. The prompt hasn't picked a canonical null-handling idiom, so each generation improvises.

**T8 (coit tower, 1 mile) — the "silent success" we discussed.** Line 107: `task_results['t1']['predicate']['value']['reference_place']`. The `task_results['t1']` dict only has keys `matched_rows`, `text_view`, `result` — there is no `predicate` key, because the hard invariant forbids stashing the IR in runtime state. That access raises `KeyError: 'predicate'`, the except block catches it, and the pipeline marks the run successful because the function returned without raising. The whole spatial body above that line is actually well-written — reprojects to EPSG:32610 (UTM 10N, correct for SF), converts 1 mile to meters, applies the mask back against the original-CRS frame. If the model had written `"within 1 mile of coit tower"` as a literal string (which it already knew at prompt time), this would have passed for real. The fix is a sentence in the prompt: *values from the predicate that you want to echo in the summary must be inlined as literals, not read from task_results at runtime.*

**T9 (Vertigo locations) — passes, same operator swap.** IR: `op: "=="`, `value: "vertigo"`. Code: `str.contains('vertigo', case=False)`. Returns 16 rows which is correct for the dataset, but would also pick up a hypothetical "Vertigo 2." Granularity is right: no dedup because `response_granularity` is `"location"`.

**T10 — no code generated.** 429 rate limit, not a codegen issue.

---

**The three patterns worth fixing at the prompt/pipeline level, ranked by severity:**

The first pattern is the **silent `==` → `contains` swap** on string fields (T3, T7, T9 — three of the seven passing tests). This is systematic. The LLM is compensating for Step 4 lowercasing predicate values — it correctly infers that the column has "Sean Penn" while the IR says "sean penn," so it reaches for case-insensitive substring. The fix is upstream: either Step 4 preserves original case, or the codegen prompt adds a rule that `==` on string fields means `series.str.lower() == value.lower()` — exact, not substring. This is the bug most likely to cause a subtle wrong answer on a real query ("sean penn" matching "Sean Penny").

The second is **runtime IR access** (T8), which is already forbidden by the hard invariants but the model did it anyway. Needs a concrete counter-example in the prompt showing "to build a summary string, inline the literal value directly, like `f\"within 1 mile of coit tower\"` — do not read it from task_results."

The third is the **success-detection gap in `execute_code`**. Even if codegen is fixed, errors caught by the generated try/except still return a structured payload; the pipeline should treat `result['metadata'].get('error')` or `result['data'] is None` as failure signals, not just raised exceptions. T8 was your canary for this.

T1's repetition loop and T2's f-string newline are both real bugs but narrower — remove the `─` from the skeleton, forbid literal newlines inside string literals, and both should disappear.

Want me to draft the prompt deltas for the three systemic issues?