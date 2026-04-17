"""Tests for `utils.backoff` — retries, Retry-After, non-retryable path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gbridge.utils.backoff import _retry_after_seconds, retry_on_api_error


def _make_http_error(status: int, retry_after: str | None = None) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "error"
    headers = {}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp.get = lambda key, default=None: headers.get(key.lower(), default)
    return HttpError(resp=resp, content=b"", uri="")


class TestRetryAfterParsing:
    def test_numeric_retry_after(self) -> None:
        exc = _make_http_error(429, retry_after="3")
        assert _retry_after_seconds(exc) == 3.0

    def test_caps_huge_values(self) -> None:
        exc = _make_http_error(429, retry_after="3600")
        assert _retry_after_seconds(exc) == 60.0

    def test_non_numeric_returns_none(self) -> None:
        exc = _make_http_error(429, retry_after="later please")
        assert _retry_after_seconds(exc) is None

    def test_missing_header_returns_none(self) -> None:
        exc = _make_http_error(429)
        assert _retry_after_seconds(exc) is None


class TestRetryDecorator:
    def test_success_on_first_try(self) -> None:
        calls: list[int] = []

        @retry_on_api_error(max_retries=2, base_delay=0)
        def fn() -> str:
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_retries_on_429(self) -> None:
        attempts = {"n": 0}

        @retry_on_api_error(max_retries=3, base_delay=0)
        def fn() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _make_http_error(429)
            return "done"

        with patch("gbridge.utils.backoff.time.sleep"):
            assert fn() == "done"
        assert attempts["n"] == 3

    def test_honors_retry_after_header(self) -> None:
        @retry_on_api_error(max_retries=2, base_delay=1)
        def fn() -> str:
            raise _make_http_error(429, retry_after="2")

        with patch("gbridge.utils.backoff.time.sleep") as sleep:
            with pytest.raises(HttpError):
                fn()
            # Every retry-sleep should be exactly the retry-after (2.0).
            for call in sleep.call_args_list:
                assert call.args[0] == 2.0

    def test_non_retryable_raises_immediately(self) -> None:
        calls = {"n": 0}

        @retry_on_api_error(max_retries=3, base_delay=0)
        def fn() -> str:
            calls["n"] += 1
            raise _make_http_error(403)  # auth error — not retryable

        with pytest.raises(HttpError):
            fn()
        assert calls["n"] == 1

    def test_exhausts_then_raises(self) -> None:
        @retry_on_api_error(max_retries=2, base_delay=0)
        def fn() -> str:
            raise _make_http_error(500)

        with patch("gbridge.utils.backoff.time.sleep"), pytest.raises(HttpError):
            fn()
