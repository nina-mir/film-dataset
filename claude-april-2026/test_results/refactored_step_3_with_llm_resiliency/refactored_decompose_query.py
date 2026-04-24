# =============================================================================
# CELL: Refactored Step 3 — decompose_query (envelope-aware)
#
# DROP THIS IN:
#   In the notebook, find the existing `def decompose_query(...)` cell
#   (under "## Step 3: Task Decomposer (hybrid: short-circuit + LLM)").
#   REPLACE the function body with the version below. The old version is
#   kept commented at the bottom so you can diff in case anything looks off
#   after testing. MULTI_INTENT_PATTERNS, TASK_DECOMPOSER_PROMPT,
#   VALID_KINDS, SCHEMA_LEAK, and validate_task_plan are unchanged — leave
#   those alone. make_fallback is no longer called from the LLM path; it's
#   commented out below for now (we may delete outright after a clean run).
#
# CONTRACT — decompose_query now ALWAYS returns this shape:
#
#   on success (deterministic short-circuit OR validated LLM result):
#     {"ok": True,
#      "result": {"tasks": [...]},     # the task plan
#      "error": None}
#
#   on failure (any kind):
#     {"ok": False,
#      "result": None,
#      "error": {flat dict: stage, kind, status_code, retryable, attempts,
#                retry_after_s, message, model}}
#
# The silent fallback to a single-task retrieve has been REMOVED from the
# LLM path. Step 3 no longer pretends success when the LLM call fails or
# the response is malformed. This closes the T18/T19 silent-wrong-answer
# class (Run 2 evidence: Step 3 503 → silent single-task fallback → lost
# the count intent → pipeline reported ✓ SUCCESS while only answering half
# the user's question).
#
# Failure kinds Step 3 can produce:
#   - "infra" / "quota_per_minute" / "quota_daily" / "client_error" / "unknown"
#         from the provider layer (set by call_gemini_safely)
#   - "parse"      JSON didn't decode at all
#   - "validation" JSON decoded but didn't match the expected schema
#
# parse and validation failures are NOT retried at the provider layer.
# They're honest, surfaced failures — same baseline policy as Step 4.
#
# NOTE on the deterministic short-circuit:
#   When MULTI_INTENT_PATTERNS doesn't match, no LLM is called and we
#   return ok=True without going through the provider. The orchestrator
#   handles both success paths (short-circuit and LLM) the same way:
#   unwrap envelope["result"] and continue.
# =============================================================================

def decompose_query(query):
    """Step 3: break the query into atomic semantic tasks.

    Returns the {ok, result, error} envelope. Never returns a fallback
    single-task retrieve on failure — that was the T18/T19 silent-wrong-
    answer bug.
    """
    # --- Deterministic short-circuit: no multi-intent signals → 1 retrieve ---
    # No LLM call, no failure modes. Always succeeds.
    if not any(p.search(query) for p in MULTI_INTENT_PATTERNS):
        return {
            "ok": True,
            "result": {
                "tasks": [
                    {"id": "t1", "kind": "retrieve",
                     "source": query, "dependsOn": []}
                ]
            },
            "error": None,
        }

    # --- Diagnostic: which pattern triggered the LLM path ---
    for p in MULTI_INTENT_PATTERNS:
        if p.search(query):
            print(f"  [decomposer] matched pattern: {p.pattern}")
            break

    # --- Provider call (with retry/backoff/classification) ---
    call = call_gemini_safely(
        TASK_DECOMPOSER_PROMPT,
        query,
        stage="step3",
        label=f"step3_{query}",
    )

    if not call["ok"]:
        # Infra / quota / client / unknown — error already structured.
        err = call["error"]
        print(f"  [decomposer] Provider failure: "
              f"kind={err['kind']} status={err['status_code']} "
              f"attempts={err['attempts']} retryable={err['retryable']}")
        if err.get("retry_after_s"):
            print(f"  [decomposer] Server suggested retry after "
                  f"{err['retry_after_s']}s")
        return {"ok": False, "result": None, "error": err}

    raw_text = call["text"]

    # --- Parse ---
    try:
        plan = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"  [decomposer] JSON parse failure: {e}")
        print(f"  [decomposer] Raw response (first 500 chars): "
              f"{raw_text[:500]}")
        return {
            "ok": False,
            "result": None,
            "error": {
                "stage": "step3",
                "kind": "parse",
                "status_code": None,
                "retryable": False,
                "attempts": 1,
                "retry_after_s": None,
                "message": f"JSONDecodeError: {e}",
                "model": MODEL_NAME,
            },
        }

    # --- Validate against expected schema ---
    if not validate_task_plan(plan, query):
        print("  [decomposer] Validation failed")
        print(f"  [decomposer] Rejected payload: "
              f"{json.dumps(plan, indent=2)[:500]}")
        return {
            "ok": False,
            "result": None,
            "error": {
                "stage": "step3",
                "kind": "validation",
                "status_code": None,
                "retryable": False,
                "attempts": 1,
                "retry_after_s": None,
                "message": "task plan failed schema validation",
                "model": MODEL_NAME,
            },
        }

    # --- Success ---
    return {"ok": True, "result": plan, "error": None}


# -----------------------------------------------------------------------------
# OLD VERSION (kept commented for diffing during testing — delete once T1-T20
# pass cleanly with the new version):
#
# def decompose_query(query):
#     if not any(p.search(query) for p in MULTI_INTENT_PATTERNS):
#         return make_fallback(query)
#
#     for p in MULTI_INTENT_PATTERNS:
#       if p.search(query):
#           print(f"  [decomposer] matched pattern: {p.pattern}")
#           break
#
#     try:
#         resp = call_gemini(TASK_DECOMPOSER_PROMPT, query, label=f'step3_{query}')
#         plan = json.loads(resp)
#         if validate_task_plan(plan, query): return plan
#         print("  [decomposer] Validation failed, fallback")
#         return make_fallback(query)
#     except Exception as e:
#         print(f"  [decomposer] Error: {e}, fallback")
#         return make_fallback(query)
#
# # make_fallback is no longer called from the LLM path. Commented out for
# # now in case we need to roll back during testing — delete after T1-T20
# # pass cleanly with the new envelope-aware version.
# # def make_fallback(query):
# #     return {"tasks": [{"id":"t1","kind":"retrieve","source":query,"dependsOn":[]}]}
# -----------------------------------------------------------------------------
