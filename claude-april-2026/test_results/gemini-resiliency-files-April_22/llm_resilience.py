"""
llm_resilience.py
=================
Centralized retry + structured-error layer for Gemini calls.

Design contract — read this before changing anything:

    NEVER let infra failure collapse into a semantically valid IR object.

This module provides three layers, in order of altitude:

    1. Structured exceptions (GeminiInfraError, GeminiQuotaError, ...)
       - Raised by the classifier when a provider call fails.
       - Carry enough metadata (status_code, retryable, retry_after_s,
         quota_kind, attempts, message) for the orchestrator to decide
         what to surface to the user.

    2. call_gemini_once(...)
       - One provider call. Returns response.text on success.
       - On failure, classifies the SDK exception and re-raises a
         structured one. No retries, no backoff, no fallback.

    3. call_gemini_with_retry(...)
       - Wraps call_gemini_once. Owns retry policy:
           * 503 / timeout / connection error -> exp backoff + jitter
           * 429 per-minute -> obey server's retryDelay (+ small buffer)
           * 429 daily quota -> NO retry, raise immediately
           * 4xx other than 429 -> NO retry (auth, bad request, etc.)
       - Returns response.text on eventual success, or raises a
         structured exception with attempts == total tries (NOT just
         retries; a clean first-call failure with no retries is
         attempts=1).

Step functions (extract_filters, decompose_query, generate_code) call
call_gemini_with_retry, then handle their own JSON parse + schema
validation, and return the uniform envelope:

    {"ok": True,  "result": <step output>, "error": None}
    {"ok": False, "result": None, "error": {flat dict}}

The envelope is flat. Fields:
    stage         : "step3" | "step4" | "step6"
    kind          : "infra" | "quota_daily" | "quota_per_minute"
                  | "client_error" | "parse" | "validation" | "unknown"
    status_code   : int | None
    retryable     : bool          # was it retryable AT THE PROVIDER level?
    attempts      : int           # total tries, not just retries
    retry_after_s : float | None  # populated for quota_per_minute
    message       : str
    model         : str           # which model was tried

Keep it flat. If you find yourself wanting nested attempt history,
add a separate `attempt_log` field — don't nest.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ============================================================================
# Structured exceptions
# ============================================================================

class GeminiError(Exception):
    """Base for all classified provider failures.

    Subclasses set `retryable` on the class. `attempts` is filled by the
    retry wrapper at the moment of final raise — call_gemini_once always
    raises with attempts=1.
    """
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after_s: Optional[float] = None,
        attempts: int = 1,
        model: Optional[str] = None,
        raw_details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after_s = retry_after_s
        self.attempts = attempts
        self.model = model
        self.raw_details = raw_details or {}

    def to_envelope_error(self, stage: str, kind: str) -> dict:
        """Render this exception as the flat error dict for the envelope."""
        return {
            "stage": stage,
            "kind": kind,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "retry_after_s": self.retry_after_s,
            "message": self.message,
            "model": self.model,
        }


class GeminiInfraError(GeminiError):
    """5xx responses, timeouts, connection errors. Retryable."""
    retryable = True


class GeminiQuotaPerMinuteError(GeminiError):
    """429 with a per-minute quotaId. Retryable, but obey server's retryDelay."""
    retryable = True


class GeminiQuotaDailyError(GeminiError):
    """429 with a daily quotaId. NOT retryable — wait until tomorrow or upgrade."""
    retryable = False


class GeminiClientError(GeminiError):
    """4xx other than 429 — auth, bad request, model-not-found, etc.
    Not retryable; the request itself is wrong."""
    retryable = False


class GeminiUnknownError(GeminiError):
    """Catch-all for things we couldn't classify. Conservatively non-retryable."""
    retryable = False


# ============================================================================
# Classification
# ============================================================================
# The google-genai SDK raises errors.APIError (with subclasses ClientError /
# ServerError). The exception carries:
#   .code     - HTTP status code (int)
#   .message  - human-readable string
#   .details  - the raw {'error': {...}} dict, which for 429 contains a list
#               of `details` items including a QuotaFailure with quotaId, and
#               a RetryInfo with retryDelay like "21s".
#
# We classify by status_code + (for 429) by quotaId pattern. We do NOT import
# google.genai.errors here — we sniff by attribute so the classifier is
# testable with plain Python exceptions.

_DAILY_QUOTA_HINTS = (
    "perday",          # GenerateRequestsPerDayPerProjectPerModel-FreeTier
    "per_day",
    "perdaily",
    "daily",
)


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Pull status code from a google-genai APIError-like exception, or None."""
    # google.genai.errors.APIError exposes .code as an int
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    # Sometimes it's stringly-typed
    if isinstance(code, str) and code.isdigit():
        return int(code)
    # Fall back to .status_code
    sc = getattr(exc, "status_code", None)
    if isinstance(sc, int):
        return sc
    return None


def _extract_details(exc: Exception) -> dict:
    """Pull the parsed error dict from the SDK exception, or {}."""
    d = getattr(exc, "details", None)
    if isinstance(d, dict):
        return d
    return {}


def _parse_retry_info(details: dict) -> tuple[Optional[float], Optional[str]]:
    """From a 429 payload, extract (retry_delay_seconds, quota_id).

    Gemini's 429 payload looks roughly like:
        {"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED",
                   "details": [
                       {"@type": ".../QuotaFailure", "violations": [
                           {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                            "quotaMetric": "..."}
                       ]},
                       {"@type": ".../RetryInfo", "retryDelay": "21s"}
                   ]}}
    """
    err = details.get("error", details) if isinstance(details, dict) else {}
    items = err.get("details", []) if isinstance(err, dict) else []

    retry_delay_s: Optional[float] = None
    quota_id: Optional[str] = None

    for item in items:
        if not isinstance(item, dict):
            continue
        t = item.get("@type", "")
        if "RetryInfo" in t:
            rd = item.get("retryDelay", "")
            # Format is like "21s" or "0.5s"
            if isinstance(rd, str) and rd.endswith("s"):
                try:
                    retry_delay_s = float(rd[:-1])
                except ValueError:
                    pass
        elif "QuotaFailure" in t:
            for v in item.get("violations", []):
                if isinstance(v, dict) and "quotaId" in v:
                    quota_id = v["quotaId"]
                    break

    return retry_delay_s, quota_id


def _is_daily_quota(quota_id: Optional[str]) -> bool:
    if not quota_id:
        return False
    qid = quota_id.lower().replace(" ", "")
    return any(hint in qid for hint in _DAILY_QUOTA_HINTS)


def classify_exception(exc: Exception, *, model: Optional[str] = None) -> GeminiError:
    """Convert any provider exception into a structured GeminiError.

    Pure function — no side effects, no retries. Always returns an instance
    (never re-raises the input). The retry wrapper is responsible for
    deciding whether to act on the result.
    """
    status = _extract_status_code(exc)
    details = _extract_details(exc)
    msg = str(exc)

    # Network / connection failures don't have a status code
    if status is None:
        # Heuristic: treat connection / timeout strings as infra
        low = msg.lower()
        if any(k in low for k in ("timeout", "timed out", "connection", "reset", "broken pipe")):
            return GeminiInfraError(msg, status_code=None, model=model, raw_details=details)
        return GeminiUnknownError(msg, status_code=None, model=model, raw_details=details)

    # 5xx — retryable infra
    if 500 <= status < 600:
        return GeminiInfraError(msg, status_code=status, model=model, raw_details=details)

    # 429 — split per-minute vs daily
    if status == 429:
        retry_delay, quota_id = _parse_retry_info(details)
        if _is_daily_quota(quota_id):
            return GeminiQuotaDailyError(
                msg, status_code=429, retry_after_s=None,
                model=model, raw_details=details,
            )
        return GeminiQuotaPerMinuteError(
            msg, status_code=429, retry_after_s=retry_delay,
            model=model, raw_details=details,
        )

    # Other 4xx — not retryable
    if 400 <= status < 500:
        return GeminiClientError(msg, status_code=status, model=model, raw_details=details)

    # Anything else
    return GeminiUnknownError(msg, status_code=status, model=model, raw_details=details)


# ============================================================================
# Layer 1: call_gemini_once — single shot with classification
# ============================================================================

def call_gemini_once(
    system_prompt: str,
    user_input: str,
    *,
    provider_call: Callable[..., Any],
    model: str,
    temperature: float = 0.0,
    label: Optional[str] = None,
) -> str:
    """One provider call. Returns response text on success.

    On failure, raises a structured GeminiError. The `provider_call` is
    injected so this is testable with a mock — in production it's
    `client.models.generate_content` (wrapped to take our signature).

    The provider_call must accept (system_prompt, user_input, model,
    temperature, label) and return an object with a `.text` attribute.
    """
    try:
        response = provider_call(
            system_prompt=system_prompt,
            user_input=user_input,
            model=model,
            temperature=temperature,
            label=label,
        )
        return response.text
    except GeminiError:
        # Already classified — let it through. Useful when provider_call
        # is itself a mock that raises structured errors directly.
        raise
    except Exception as e:
        raise classify_exception(e, model=model) from e


# ============================================================================
# Layer 2: call_gemini_with_retry — owns retry/backoff policy
# ============================================================================

@dataclass
class RetryPolicy:
    """All retry tunables in one place. Defaults match the agreed plan."""
    max_attempts: int = 3
    # Exponential backoff for retryable infra (503 / timeout / connection):
    #   wait = base * (factor ** (attempt-1)), then jitter ±jitter_frac
    base_delay_s: float = 5.0
    factor: float = 2.0
    jitter_frac: float = 0.2
    # For 429 per-minute, we obey server's retryDelay + this buffer:
    quota_buffer_s: float = 3.0
    # Cap on any single sleep, just in case server returns a huge value:
    max_sleep_s: float = 90.0


def _backoff_delay(attempt: int, policy: RetryPolicy) -> float:
    """Compute the sleep before attempt N+1, given that attempt N just failed."""
    raw = policy.base_delay_s * (policy.factor ** (attempt - 1))
    jitter = raw * policy.jitter_frac * (2 * random.random() - 1)
    delay = max(0.5, raw + jitter)
    return min(delay, policy.max_sleep_s)


def call_gemini_with_retry(
    system_prompt: str,
    user_input: str,
    *,
    provider_call: Callable[..., Any],
    model: str,
    temperature: float = 0.0,
    label: Optional[str] = None,
    policy: Optional[RetryPolicy] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Call Gemini with retry + structured failure.

    Returns response.text on eventual success.
    Raises a structured GeminiError on final failure, with `.attempts`
    set to the TOTAL number of tries (not just retries; a single-shot
    failure with no retry is attempts=1).

    Retry policy:
        - GeminiInfraError       -> retry with exponential backoff + jitter
        - GeminiQuotaPerMinute   -> sleep retry_after_s + buffer, then retry
        - GeminiQuotaDailyError  -> raise immediately (attempts=1)
        - GeminiClientError      -> raise immediately
        - GeminiUnknownError     -> raise immediately

    `sleep_fn` is injected so tests can run without real sleeping.
    """
    policy = policy or RetryPolicy()
    last_exc: Optional[GeminiError] = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return call_gemini_once(
                system_prompt, user_input,
                provider_call=provider_call,
                model=model,
                temperature=temperature,
                label=label,
            )
        except GeminiError as e:
            last_exc = e
            last_exc.attempts = attempt

            # Fast-fail non-retryable kinds
            if not e.retryable:
                raise

            # Out of attempts
            if attempt >= policy.max_attempts:
                raise

            # Decide sleep duration
            if isinstance(e, GeminiQuotaPerMinuteError):
                delay = (e.retry_after_s or policy.base_delay_s) + policy.quota_buffer_s
                delay = min(delay, policy.max_sleep_s)
            else:
                # Infra (5xx / timeout / connection)
                delay = _backoff_delay(attempt, policy)

            sleep_fn(delay)

    # Should be unreachable — the loop either returns or raises.
    assert last_exc is not None
    raise last_exc
