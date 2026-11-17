"""Concurrent exact-handle scanner; identity ownership is never inferred here."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time
from urllib.parse import quote

import requests

from .detector import detect
from .models import Candidate, Evidence, Finding, Status
from .transport import BudgetExceeded, OfflineError, RetryDeferred, ScanCancelled


def interpolate(value, username):
    if isinstance(value, str):
        return value.replace("{}", username)
    if isinstance(value, dict):
        return {k: interpolate(v, username) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, username) for v in value]
    return value


class Scanner:
    def __init__(self, transport, max_workers: int = 10):
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 32:
            raise ValueError("Worker count must be between 1 and 32")
        self.transport = transport
        self.max_workers = max_workers

    def _scan_one(self, username, platform, info, candidate):
        encoded = quote(username, safe="")
        url = interpolate(info["url"], encoded)
        probe = interpolate(info.get("urlProbe", info["url"]), encoded)
        origins = [Evidence("candidate_origin:" + item.kind, item.source,
                    item.detail, item.observed_at) for item in candidate.evidence]
        origins.append(Evidence("candidate_origin", "input", f"Origin: {candidate.origin}; username: {username}"))
        finding = Finding(platform, username, url, Status.UNKNOWN, "Not queried",
                          evidence=origins, origin=candidate.origin)
        if not username or username in (".", "..") or any(ord(char) < 32 or ord(char) == 127 for char in username):
            finding.status, finding.reason = Status.INVALID, "Username is empty or contains control characters"
            return finding
        regex = info.get("regexCheck")
        if regex and re.search(regex, username) is None:
            finding.status, finding.reason = Status.INVALID, "Username fails this platform's configured syntax"
            return finding
        method = info.get("request_method", "GET")
        # GET lets detectors inspect login/WAF pages even for status-code sites.
        kwargs = {"headers": dict(info.get("headers", {})), "allow_redirects": True}
        if "response_url" in ([info["errorType"]] if isinstance(info["errorType"], str) else info["errorType"]):
            kwargs["allow_redirects"] = False
        if info.get("request_payload") is not None:
            kwargs["json"] = interpolate(info["request_payload"], username)
        started = time.monotonic()
        response = None
        try:
            response = self.transport.request(method, probe, **kwargs)
            site_info = dict(info)
            if "errorUrl" in site_info:
                site_info["errorUrl"] = interpolate(site_info["errorUrl"], encoded)
            finding.status, finding.reason = detect(response, site_info)
            finding.http_status = response.status_code
            finding.evidence.append(Evidence("http_response", response.url or probe,
                f"{method} returned HTTP {response.status_code}. {finding.reason}"))
            for hop in getattr(response, "history", []):
                finding.evidence.append(Evidence("redirect", hop.url or probe,
                    f"HTTP {hop.status_code}; Location: {hop.headers.get('Location', '')[:512]}"))
        except OfflineError:
            finding.status, finding.reason = Status.UNKNOWN, "Offline mode: profile not queried"
        except BudgetExceeded:
            finding.status, finding.reason = Status.BUDGET_EXHAUSTED, "Shared request budget exhausted; profile not established"
        except ScanCancelled:
            finding.status, finding.reason = Status.CANCELLED, "Scan cancelled; profile not established"
        except RetryDeferred as error:
            response = error.response
            finding.http_status = response.status_code if response is not None else None
            finding.status = Status.RATE_LIMITED if finding.http_status == 429 else Status.ERROR
            finding.reason = str(error)
            finding.evidence.append(Evidence("retry_deferred", probe, str(error)))
        except (requests.exceptions.RequestException, UnicodeError, ValueError) as error:
            finding.status = Status.ERROR
            # Avoid storing proxy credentials, huge response bodies or query
            # secrets from exception strings.
            finding.reason = f"Request failed: {type(error).__name__}"
        finally:
            finding.query_time = time.monotonic() - started
            if response is not None:
                response.close()
        return finding

    def scan(self, username: str, sites: dict, *, candidate: Candidate | None = None) -> list[Finding]:
        candidate = candidate or Candidate(username)
        if candidate.username != username:
            raise ValueError("Candidate username must match scanned username")
        if not sites:
            return []
        executor = ThreadPoolExecutor(max_workers=min(len(sites), self.max_workers))
        futures = {}
        try:
            futures = {executor.submit(self._scan_one, username, name, info, candidate): name for name, info in sites.items()}
            result = {futures[future]: future.result() for future in as_completed(futures)}
            return [result[name] for name in sites]
        except KeyboardInterrupt:
            self.transport.cancel_event.set()
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
