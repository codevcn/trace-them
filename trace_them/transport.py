"""Bounded HTTP transport: every wire attempt is explicit and budgeted."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests


class _ManualRedirectSession(requests.Session):
    def resolve_redirects(self, response, request, **kwargs):
        # Session.send() calls this even with allow_redirects=False to populate
        # response._next, consuming the body before our bounded reader sees it.
        # All redirect preparation and wire attempts belong to HTTPTransport.
        return iter(())


class OfflineError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class ScanCancelled(RuntimeError):
    pass


class RetryDeferred(RuntimeError):
    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.response = response


class RequestBudget:
    def __init__(self, limit: int = 500):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("Request budget must be a nonnegative integer")
        self.limit = limit
        self._used = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return self.limit - self._used

    def consume(self) -> None:
        with self._lock:
            if self._used >= self.limit:
                raise BudgetExceeded("The shared request budget is exhausted")
            self._used += 1


class HTTPTransport:
    def __init__(self, budget: RequestBudget, timeout=(5, 15), retries: int = 1,
                 per_domain_interval: float = 0.25, max_retry_after: float = 10,
                 offline: bool = False, cancel_event=None, proxy: str | None = None):
        if len(timeout) != 2 or any(not math.isfinite(v) or v <= 0 for v in timeout):
            raise ValueError("Connect and read timeouts must be positive and finite")
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 5:
            raise ValueError("Retries must be an integer between 0 and 5")
        if any(not math.isfinite(v) or v < 0 for v in (per_domain_interval, max_retry_after)):
            raise ValueError("Rate and retry delays must be finite and nonnegative")
        self.budget = budget
        self.timeout = timeout
        self.retries = retries
        self.per_domain_interval = per_domain_interval
        self.max_retry_after = max_retry_after
        self.offline = offline
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.max_redirects = 5
        self.max_response_bytes = 2 * 1024 * 1024
        self.proxy = proxy
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions = []
        self._next_request = {}
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _check(self):
        if self.cancel_event.is_set():
            raise ScanCancelled("Scan cancelled")
        if self._closed:
            raise ScanCancelled("Transport is closed")
        if self.offline:
            raise OfflineError("Network access is disabled by offline mode")

    def _wait(self, delay: float):
        if delay > 0 and self.cancel_event.wait(delay):
            raise ScanCancelled("Scan cancelled while waiting")
        self._check()

    @staticmethod
    def _domain(url: str) -> str:
        host = (urlsplit(url).hostname or "").lower()
        # Conservative grouping: shared parent domains share a limiter. This may
        # throttle unrelated co.uk hosts together, which is safe, not a bypass.
        return ".".join(host.split(".")[-2:])

    @staticmethod
    def _validate_url(url: str):
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise requests.exceptions.InvalidURL("Only HTTP(S) URLs without embedded credentials are supported")

    def _throttle(self, url: str):
        domain = self._domain(url)
        while True:
            self._check()
            if self.budget.remaining == 0:
                raise BudgetExceeded("The shared request budget is exhausted")
            with self._lock:
                now = time.monotonic()
                delay = self._next_request.get(domain, now) - now
                if delay <= 0:
                    self._next_request[domain] = now + self.per_domain_interval
                    return
            self._wait(delay)

    def _session(self):
        if not hasattr(self._local, "session"):
            session = _ManualRedirectSession()
            # Explicit proxies remain supported. Disabling environment discovery
            # also prevents implicit netrc credentials across origin boundaries.
            session.trust_env = False
            if self.proxy:
                session.proxies = {"http": self.proxy, "https": self.proxy}
            session.headers["User-Agent"] = "TraceThem/1.0 (public profile lookup)"
            # requests defaults to zero retries; make that invariant explicit.
            for scheme in ("http://", "https://"):
                session.mount(scheme, requests.adapters.HTTPAdapter(max_retries=0))
            with self._lock:
                if self._closed:
                    session.close()
                    raise ScanCancelled("Transport is closed")
                self._sessions.append(session)
            self._local.session = session
        return self._local.session

    @staticmethod
    def _retry_delay(response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                delay = float(value)
                if math.isfinite(delay):
                    return max(0.0, delay)
            except ValueError:
                try:
                    date = parsedate_to_datetime(value)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(0.5 * (2 ** attempt), 4)

    def request(self, method: str, url: str, **kwargs):
        self._check()
        self._validate_url(url)
        method = method.upper()
        if method not in ("GET", "HEAD", "POST", "PUT"):
            raise ValueError("Unsupported HTTP method")
        allow_redirects = kwargs.pop("allow_redirects", True)
        kwargs.setdefault("timeout", self.timeout)
        kwargs["stream"] = True
        kwargs["headers"] = dict(kwargs.get("headers") or {})
        redirects = 0
        attempt = 0
        history = []
        while True:
            self._throttle(url)
            self._check()
            self.budget.consume()
            try:
                response = self._session().request(method, url, allow_redirects=False, **kwargs)
                self._read_bounded(response)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if method not in ("GET", "HEAD") or attempt >= self.retries:
                    raise
                self._wait(min(0.5 * (2 ** attempt), self.max_retry_after))
                attempt += 1
                continue
            try:
                self._check()
            except (OfflineError, ScanCancelled):
                response.close()
                raise
            if response.status_code in (429, 502, 503, 504) and method in ("GET", "HEAD") and attempt < self.retries:
                if self.budget.remaining == 0:
                    response.history = history
                    return response
                delay = self._retry_delay(response, attempt)
                if delay > self.max_retry_after:
                    raise RetryDeferred("Retry-After exceeds the bounded wait; retry later", response)
                with self._lock:
                    domain = self._domain(url)
                    self._next_request[domain] = max(self._next_request.get(domain, 0), time.monotonic() + delay)
                response.close()
                self._wait(delay)
                attempt += 1
                continue
            location = response.headers.get("Location")
            if allow_redirects and response.status_code in (301, 302, 303, 307, 308) and location:
                if redirects >= self.max_redirects:
                    response.close()
                    raise requests.exceptions.TooManyRedirects("Redirect limit exceeded")
                next_url = urljoin(url, location)
                self._validate_url(next_url)
                # Redirects must not turn public profile reads into auth or
                # registration enumeration, including encoded endpoint names.
                from .manifest import restricted_endpoint

                if restricted_endpoint(next_url):
                    response.trace_them_policy_blocked = True
                    response.history = history
                    return response
                previous = urlsplit(url)
                upcoming = urlsplit(next_url)
                if (previous.scheme, previous.hostname, previous.port) != (upcoming.scheme, upcoming.hostname, upcoming.port):
                    kwargs["headers"] = {k: v for k, v in kwargs["headers"].items() if k.lower() not in ("authorization", "cookie", "host")}
                    kwargs.pop("auth", None)
                    kwargs.pop("cookies", None)
                    self._session().cookies.clear()
                if ((response.status_code == 303 and method != "HEAD")
                        or (response.status_code in (301, 302) and method == "POST")):
                    method = "GET"
                    for key in ("json", "data", "files"):
                        kwargs.pop(key, None)
                kwargs.pop("params", None)
                history.append(response)
                response.close()
                url = next_url
                redirects += 1
                continue
            response.history = history
            return response

    def _read_bounded(self, response):
        try:
            # Test adapters and cached responses may already have materialized
            # content. Normal wire responses are streamed and decompressed here.
            if isinstance(getattr(response, "_content", None), bytes):
                if len(response._content) > self.max_response_bytes:
                    raise requests.exceptions.ContentDecodingError("Response exceeds the 2 MiB body limit")
                return
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=65536):
                self._check()
                size += len(chunk)
                if size > self.max_response_bytes:
                    raise requests.exceptions.ContentDecodingError("Response exceeds the 2 MiB body limit")
                chunks.append(chunk)
            response._content = b"".join(chunks)
            response._content_consumed = True
        except BaseException:
            response.close()
            raise

    def close(self):
        self.cancel_event.set()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            session.close()
