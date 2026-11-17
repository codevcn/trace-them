"""Conservative interpretation of legacy website detection rules."""

import json
import re
from urllib.parse import urlsplit

from .models import Status


BLOCK_MARKERS = (
    'id="challenge-error-text"', "awswafintegration.forcerefreshtoken",
    "cf-chl-", "challenge-platform", "verify you are human", "verify that you are human",
    "checking your browser", "captcha challenge", "g-recaptcha", "hcaptcha",
    "perimeterxidentifiers", "access to this page has been denied",
    "please enable javascript and cookies to continue", "just a moment...",
)


def detect(response, site_info: dict) -> tuple[Status, str]:
    if getattr(response, "trace_them_policy_blocked", False):
        return Status.BLOCKED, "Redirect to an authentication/registration endpoint was not followed"
    code = response.status_code
    if code == 429:
        return Status.RATE_LIMITED, "HTTP 429: server rate limit; no absence conclusion"
    if code in (401, 403, 407, 451):
        return Status.BLOCKED, f"HTTP {code}: access restricted; no absence conclusion"
    if code >= 500:
        return Status.ERROR, f"HTTP {code}: server failure; no absence conclusion"
    text = response.text
    lower = text.lower()
    if any(marker in lower for marker in BLOCK_MARKERS):
        return Status.BLOCKED, "Response contains a bot challenge or access denial"
    if any(marker in lower for marker in ("too many requests", "rate limit exceeded", "rate limited")):
        return Status.RATE_LIMITED, "Response reports rate limiting; no absence conclusion"
    if any(marker in lower for marker in ("services are temporarily offline", "internal server error",
                                          "service unavailable", "temporarily unavailable")):
        return Status.ERROR, "Response reports a service failure; no absence conclusion"
    title = re.search(r"<title[^>]*>(.*?)</title>", lower, flags=re.S)
    title_text = re.sub(r"\s+", " ", title.group(1)) if title else ""
    location = response.headers.get("Location", "")
    paths = [urlsplit(response.url or "").path, urlsplit(location).path]
    for hop in getattr(response, "history", []):
        paths.extend((urlsplit(hop.url or "").path, urlsplit(hop.headers.get("Location", "")).path))
    if any(re.search(r"(?:^|/)(?:login|signin|sign-in|log-in|auth)(?:/|$)", p, re.I) for p in paths):
        return Status.BLOCKED, "Response or redirect leads to an authentication page"
    if re.search(r"\b(?:log[ -]?in|sign[ -]?in)\b", title_text):
        return Status.BLOCKED, "Response title indicates a login page"
    if re.search(r"<input\b[^>]*\btype\s*=\s*[\"']?password\b", lower):
        outside_forms = re.sub(r"<(form|head|script|style)\b[^>]*>.*?</\1>", "", lower,
                               flags=re.S)
        visible = re.sub(r"<[^>]+>", "", outside_forms).strip()
        if len(visible) < 120:
            return Status.BLOCKED, "Response is dominated by an authentication form"
    if code in (404, 410):
        return Status.NOT_FOUND, f"HTTP {code}: public profile endpoint reports absence"
    error_codes = site_info.get("errorCode", [])
    if isinstance(error_codes, int):
        error_codes = [error_codes]
    # Explicit negative codes only count after block/transient checks above.
    if code in error_codes:
        return Status.NOT_FOUND, f"HTTP {code}: configured negative status"
    error_types = site_info.get("errorType", [])
    if isinstance(error_types, str):
        error_types = [error_types]
    if not error_types or any(t not in ("message", "status_code", "response_url") for t in error_types):
        return Status.UNSUPPORTED, "Unsupported or missing detection method"
    if 300 <= code < 400:
        error_url = site_info.get("errorUrl")
        if "response_url" in error_types and error_url and location:
            # A generic redirect is ambiguous; only a matching configured
            # negative destination is evidence for absence.
            configured = urlsplit(error_url)
            actual = urlsplit(location)
            if (actual.hostname in (None, configured.hostname) and actual.path == configured.path
                    and (not configured.query or actual.query == configured.query)):
                return Status.NOT_FOUND, "Redirect matches configured negative destination"
        return Status.UNKNOWN, f"HTTP {code}: redirect is not evidence of profile existence"
    if not 200 <= code < 300:
        return Status.ERROR, f"HTTP {code}: unexpected request failure"
    if re.search(r"\b(?:internal server error|service unavailable|temporarily unavailable|something went wrong)\b", title_text):
        return Status.UNKNOWN, "Generic error page with successful HTTP status"
    # JSON errors sometimes arrive as 200. Do not mistake an error envelope for
    # a real profile, or an empty collection for evidence of existence.
    content_type = response.headers.get("Content-Type", "").lower()
    json_value = None
    parsed_json = False
    if "json" in content_type or text.lstrip().startswith(("{", "[")):
        try:
            value = json.loads(text)
            json_value = value
            parsed_json = True
        except (ValueError, TypeError):
            return Status.UNKNOWN, "Malformed JSON response"
        if isinstance(value, dict) and (value.get("error") or value.get("errors") or value.get("success") is False):
            return Status.UNKNOWN, "JSON response contains an error envelope"
        if isinstance(value, dict) and str(value.get("status", "")).lower() in ("error", "failed", "failure"):
            return Status.UNKNOWN, "JSON response reports an unsuccessful operation"
    if "message" in error_types:
        if site_info.get("request_method") == "HEAD" and not text.strip():
            return Status.UNKNOWN, "HEAD response cannot evaluate negative message markers"
        errors = site_info.get("errorMsg", [])
        if isinstance(errors, str):
            errors = [errors]
        if not errors or not all(isinstance(item, str) and item for item in errors):
            return Status.UNSUPPORTED, "Message detector requires nonempty negative markers"
        if any(error in text for error in errors):
            if any(error in text and error.strip().lower() in ("sorry.", "something went wrong", "error")
                   for error in errors):
                return Status.UNKNOWN, "Generic error marker is insufficient to establish profile absence"
            return Status.NOT_FOUND, "Response matches a configured negative message"
    if parsed_json and (not isinstance(json_value, (dict, list)) or not json_value):
        return Status.UNKNOWN, "Empty JSON response does not establish a public profile"
    if re.search(r"\b(?:not found|does not exist|something went wrong|service unavailable|internal server error)\b", title_text):
        return Status.UNKNOWN, "Generic missing/error page does not match the configured negative rule"
    if len(text) < 2000 and re.search(r"\b(?:something went wrong|service temporarily unavailable|internal server error)\b", lower):
        return Status.UNKNOWN, "Generic error body with successful HTTP status"
    if not text.strip() and site_info.get("request_method") != "HEAD":
        return Status.UNKNOWN, "Empty successful response does not establish a public profile"
    # SPA bootstrap shells with no rendered content cannot prove existence.
    if ("<script" in lower
            or re.search(r"<(?:div|main)\b[^>]*\bid=[\"'](?:root|app|__next)[\"'][^>]*>\s*</", text, re.I)):
        visible = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
        visible = re.sub(r"<head\b[^>]*>.*?</head>", "", visible, flags=re.I | re.S)
        visible = re.sub(r"<[^>]+>", "", visible).strip()
        if len(visible) < 40:
            return Status.UNKNOWN, "JavaScript bootstrap shell has no usable profile content"
    if "message" in error_types:
        return Status.FOUND, "Successful public response lacks configured negative messages (heuristic)"
    return Status.FOUND, "Successful public profile HTTP response (heuristic)"
