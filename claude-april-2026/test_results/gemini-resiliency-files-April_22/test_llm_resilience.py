"""
test_llm_resilience.py
======================
Unit tests for the retry wrapper. Run before refactoring any step.

Covers:
    - Classifier handles 503, 429-per-minute, 429-daily, 4xx, timeout,
      connection errors, and unknowns correctly.
    - call_gemini_once raises structured exceptions, never bare ones.
    - call_gemini_with_retry:
        * succeeds on clean first call (attempts=1, no sleeps)
        * succeeds after 503 retry (attempts=2, one sleep recorded)
        * obeys server retryDelay on 429 per-minute (sleep ~= delay + buffer)
        * does NOT retry on 429 daily quota (attempts=1, no sleeps)
        * does NOT retry on 4xx (attempts=1)
        * exhausts retries on persistent 503 (attempts=max, raises)
        * sleep_fn is injected, never calls real time.sleep

Run with:  python -m pytest test_llm_resilience.py -v
   or:    python test_llm_resilience.py     (uses unittest)
"""

import unittest
from typing import Any, Callable
from unittest.mock import MagicMock

from llm_resilience import (
    GeminiClientError,
    GeminiError,
    GeminiInfraError,
    GeminiQuotaDailyError,
    GeminiQuotaPerMinuteError,
    GeminiUnknownError,
    RetryPolicy,
    call_gemini_once,
    call_gemini_with_retry,
    classify_exception,
)


# ----------------------------------------------------------------------------
# Fake SDK exceptions — mimic google.genai.errors.APIError shape
# ----------------------------------------------------------------------------

class FakeAPIError(Exception):
    """Mimics google.genai.errors.APIError: has .code, .message, .details."""
    def __init__(self, code: int, message: str, details: dict | None = None):
        super().__init__(f"{code} {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def _quota_payload(quota_id: str, retry_delay: str | None = None) -> dict:
    """Build a realistic 429 details dict."""
    inner_details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaId": quota_id, "quotaMetric": "x"}],
        }
    ]
    if retry_delay is not None:
        inner_details.append({
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": retry_delay,
        })
    return {
        "error": {
            "code": 429,
            "message": "Resource exhausted",
            "status": "RESOURCE_EXHAUSTED",
            "details": inner_details,
        }
    }


# ----------------------------------------------------------------------------
# Mock provider — composable scripted responses
# ----------------------------------------------------------------------------

class MockProvider:
    """Scripted provider. Each call pops the next item from the script.

    A script item is either:
        - a string  -> return an object with .text == that string
        - an Exception instance -> raise it
    """
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> Any:
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("MockProvider script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        # Wrap the string in something with a .text attribute
        m = MagicMock()
        m.text = item
        return m


class SleepRecorder:
    """Drop-in replacement for time.sleep that records durations."""
    def __init__(self):
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# ============================================================================
# Classifier tests
# ============================================================================

class TestClassifier(unittest.TestCase):

    def test_503_is_infra_retryable(self):
        e = classify_exception(FakeAPIError(503, "model overloaded"))
        self.assertIsInstance(e, GeminiInfraError)
        self.assertTrue(e.retryable)
        self.assertEqual(e.status_code, 503)

    def test_500_is_infra_retryable(self):
        e = classify_exception(FakeAPIError(500, "internal error"))
        self.assertIsInstance(e, GeminiInfraError)
        self.assertTrue(e.retryable)

    def test_429_per_minute_extracts_retry_delay(self):
        payload = _quota_payload(
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
            retry_delay="21s",
        )
        e = classify_exception(FakeAPIError(429, "Resource exhausted", payload))
        self.assertIsInstance(e, GeminiQuotaPerMinuteError)
        self.assertTrue(e.retryable)
        self.assertEqual(e.retry_after_s, 21.0)

    def test_429_daily_quota_not_retryable(self):
        payload = _quota_payload(
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            retry_delay="60s",  # even with retryDelay, daily means daily
        )
        e = classify_exception(FakeAPIError(429, "Daily quota exceeded", payload))
        self.assertIsInstance(e, GeminiQuotaDailyError)
        self.assertFalse(e.retryable)

    def test_429_with_no_quota_details_defaults_to_per_minute(self):
        # If we can't tell, treat as per-minute (retry-friendly is the safer
        # default than dropping a request that might have succeeded).
        e = classify_exception(FakeAPIError(429, "rate limited", {"error": {"code": 429}}))
        self.assertIsInstance(e, GeminiQuotaPerMinuteError)
        self.assertIsNone(e.retry_after_s)

    def test_400_bad_request_not_retryable(self):
        e = classify_exception(FakeAPIError(400, "invalid argument"))
        self.assertIsInstance(e, GeminiClientError)
        self.assertFalse(e.retryable)

    def test_401_unauthenticated_not_retryable(self):
        e = classify_exception(FakeAPIError(401, "API keys are not supported"))
        self.assertIsInstance(e, GeminiClientError)
        self.assertFalse(e.retryable)

    def test_404_model_not_found_not_retryable(self):
        e = classify_exception(FakeAPIError(404, "model not found"))
        self.assertIsInstance(e, GeminiClientError)

    def test_timeout_string_classified_as_infra(self):
        e = classify_exception(TimeoutError("connection timed out"))
        self.assertIsInstance(e, GeminiInfraError)
        self.assertTrue(e.retryable)

    def test_connection_reset_classified_as_infra(self):
        e = classify_exception(ConnectionError("connection reset by peer"))
        self.assertIsInstance(e, GeminiInfraError)

    def test_random_exception_classified_as_unknown(self):
        e = classify_exception(ValueError("something weird"))
        self.assertIsInstance(e, GeminiUnknownError)
        self.assertFalse(e.retryable)

    def test_model_propagates_through_classification(self):
        e = classify_exception(FakeAPIError(503, "x"), model="gemini-2.5-flash")
        self.assertEqual(e.model, "gemini-2.5-flash")

    def test_envelope_error_is_flat(self):
        e = classify_exception(
            FakeAPIError(503, "down"), model="gemini-2.5-flash"
        )
        e.attempts = 3
        env = e.to_envelope_error(stage="step4", kind="infra")
        # Flat dict, no nesting
        for v in env.values():
            self.assertNotIsInstance(v, dict)
        self.assertEqual(env["stage"], "step4")
        self.assertEqual(env["status_code"], 503)
        self.assertEqual(env["attempts"], 3)
        self.assertTrue(env["retryable"])


# ============================================================================
# call_gemini_once tests
# ============================================================================

class TestCallOnce(unittest.TestCase):

    def test_returns_text_on_success(self):
        provider = MockProvider(["hello world"])
        text = call_gemini_once(
            "sys", "user",
            provider_call=provider, model="m", label="t",
        )
        self.assertEqual(text, "hello world")
        self.assertEqual(len(provider.calls), 1)

    def test_raises_structured_on_503(self):
        provider = MockProvider([FakeAPIError(503, "down")])
        with self.assertRaises(GeminiInfraError) as ctx:
            call_gemini_once("s", "u", provider_call=provider, model="m")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.attempts, 1)  # always 1 from once

    def test_passes_through_already_classified_error(self):
        # If the provider already raises a GeminiError, don't re-wrap it.
        original = GeminiInfraError("already", status_code=503)
        provider = MockProvider([original])
        with self.assertRaises(GeminiInfraError) as ctx:
            call_gemini_once("s", "u", provider_call=provider, model="m")
        self.assertIs(ctx.exception, original)


# ============================================================================
# call_gemini_with_retry tests
# ============================================================================

class TestCallWithRetry(unittest.TestCase):

    def setUp(self):
        self.sleeper = SleepRecorder()
        self.policy = RetryPolicy(
            max_attempts=3,
            base_delay_s=4.0,
            factor=2.0,
            jitter_frac=0.0,  # zero jitter for deterministic test sleeps
            quota_buffer_s=3.0,
            max_sleep_s=90.0,
        )

    def _call(self, provider):
        return call_gemini_with_retry(
            "sys", "user",
            provider_call=provider,
            model="gemini-test",
            policy=self.policy,
            sleep_fn=self.sleeper,
        )

    # --- happy path -------------------------------------------------------

    def test_clean_success_no_sleep(self):
        provider = MockProvider(["ok"])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        self.assertEqual(self.sleeper.sleeps, [])
        self.assertEqual(len(provider.calls), 1)

    def test_succeeds_after_one_503(self):
        provider = MockProvider([FakeAPIError(503, "down"), "ok"])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        self.assertEqual(len(self.sleeper.sleeps), 1)
        # First retry: base_delay * factor^0 = 4.0 (jitter=0)
        self.assertAlmostEqual(self.sleeper.sleeps[0], 4.0, places=3)

    def test_succeeds_after_two_503(self):
        provider = MockProvider([
            FakeAPIError(503, "down"),
            FakeAPIError(503, "still down"),
            "ok",
        ])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        self.assertEqual(len(self.sleeper.sleeps), 2)
        self.assertAlmostEqual(self.sleeper.sleeps[0], 4.0, places=3)
        self.assertAlmostEqual(self.sleeper.sleeps[1], 8.0, places=3)

    # --- 429 per-minute ---------------------------------------------------

    def test_429_per_minute_obeys_server_retry_delay(self):
        payload = _quota_payload(
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
            retry_delay="21s",
        )
        provider = MockProvider([
            FakeAPIError(429, "rate limited", payload),
            "ok",
        ])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        # Should sleep 21 + buffer(3) = 24
        self.assertEqual(len(self.sleeper.sleeps), 1)
        self.assertAlmostEqual(self.sleeper.sleeps[0], 24.0, places=3)

    def test_429_per_minute_caps_at_max_sleep(self):
        # Server returns ridiculous retryDelay — we cap it.
        payload = _quota_payload("PerMinute", retry_delay="3600s")
        provider = MockProvider([
            FakeAPIError(429, "rate limited", payload),
            "ok",
        ])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        self.assertEqual(self.sleeper.sleeps[0], self.policy.max_sleep_s)

    # --- 429 daily quota: NO retry ---------------------------------------

    def test_429_daily_quota_does_not_retry(self):
        payload = _quota_payload(
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
        )
        provider = MockProvider([FakeAPIError(429, "daily exhausted", payload)])
        with self.assertRaises(GeminiQuotaDailyError) as ctx:
            self._call(provider)
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(self.sleeper.sleeps, [])
        self.assertEqual(len(provider.calls), 1)

    # --- 4xx: NO retry ----------------------------------------------------

    def test_400_does_not_retry(self):
        provider = MockProvider([FakeAPIError(400, "bad request")])
        with self.assertRaises(GeminiClientError) as ctx:
            self._call(provider)
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(self.sleeper.sleeps, [])

    def test_401_does_not_retry(self):
        provider = MockProvider([FakeAPIError(401, "unauthenticated")])
        with self.assertRaises(GeminiClientError):
            self._call(provider)
        self.assertEqual(self.sleeper.sleeps, [])

    # --- exhaustion -------------------------------------------------------

    def test_persistent_503_exhausts_attempts(self):
        provider = MockProvider([
            FakeAPIError(503, "down"),
            FakeAPIError(503, "down"),
            FakeAPIError(503, "down"),
        ])
        with self.assertRaises(GeminiInfraError) as ctx:
            self._call(provider)
        # attempts counts TOTAL tries
        self.assertEqual(ctx.exception.attempts, 3)
        # 2 retries between 3 attempts -> 2 sleeps
        self.assertEqual(len(self.sleeper.sleeps), 2)
        self.assertEqual(len(provider.calls), 3)

    def test_attempts_field_is_total_tries_not_retries(self):
        # Documenting the agreed convention: attempts=1 means "one try, no
        # retry". attempts=3 with max_attempts=3 means "tried 3 times".
        provider = MockProvider([FakeAPIError(503, "down")])
        policy = RetryPolicy(max_attempts=1, jitter_frac=0.0)
        with self.assertRaises(GeminiInfraError) as ctx:
            call_gemini_with_retry(
                "s", "u", provider_call=provider, model="m",
                policy=policy, sleep_fn=self.sleeper,
            )
        self.assertEqual(ctx.exception.attempts, 1)
        # No sleeps: max_attempts=1 means we never wait
        self.assertEqual(self.sleeper.sleeps, [])

    # --- timeout / connection error --------------------------------------

    def test_timeout_is_retried_as_infra(self):
        provider = MockProvider([
            TimeoutError("connection timed out"),
            "ok",
        ])
        text = self._call(provider)
        self.assertEqual(text, "ok")
        self.assertEqual(len(self.sleeper.sleeps), 1)

    def test_connection_error_is_retried_as_infra(self):
        provider = MockProvider([
            ConnectionError("connection reset by peer"),
            "ok",
        ])
        text = self._call(provider)
        self.assertEqual(text, "ok")

    # --- unknown errors ---------------------------------------------------

    def test_unknown_exception_does_not_retry(self):
        # Conservative: if we couldn't classify it, don't burn quota retrying
        provider = MockProvider([ValueError("weird")])
        with self.assertRaises(GeminiUnknownError) as ctx:
            self._call(provider)
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(self.sleeper.sleeps, [])

    # --- never calls real time.sleep -------------------------------------

    def test_uses_injected_sleep_fn_not_real_time(self):
        # Sanity check: if we pass a recording sleeper, the test would
        # not have completed within seconds if real sleep was used
        # (we configure base_delay_s=4.0 above). The fact that the prior
        # tests run in milliseconds is the actual proof; this is just
        # an explicit assertion that recordings happened.
        provider = MockProvider([FakeAPIError(503, "down"), "ok"])
        self._call(provider)
        self.assertGreater(len(self.sleeper.sleeps), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
