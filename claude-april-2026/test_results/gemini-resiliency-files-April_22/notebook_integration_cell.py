# =============================================================================
# CELL: LLM resilience layer — paste this into your notebook AFTER the existing
#       call_gemini definition and BEFORE the step functions (extract_filters,
#       decompose_query, generate_code).
#
# This cell does NOT modify call_gemini. It defines:
#   - gemini_provider_call(...)     : adapter that matches the wrapper's signature
#   - call_gemini_safely(...)       : the public entry point step functions will use
#
# After you run this cell, the next step (in a follow-up edit) is to replace
# `call_gemini(...)` calls inside extract_filters / decompose_query /
# generate_code with `call_gemini_safely(...)` and switch them to return the
# {ok, result, error} envelope.
# =============================================================================

# Make sure llm_resilience.py is importable. In Colab, drop the file into
# /content (or your Drive folder) and add it to sys.path:
#
#   import sys
#   sys.path.insert(0, '/content')
#
# Then:
from llm_resilience import (
    GeminiError,
    RetryPolicy,
    call_gemini_with_retry,
)


# -----------------------------------------------------------------------------
# Adapter: bridge your existing call_gemini to the wrapper's expected signature.
# The wrapper expects provider_call(system_prompt, user_input, model,
# temperature, label) -> object with .text. Your call_gemini already returns
# response.text directly, so we wrap it to look object-shaped.
# -----------------------------------------------------------------------------

class _TextWrapper:
    """Minimal stand-in for an SDK response object — only .text is read."""
    __slots__ = ("text",)
    def __init__(self, text: str):
        self.text = text


def gemini_provider_call(*, system_prompt, user_input, model, temperature, label):
    """Adapter: route through the existing call_gemini in this notebook.

    NOTE: existing call_gemini reads MODEL_NAME from globals. We pass `model`
    here for envelope/logging metadata, but the actual model used is whatever
    MODEL_NAME is set to. If you later parameterize call_gemini to take a
    model argument, plumb it through here.
    """
    text = call_gemini(
        system_prompt=system_prompt,
        user_input=user_input,
        temperature=temperature,
        label=label,
    )
    return _TextWrapper(text)


# -----------------------------------------------------------------------------
# Default policy. Tunable in one place.
# -----------------------------------------------------------------------------

DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts=3,    # total tries, NOT just retries
    base_delay_s=5.0,  # 503/timeout: ~5s, ~10s, ~20s with jitter
    factor=2.0,
    jitter_frac=0.2,
    quota_buffer_s=3.0,  # added to server's retryDelay on per-minute 429
    max_sleep_s=90.0,    # safety cap on any single sleep
)


# -----------------------------------------------------------------------------
# Public entry point for step functions. One line replaces the bare
# call_gemini(...) call inside extract_filters / decompose_query / generate_code.
#
# Returns the envelope directly. Step functions then layer parse + validation
# on top of a successful infra call.
# -----------------------------------------------------------------------------

def call_gemini_safely(
    system_prompt: str,
    user_input: str,
    *,
    stage: str,           # "step3" | "step4" | "step6"
    label: str | None = None,
    temperature: float = 0.0,
    policy: RetryPolicy | None = None,
) -> dict:
    """Call Gemini with retry + structured failure. Returns the envelope.

    Success:
        {"ok": True, "text": "<response text>", "error": None,
         "stage": stage, "attempts": <int>}

    Failure (infra/quota/client):
        {"ok": False, "text": None,
         "error": {flat dict with stage, kind, status_code, retryable,
                   attempts, retry_after_s, message, model}}

    The step function is responsible for parse + validation on the text and
    for converting parse/validation failures into envelope errors with the
    appropriate `kind`. This function only handles the provider layer.
    """
    try:
        text = call_gemini_with_retry(
            system_prompt, user_input,
            provider_call=gemini_provider_call,
            model=MODEL_NAME,
            temperature=temperature,
            label=label,
            policy=policy or DEFAULT_RETRY_POLICY,
        )
        return {
            "ok": True,
            "text": text,
            "error": None,
            "stage": stage,
            "attempts": 1,  # success path; if you want exact retry-success
                            # counts, plumb that out of the wrapper later
        }
    except GeminiError as e:
        kind = {
            "GeminiInfraError": "infra",
            "GeminiQuotaPerMinuteError": "quota_per_minute",
            "GeminiQuotaDailyError": "quota_daily",
            "GeminiClientError": "client_error",
            "GeminiUnknownError": "unknown",
        }.get(type(e).__name__, "unknown")
        return {
            "ok": False,
            "text": None,
            "error": e.to_envelope_error(stage=stage, kind=kind),
        }
