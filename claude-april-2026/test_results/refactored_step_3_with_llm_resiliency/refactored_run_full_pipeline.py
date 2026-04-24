# =============================================================================
# CELL: Updated run_full_pipeline (printout adds step3 branch)
#
# DROP THIS IN:
#   Find your CURRENT (post-Step-4-refactor) `def run_full_pipeline(...)` cell
#   in the "## End-to-End Runner" section. REPLACE its body with the version
#   below. The functional behavior is IDENTICAL to what you have now — the
#   existing `if isinstance(ir, dict) and ir.get('error')` check already
#   catches the new step3 structured failure. The only change is one extra
#   `elif stage == 'step3':` branch in the printout, mirroring step4's.
#
# WHY THIS MATTERS:
#   Without this patch, a Step 3 failure still short-circuits correctly
#   (because the envelope shape matches what the orchestrator expects), but
#   the test harness summary prints the generic "Pipeline stopped" line
#   instead of surfacing kind/status_code/retry-after. The Step 3
#   detail still appears in the [Step 3] block above, so this patch is
#   strictly cosmetic — but consistency with step4 is worth it.
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
            elif stage == 'step3':
                # Structured infra/quota/parse/validation failure (NEW)
                err = ir.get('stage_error', {})
                kind = err.get('kind', 'unknown')
                print(f"\n❌ Pipeline stopped (Step 3 {kind}): "
                      f"{ir.get('message')}")
                if kind == 'quota_per_minute' and err.get('retry_after_s'):
                    print(f"   → Try again in about "
                          f"{int(err['retry_after_s']) + 5} seconds.")
                elif kind == 'quota_daily':
                    print(f"   → Daily quota exhausted. Try again tomorrow "
                          f"or upgrade the API plan.")
                elif kind == 'infra':
                    print(f"   → The model service is temporarily unavailable. "
                          f"Try again shortly.")
            elif stage == 'step4':
                # Structured infra/quota/parse/validation failure
                err = ir.get('stage_error', {})
                kind = err.get('kind', 'unknown')
                print(f"\n❌ Pipeline stopped (Step 4 {kind}): "
                      f"{ir.get('message')}")
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
    # (Unchanged. Will be refactored to envelope after Step 3 is proven.)
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
