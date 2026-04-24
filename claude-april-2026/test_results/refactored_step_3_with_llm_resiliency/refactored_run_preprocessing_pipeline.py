# =============================================================================
# CELL: Refactored run_preprocessing_pipeline (Steps 1-5 orchestrator)
#
# DROP THIS IN:
#   Find your CURRENT (post-Step-4-refactor) `def run_preprocessing_pipeline(...)`
#   cell — the one with the comment "NOTE: Step 3 still uses the legacy fallback
#   path." REPLACE the function body with the version below. The other steps
#   (normalize_query, safety_check, expand_actors_in_result, resolve_geocoding,
#   resolve_presentation, extract_filters) are unchanged — leave those alone.
#
# WHAT CHANGES (from the post-Step-4-refactor version):
#   - Step 3 now returns the {ok, result, error} envelope. We unwrap it.
#   - On ok=False, we short-circuit immediately with a structured failure
#     payload, same shape as the Step 4 failure payload (just with
#     failed_stage='step3'). Post-processors, Step 4, Step 5, codegen, and
#     execution are all skipped.
#   - The "NOTE: Step 3 still uses the legacy fallback path" comment is gone.
#
# WHAT DOES NOT CHANGE:
#   - Step 4 envelope handling (already done previously).
#   - Steps 1, 2, 5 (rule-based, unchanged).
#   - Post-processors (expand_actors_in_result, resolve_geocoding).
#   - The success-path return value: still a bare IR.
#   - The failure-payload shape: still {error: True, message: str,
#     failed_stage: str, stage_error: dict}, recognized by run_full_pipeline's
#     existing `if isinstance(ir, dict) and ir.get('error')` check.
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

    # --- Step 3: Task Decomposer (NEW: envelope-aware) ---
    if verbose:
        print(f"\n[Step 3] Decomposing...")

    decompose_envelope = decompose_query(cleaned)

    if not decompose_envelope["ok"]:
        # Honest failure — short-circuit. Do NOT proceed to Step 4, Step 5,
        # codegen, or execution. This is the fix for the T18/T19 silent-
        # wrong-answer class: a 503 in Step 3 used to silently fall back
        # to a single-task retrieve, dropping the count intent. Now it
        # surfaces.
        err = decompose_envelope["error"]
        msg = (f"Step 3 failed: {err['kind']} "
               f"(status={err['status_code']}, attempts={err['attempts']})")
        if verbose:
            print(f"\n❌ {msg}")
            if err.get("retry_after_s"):
                print(f"   Server suggested retry after "
                      f"~{err['retry_after_s']}s")
        return {
            'error': True,
            'message': msg,
            'failed_stage': 'step3',
            'stage_error': err,   # full flat envelope, for the test harness
        }

    task_plan = decompose_envelope["result"]
    if verbose:
        print(f"  Tasks: {json.dumps(task_plan, indent=2)}")
    time.sleep(LLM_DELAY)

    # --- Step 4: Filter Extractor (envelope-aware, unchanged from prior refactor) ---
    if verbose:
        print(f"\n[Step 4] Extracting filters...")

    filter_envelope = extract_filters(task_plan, user_query)

    if not filter_envelope["ok"]:
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
            'stage_error': err,
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
