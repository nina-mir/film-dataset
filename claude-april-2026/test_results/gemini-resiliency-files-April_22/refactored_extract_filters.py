# =============================================================================
# CELL: Refactored Step 4 — extract_filters
#
# DROP THIS IN:
#   In the notebook, find the existing `def extract_filters(...)` cell
#   (under "## Step 4: Filter Extractor (LLM) + Post-processors").
#   REPLACE the function body with the version below. The old version is kept
#   commented at the bottom so you can diff in case anything looks off after
#   testing. validate_filter_result, _validate_predicate, VALID_FIELDS, and
#   VALID_OPS are unchanged — leave those alone.
#
# CONTRACT — extract_filters now ALWAYS returns this shape:
#
#   on success:
#     {"ok": True,
#      "result": {"tasks": [...]},   # the filter-extracted task plan
#      "error": None}
#
#   on failure (any kind):
#     {"ok": False,
#      "result": None,
#      "error": {flat dict: stage, kind, status_code, retryable, attempts,
#                retry_after_s, message, model}}
#
# The fallback to null predicates has been REMOVED. Step 4 no longer
# silently produces a semantically-valid IR when something goes wrong.
# Downstream is responsible for short-circuiting on ok=False.
#
# Failure kinds Step 4 can produce:
#   - "infra" / "quota_per_minute" / "quota_daily" / "client_error" / "unknown"
#         from the provider layer (set by call_gemini_safely)
#   - "parse"      JSON didn't decode at all
#   - "validation" JSON decoded but didn't match the expected schema
#
# parse and validation failures are NOT retried at the provider layer.
# They are honest, surfaced failures. If they prove flaky later, we'll
# add a measured single-retry path — but only after we have data showing
# how often they actually happen, not on a hunch.
# =============================================================================

def extract_filters(task_plan, user_query):
    """Step 4: attach a predicate tree to each task in the task plan.

    Returns the {ok, result, error} envelope. Never returns a fallback
    null-predicate IR on failure — that was the silent-wrong-answer bug.
    """
    input_json = json.dumps(task_plan)

    # --- Provider call (with retry/backoff/classification) ---
    call = call_gemini_safely(
        FILTER_EXTRACTOR_PROMPT,
        input_json,
        stage="step4",
        label=f"step4_{user_query[:30]}",
    )

    if not call["ok"]:
        # Infra / quota / client / unknown — error already structured.
        err = call["error"]
        print(f"  [filter_extractor] Provider failure: "
              f"kind={err['kind']} status={err['status_code']} "
              f"attempts={err['attempts']} retryable={err['retryable']}")
        if err.get("retry_after_s"):
            print(f"  [filter_extractor] Server suggested retry after "
                  f"{err['retry_after_s']}s")
        return {"ok": False, "result": None, "error": err}

    raw_text = call["text"]

    # --- Parse ---
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"  [filter_extractor] JSON parse failure: {e}")
        print(f"  [filter_extractor] Raw response (first 500 chars): "
              f"{raw_text[:500]}")
        return {
            "ok": False,
            "result": None,
            "error": {
                "stage": "step4",
                "kind": "parse",
                "status_code": None,
                "retryable": False,
                "attempts": 1,
                "retry_after_s": None,
                "message": f"JSONDecodeError: {e}",
                "model": MODEL_NAME,
            },
        }

    # --- Normalize envelope: bare-array → wrapped (existing behavior) ---
    if isinstance(result, list):
        print("  [filter_extractor] Normalizing bare-array response")
        result = {"tasks": result}

    # --- Validate against expected schema ---
    if not validate_filter_result(result, task_plan):
        print("  [filter_extractor] Validation failed")
        print(f"  [filter_extractor] Rejected payload: "
              f"{json.dumps(result, indent=2)[:500]}")
        return {
            "ok": False,
            "result": None,
            "error": {
                "stage": "step4",
                "kind": "validation",
                "status_code": None,
                "retryable": False,
                "attempts": 1,
                "retry_after_s": None,
                "message": "filter result failed schema validation",
                "model": MODEL_NAME,
            },
        }

    # --- Success ---
    return {"ok": True, "result": result, "error": None}


# -----------------------------------------------------------------------------
# OLD VERSION (kept commented for diffing during testing — delete once T1-T20
# pass cleanly with the new version):
#
# def extract_filters(task_plan, user_query):
#     input_json = json.dumps(task_plan)
#     try:
#         resp = call_gemini(FILTER_EXTRACTOR_PROMPT, input_json,
#                            label=f'step4_{user_query[:30]}')
#         result = json.loads(resp)
#         if isinstance(result, list):
#             print("  [filter_extractor] Normalizing bare-array response")
#             result = {"tasks": result}
#         if validate_filter_result(result, task_plan):
#             return result
#         print("  [filter_extractor] Validation failed, null predicates fallback")
#         print(f"  [filter_extractor] Rejected payload: "
#               f"{json.dumps(result, indent=2)[:500]}")
#     except Exception as e:
#         print(f"  [filter_extractor] Error: {e}, null predicates fallback")
#     fallback = copy.deepcopy(task_plan)
#     for t in fallback['tasks']:
#         t['predicate'] = None
#     return fallback
# -----------------------------------------------------------------------------
