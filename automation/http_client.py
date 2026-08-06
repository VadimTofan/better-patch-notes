from __future__ import annotations

from collections.abc import Callable, Iterable
from hashlib import sha256
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from automation.models import HttpResponse


ALLOWED_MIME_TYPES = {
    "application/atom+xml",
    "application/json",
    "application/rss+xml",
    "application/xml",
    "text/html",
    "text/plain",
    "text/xml",
}
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


class SourceError(RuntimeError):
    """Base error for safe source retrieval."""


class SourceRejected(SourceError):
    """The source violates an allowlist or response-safety rule."""


class SourceUnavailable(SourceError):
    """The source could not be retrieved after bounded attempts."""


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(
        self,
        validate_redirect: Callable[[str, str], None],
    ) -> None:
        super().__init__()
        self._validate_redirect = validate_redirect

    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> Request | None:
        self._validate_redirect(request.full_url, new_url)

        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


class BlizzardHttpClient:
    def __init__(
        self,
        allowed_hosts: Iterable[str],
        max_response_bytes: int,
        timeout_seconds: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        allow_insecure_localhost: bool = False,
    ) -> None:
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

        self._allowed_hosts = frozenset(
            host.lower().rstrip(".") for host in allowed_hosts
        )
        if not self._allowed_hosts:
            raise ValueError("allowed_hosts must not be empty")

        self._max_response_bytes = max_response_bytes
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._allow_insecure_localhost = allow_insecure_localhost
        self._opener = build_opener(
            _SafeRedirectHandler(self._validate_redirect),
        )

    def _validate_url(self, url: str, *, redirect: bool = False) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        label = "redirect host" if redirect else "source host"
        if host not in self._allowed_hosts:
            raise SourceRejected(f"{label} is not allowlisted: {host}")
        if parsed.username or parsed.password:
            raise SourceRejected("source URL must not contain credentials")
        if parsed.fragment:
            raise SourceRejected("source URL must not contain a fragment")

        insecure_localhost = (
            self._allow_insecure_localhost
            and host in {"127.0.0.1", "localhost", "::1"}
        )
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and insecure_localhost
        ):
            raise SourceRejected("source URL must use HTTPS")

    def _validate_redirect(self, old_url: str, new_url: str) -> None:
        self._validate_url(new_url, redirect=True)
        old_scheme = urlsplit(old_url).scheme
        new_scheme = urlsplit(new_url).scheme
        if old_scheme == "https" and new_scheme != "https":
            raise SourceRejected("redirect must not downgrade HTTPS")

    def _read_response(self, response: object) -> HttpResponse:
        final_url = response.geturl()
        self._validate_url(final_url)

        raw_content_type = response.headers.get("Content-Type", "")
        mime_type = raw_content_type.split(";", 1)[0].strip().lower()
        if mime_type not in ALLOWED_MIME_TYPES:
            raise SourceRejected(f"unsupported MIME type: {mime_type or 'missing'}")

        raw_content_length = response.headers.get("Content-Length")
        if raw_content_length:
            try:
                content_length = int(raw_content_length)
            except ValueError as error:
                raise SourceRejected("invalid Content-Length") from error
            if content_length > self._max_response_bytes:
                raise SourceRejected("response limit exceeded")

        body = response.read(self._max_response_bytes + 1)
        if len(body) > self._max_response_bytes:
            raise SourceRejected("response limit exceeded")

        return HttpResponse(
            body=body,
            final_url=final_url,
            mime_type=mime_type,
            status=response.status,
            content_hash=sha256(body).hexdigest(),
        )

    def get(self, url: str) -> HttpResponse:
        self._validate_url(url)
        request = Request(
            url,
            headers={"User-Agent": "BetterPatchNotes/automatic-refresh"},
            method="GET",
        )

        for attempt in range(3):
            try:
                with self._opener.open(
                    request,
                    timeout=self._timeout_seconds,
                ) as response:
                    return self._read_response(response)
            except SourceRejected:
                raise
            except HTTPError as error:
                if error.code not in TRANSIENT_HTTP_STATUSES:
                    raise SourceUnavailable(f"source returned HTTP {error.code}") from error
                last_error: Exception = error
            except URLError as error:
                last_error = error

            if attempt < 2:
                self._sleep(float(2**attempt))

        raise SourceUnavailable("source unavailable after 3 attempts") from last_error
