# =============================================================================
# CELL: Refactored run_preprocessing_pipeline (Steps 1-5 orchestrator)
#
# DROP THIS IN:
#   Find the existing `def run_preprocessing_pipeline(...)` cell in the
#   "## Pipeline Runner (Steps 1–5)" section. REPLACE the function body with
#   the version below. The other steps (decompose_query, expand_actors_in_result,
#   resolve_geocoding, resolve_presentation, safety_check, normalize_query)
#   are unchanged — leave those alone.
#
# WHAT CHANGES:
#   - Step 4 now returns the {ok, result, error} envelope instead of a bare
#     IR. We unwrap it.
#   - On ok=False, we short-circuit immediately with a structured failure
#     payload that includes the full error envelope. We do NOT proceed to
#     post-processors, Step 5, code generation, or execution.
#   - The failure payload uses the same {error: True, ...} shape that the
#     safety gate already uses, so run_full_pipeline's existing
#     `if isinstance(ir, dict) and ir.get('error')` check catches it
#     automatically. No change needed in run_full_pipeline (but I include
#     a small enhancement below for nicer printing).
#
# WHAT DOES NOT CHANGE:
#   - Steps 1, 2, 3, 5 are untouched. (Step 3 still uses the old call_gemini
#     and old fallback behavior — we'll refactor it AFTER Step 4 is proven.)
#   - Post-processors (expand_actors_in_result, resolve_geocoding) are
#     untouched. They still receive a bare IR ({"tasks": [...]}), only we
#     give them the unwrapped result.
#   - The success-path return value is unchanged: a bare IR.
# =============================================================================

def run_preprocessing_pipeline(user_query, known_values, verbose=True):
    """Run Steps 1-5 and return the complete IR.

    Returns either:
      - the IR dict (success), OR
      - {'error': True, 'message': str, 'failed_stage': str,
         'stage_error': <flat error envelope>} on a structured failure.

    The latter shape is recognized by run_full_pipeline's existing
    error-check, so the orchestrator short-circuits cleanly.
    """
    if verbose:
        print(f"\n{'='*60}\nQuery: {user_query}\n{'='*60}")

    # --- Step 1: Normalize ---
    norm = normalize_query(user_query, known_values)
    cleaned = norm['normalized']
    if verbose:
        print(f"\n[Step 1] Normalized: {cleaned}")
        if norm['corrections']:
            print(f"  Corrections: {norm['corrections']}")

    # --- Step 2: Safety Gate ---
    gate = safety_check(cleaned)
    if not gate['safe']:
        if verbose:
            print(f"\n[Step 2] BLOCKED: {gate['blocked_by']}")
        return {
            'error': True,
            'message': gate['message'],
            'blocked_by': gate['blocked_by'],
            'failed_stage': 'step2',
        }
    if verbose:
        print(f"[Step 2] Safe ✓")

    # --- Step 3: Task Decomposer ---
    # NOTE: Step 3 still uses the legacy fallback path. It will be
    # refactored to return the envelope AFTER Step 4 has been validated
    # end-to-end on T1-T20.
    if verbose:
        print(f"\n[Step 3] Decomposing...")
    task_plan = decompose_query(cleaned)
    if verbose:
        print(f"  Tasks: {json.dumps(task_plan, indent=2)}")
    time.sleep(LLM_DELAY)

    # --- Step 4: Filter Extractor (NEW: envelope-aware) ---
    if verbose:
        print(f"\n[Step 4] Extracting filters...")

    filter_envelope = extract_filters(task_plan, user_query)

    if not filter_envelope["ok"]:
        # Honest failure — short-circuit. Do NOT run post-processors,
        # do NOT proceed to Step 5 or codegen. The whole point of this
        # refactor is that infra failure no longer pretends to succeed.
        err = filter_envelope["error"]
        msg = (f"Step 4 failed: {err['kind']} "
               f"(status={err['status_code']}, attempts={err['attempts']})")
        if verbose:
            print(f"\n❌ {msg}")
            if err.get("retry_after_s"):
                print(f"   Server suggested retry after "
                      f"~{err['retry_after_s']}s")
        return {
            'error': True,
            'message': msg,
            'failed_stage': 'step4',
            'stage_error': err,   # full flat envelope, for the test harness
        }

    # Unwrap on success and run post-processors as before.
    filter_result = filter_envelope["result"]
    filter_result = expand_actors_in_result(filter_result)
    filter_result = resolve_geocoding(filter_result)
    if verbose:
        print(f"  Filters: {json.dumps(filter_result, indent=2)}")
    time.sleep(LLM_DELAY)

    # --- Step 5: Presentation Resolver ---
    ir = resolve_presentation(filter_result)
    if verbose:
        print(f"\n[Step 5] Presentation resolved:")
        for t in ir['tasks']:
            print(f"  {t['id']}: granularity={t.get('response_granularity')}, "
                  f"offer_map={t.get('offer_map')}")
        print(f"  Top-level offer_map: {ir.get('offer_map')}")

    return ir


# =============================================================================
# CELL (optional but recommended): Enhanced run_full_pipeline printout
#
# DROP THIS IN:
#   Find `def run_full_pipeline(...)` in the "## End-to-End Runner" section.
#   REPLACE its body with the version below. The functional behavior is
#   IDENTICAL to what you have today — the existing
#   `if isinstance(ir, dict) and ir.get('error')` check already catches the
#   new structured failure. The only changes are:
#     - Surface failed_stage and stage_error details in the printout
#     - Make infra-failure visually distinct from semantic failure
#
# If you'd rather not change run_full_pipeline yet, you don't have to.
# The original version still works; you just won't see the kind/status_code
# in the test summary — you'll see them in the [Step 4] printout from the
# preprocessing pipeline, which is enough to confirm correctness.
# =============================================================================

def run_full_pipeline(user_query, gdf, known_values, verbose=True):
    """Complete pipeline: preprocessing (Steps 1-5) → code generation → execution.
    Returns all intermediate results for inspection.
    """
    pipeline_result = {
        'query': user_query,
        'ir': None,
        'codegen': None,
        'execution': None,
        'success': False,
    }

    # --- Steps 1-5: Preprocessing ---
    ir = run_preprocessing_pipeline(user_query, known_values, verbose=verbose)

    # --- Check for blocked queries (safety gate) and structured stage failures ---
    if isinstance(ir, dict) and ir.get('error'):
        pipeline_result['ir'] = ir
        if verbose:
            stage = ir.get('failed_stage', 'unknown')
            if stage == 'step2':
                print(f"\n❌ Pipeline stopped (safety gate): {ir.get('message')}")
            elif stage == 'step4':
                # Structured infra/quota/parse/validation failure
                err = ir.get('stage_error', {})
                kind = err.get('kind', 'unknown')
                print(f"\n❌ Pipeline stopped (Step 4 {kind}): "
                      f"{ir.get('message')}")
                # Friendly user-facing hint based on kind
                if kind == 'quota_per_minute' and err.get('retry_after_s'):
                    print(f"   → Try again in about "
                          f"{int(err['retry_after_s']) + 5} seconds.")
                elif kind == 'quota_daily':
                    print(f"   → Daily quota exhausted. Try again tomorrow "
                          f"or upgrade the API plan.")
                elif kind == 'infra':
                    print(f"   → The model service is temporarily unavailable. "
                          f"Try again shortly.")
            else:
                print(f"\n❌ Pipeline stopped: {ir.get('message')}")
        return pipeline_result

    # --- Check for clarify-only tasks ---
    if all(t['kind'] == 'clarify' for t in ir.get('tasks', [])):
        pipeline_result['ir'] = ir
        if verbose:
            print(f"\n⚠️ Clarification needed — skipping code generation")
        return pipeline_result

    pipeline_result['ir'] = ir
    time.sleep(LLM_DELAY)

    # --- Step 6: Code Generation ---
    # (Unchanged. Will be refactored to envelope after Step 4 is proven.)
    codegen = generate_code(ir, user_query, verbose=verbose)
    pipeline_result['codegen'] = codegen

    if codegen.get('error'):
        if verbose:
            print(f"\n❌ Code generation failed: {codegen.get('message')}")
        return pipeline_result

    # --- Execution ---
    execution = execute_code(codegen['code'], gdf, verbose=verbose)
    pipeline_result['execution'] = execution
    pipeline_result['success'] = execution.get('success', False)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Pipeline {'✓ SUCCESS' if pipeline_result['success'] else '✗ FAILED'}")
        print(f"{'='*60}")

    return pipeline_result
