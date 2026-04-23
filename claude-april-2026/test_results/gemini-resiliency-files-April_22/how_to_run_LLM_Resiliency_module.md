Yes — let's do it now while it's fresh, and yes, your sequencing is exactly right: **refactor extract_filters tomorrow, test it, prove it works, *then* touch Step 3 and Step 6.** One step at a time. If `extract_filters` reveals a flaw in the wrapper or the envelope contract, I'd rather find it once than three times. That discipline is what's going to make this resume-ready.

Let me pull the current `extract_filters` and `run_preprocessing_pipeline` so the refactor matches reality exactly — including the post-processors that run after Step 4 (`expand_actors_in_result`, `resolve_geocoding`).I have what I need. Let me also look at the exact validation function and the surrounding pipeline code so I match the existing patterns precisely.I have everything. Let me also check the `run_full_pipeline` so I match its short-circuit pattern.I have everything. Now let me build the refactored cells. I'll be deliberate: place the new `extract_filters` next to the old one (commented out, so you can diff), update `run_preprocessing_pipeline` and `run_full_pipeline` to short-circuit, and keep all the logging clear.Now the orchestrator. There's a layering question: `run_preprocessing_pipeline` calls `extract_filters` and then immediately calls `expand_actors_in_result(filter_result)` and `resolve_geocoding(filter_result)` — both expecting an IR-shaped object, not the envelope. The cleanest fix is to short-circuit *before* the post-processors run, and only pass the unwrapped `result` to them.Quick sanity check that both cells parse, then move them to outputs.Done. Two files, both ready to drop in tomorrow.

## Answering your second question first

**Yes — exactly that plan.** Tomorrow we refactor *only* `extract_filters` (Step 4) and the orchestrator. We test it on T1–T20. If it works cleanly, we then do Step 3 (`decompose_query`) and Step 6 (`generate_code`) in a later session, one at a time. The whole point of this sequencing is that if something is wrong with the wrapper, the envelope contract, or the way I've drafted the failure flow, we catch it in *one* place — not three.

## What's in the two files

**`refactored_extract_filters.py`** — drop-in replacement for the existing `extract_filters` cell. The new function is at the top; the old version is preserved at the bottom in a comment block so you can diff after testing. Validation helpers (`validate_filter_result`, `_validate_predicate`, `VALID_FIELDS`, `VALID_OPS`) are untouched — those still live in the cell above and don't need to change.

**`refactored_pipeline.py`** — contains *two* cells:
1. The new `run_preprocessing_pipeline` that unwraps the envelope and short-circuits on `ok=False` *before* the post-processors run.
2. An optional enhanced `run_full_pipeline` that prints structured failures with kind-aware hints ("Try again in ~25s", "Daily quota exhausted", etc.). The functional behavior is identical to your existing version — the existing `if isinstance(ir, dict) and ir.get('error')` check already catches the new failure shape, because I deliberately reused that pattern. The only thing the new printout adds is nicer logging.

## A few things worth knowing before you paste tomorrow

**1. Step 3 and Step 6 still use the old `call_gemini` and old fallback behavior.** That is *intentional* and called out in the comments. Don't touch them yet. You'll see them succeed or fail the same way they always have. Only Step 4 changes.

**2. The post-processors (`expand_actors_in_result`, `resolve_geocoding`) still receive a bare IR.** I unwrap the envelope before passing it to them. They don't need to know the envelope exists.

**3. The `failed_stage` field is your friend.** Every short-circuited failure now carries `failed_stage` (`"step2"` or `"step4"`) and Step 4 failures additionally carry `stage_error` (the full flat envelope). When you grep test printouts tomorrow, that's the field that lets you separate "infra failure" from "semantic failure" cleanly — the thing your handoff doc said you couldn't do.

**4. The optional `run_full_pipeline` enhancement is genuinely optional.** If you'd rather minimize the diff, only swap `extract_filters` and `run_preprocessing_pipeline`. The original `run_full_pipeline` still works correctly with the new failure shape. The enhancement is just nicer printouts.

## Suggested order tomorrow

1. **Read** `refactored_extract_filters.py` end to end. Read it slowly. Ask me about anything that's unclear before pasting.
2. **Sanity scratch cell**: paste this into a new empty cell and run it before swapping anything in:
   ```python
   # Confirm the wrapper from yesterday is still loaded and working
   print(call_gemini_safely.__name__)
   print(DEFAULT_RETRY_POLICY.max_attempts)
   ```
   Should print `call_gemini_safely` and `3`. If not, reload the integration cell first.
3. **Swap `extract_filters`**: replace the cell body. Run it. Should produce no output (just defines a function).
4. **Swap `run_preprocessing_pipeline`**: replace the cell body. Run it. Should produce no output.
5. **(Optional) Swap `run_full_pipeline`**: same drill.
6. **Single-test run first**: run T1 alone before unleashing T1–T20. If it passes (and honestly, T1 is probably going to pass cleanly on a healthy day), run the full suite.

Get some rest. Tomorrow is a clean 30-minute paste-and-test session, not a refactor marathon. The hard part — the design, the wrapper, the test suite, the contract — is already done.