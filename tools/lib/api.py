"""
Shared HTTP client with retry, timeout, and proper error handling.
Built on httpx with a reusable Client for connection pooling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(Exception):
    """Raised when an API call returns a non-success status."""

    def __init__(self, status: int, body: Any, path: str):
        self.status = status
        self.body = body
        self.path = path
        super().__init__(f"API error {status} on {path}: {body}")


@dataclass(frozen=True)
class ApiResponse:
    """Normalized API response."""

    status: int
    data: Any  # dict | list | str | bytes


DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


class ApiClient:
    """HTTP client with API key auth, retry, and typed error handling.

    Reuses a single httpx.Client for connection pooling. Can be used as a
    context manager so the underlying client is closed cleanly:

        with ApiClient(base_url, key) as client:
            client.get("/resumes")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.retries = retries
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _headers(self, has_body: bool = False) -> dict[str, str]:
        h = {"x-api-key": self.api_key}
        if has_body:
            h["Content-Type"] = "application/json"
        return h

    def request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
    ) -> ApiResponse:
        """Make an API request with retry logic.

        Returns ApiResponse on success (2xx).
        Raises ApiError on non-retryable failure after exhausting retries.
        """
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data is not None else None
        headers = self._headers(has_body=body is not None)

        last_error: ApiError | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._client.request(
                    method,
                    url,
                    content=body,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                if attempt < self.retries:
                    continue
                raise ApiError(0, str(exc), path) from exc

            status = resp.status_code
            content_type = resp.headers.get("content-type", "")

            if 200 <= status < 300:
                if "application/pdf" in content_type:
                    return ApiResponse(status, resp.content)
                text = resp.text
                if text:
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = text.strip().strip('"')
                    return ApiResponse(status, parsed)
                return ApiResponse(status, None)

            error_body: Any
            try:
                error_body = resp.json()
            except (json.JSONDecodeError, ValueError):
                error_body = resp.text

            last_error = ApiError(status, error_body, path)
            if status not in RETRYABLE_STATUSES:
                break

        raise last_error  # type: ignore[misc]

    def get(self, path: str) -> ApiResponse:
        return self.request("GET", path)

    def post(self, path: str, data: dict | None = None) -> ApiResponse:
        return self.request("POST", path, data)

    def put(self, path: str, data: dict | None = None) -> ApiResponse:
        return self.request("PUT", path, data)

    def delete(self, path: str) -> ApiResponse:
        return self.request("DELETE", path)
