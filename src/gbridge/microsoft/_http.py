"""Thin HTTP helper for Microsoft Graph calls.

This module centralises:
- Bearer-token auth header injection from MicrosoftAuthManager
- Retry on 429 (respecting Retry-After) and 5xx transient errors
- Detection of 410 GONE for expired delta tokens (raised as DeltaExpiredError)
- @odata.nextLink pagination helper

Using `requests` keeps us dependency-light and lets the tests stub via
the `responses` library without pulling in an async runtime.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Any, cast

import requests

from gbridge.config.defaults import (
    BASE_RETRY_DELAY_SECONDS,
    MAX_RETRIES,
    MICROSOFT_GRAPH_BASE,
)

if TYPE_CHECKING:
    from gbridge.microsoft.auth import MicrosoftAuthManager

logger = logging.getLogger(__name__)

# Graph transient codes — safe to retry.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Hard cap on Retry-After to avoid hanging if Graph returns a huge value.
_MAX_RETRY_AFTER_SECONDS = 60.0


class GraphError(RuntimeError):
    """Non-retryable Graph API failure."""

    def __init__(self, status: int, message: str, body: Any = None) -> None:
        super().__init__(f"Graph API {status}: {message}")
        self.status = status
        self.body = body


class DeltaExpiredError(GraphError):
    """The delta/sync token is no longer valid — caller should redo full fetch."""


class PreconditionFailedError(GraphError):
    """Etag mismatch on an If-Match write. Caller should refetch and retry."""


class GraphClient:
    """Authenticated Microsoft Graph HTTP client with retries and pagination."""

    def __init__(
        self,
        auth: MicrosoftAuthManager,
        *,
        base_url: str = MICROSOFT_GRAPH_BASE,
        max_retries: int = MAX_RETRIES,
        base_delay: float = BASE_RETRY_DELAY_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._session = session or requests.Session()

    # ---- public surface ----------------------------------------------------

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a single Graph URL (absolute or relative)."""
        return self._request("GET", url, params=params)

    def post(
        self, url: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._request("POST", url, json=json)

    def patch(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        if_match: str | None = None,
    ) -> dict[str, Any]:
        return self._request("PATCH", url, json=json, if_match=if_match)

    def delete(self, url: str, *, if_match: str | None = None) -> None:
        self._request("DELETE", url, if_match=if_match, expect_json=False)

    def iter_pages(
        self, url: str, *, params: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Follow @odata.nextLink, accumulating `value` items.

        Returns (items, delta_link). ``delta_link`` is the ``@odata.deltaLink``
        from the final page (if present) — callers store it for the next
        incremental fetch.
        """
        items: list[dict[str, Any]] = []
        delta_link: str | None = None
        next_url: str | None = url
        next_params: dict[str, Any] | None = params

        while next_url:
            body = self.get(next_url, params=next_params)
            for item in body.get("value", []):
                items.append(item)
            next_url = body.get("@odata.nextLink")
            # Only the first request uses our explicit params.
            next_params = None
            delta_link = body.get("@odata.deltaLink") or delta_link

        return items, delta_link

    # ---- internals ---------------------------------------------------------

    def _full_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._base_url}/{url.lstrip('/')}"

    def _auth_headers(self) -> dict[str, str]:
        token = self._auth.get_credentials()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def _request(  # noqa: PLR0912
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        if_match: str | None = None,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        full_url = self._full_url(url)
        headers = self._auth_headers()
        headers["Accept"] = "application/json"
        if json is not None:
            headers["Content-Type"] = "application/json"
        if if_match:
            headers["If-Match"] = if_match

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    full_url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=30,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise GraphError(0, str(exc)) from exc
                self._sleep_backoff(attempt)
                continue

            status = response.status_code
            if 200 <= status < 300:
                if not expect_json or status == 204 or not response.content:
                    return {}
                return cast("dict[str, Any]", response.json())

            if status == 410:
                # Expired delta/sync token
                raise DeltaExpiredError(status, "delta token expired", response.text)

            if status == 412:
                # Etag mismatch on If-Match — not retryable, pusher handles it.
                raise PreconditionFailedError(
                    status, "precondition failed (etag mismatch)", response.text
                )

            if status in _RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                retry_after = self._parse_retry_after(response)
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                logger.warning(
                    "Graph %s %s -> %d, retrying in %.1fs (%d/%d)",
                    method,
                    url,
                    status,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                time.sleep(delay)
                continue

            # Non-retryable or out of retries
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise GraphError(status, response.reason or "error", body)

        # Only reachable via an unreachable code path — keep type checker happy.
        if last_exc is not None:
            raise GraphError(0, str(last_exc)) from last_exc
        raise GraphError(0, "retry loop exhausted")  # pragma: no cover

    @staticmethod
    def _parse_retry_after(response: requests.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if not raw:
            return None
        try:
            seconds = float(raw)
        except ValueError:
            return None
        return min(max(0.0, seconds), _MAX_RETRY_AFTER_SECONDS)

    def _backoff(self, attempt: int) -> float:
        return float(self._base_delay * (2**attempt) + random.uniform(0, 0.5))  # noqa: S311

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self._backoff(attempt))
