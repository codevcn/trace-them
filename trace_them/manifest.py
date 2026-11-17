"""Load legacy Sherlock manifests with an enforced public-source policy."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .transport import OfflineError


RESOURCE_DIR = Path(__file__).with_name("resources")


@dataclass
class Manifest:
    sites: dict
    skipped: dict
    source: str


# The rule applies to custom and remote manifests too: changing a target name
# cannot make a registration or authentication endpoint a public profile source.
AUTH_ENDPOINT = re.compile(
    r"(?:^|[/?.=&_-])(?:signup|sign-up|register|registration|login|signin|password-reset|"
    r"reset-password|forgot-password|usernameExists|check_username|check_nickname|"
    r"username-attempt|availability|validate)(?:$|[/?.=&_-])", re.I)
KNOWN_RESTRICTIONS = {
    "boardgamegeek": "Registration username validation endpoint",
    "chess": "Username validation endpoint rather than public profile data",
    "discord": "Unauthenticated registration username-attempt endpoint",
    "diskusjon.no": "Registration usernameExists endpoint",
    "holopin": "Authentication username validation endpoint",
    "kvinneguiden": "Registration usernameExists endpoint",
    "dailykos": "Signup nickname validation endpoint",
    "minds": "Registration username validation endpoint",
    "omg.lol": "Address availability endpoint rather than public profile data",
    "hudsonrock": "Breach-associated lookup rather than a public profile source",
    "librarything": "Legacy probe uses a manufactured human-verification cookie",
}


def restricted_endpoint(url: str) -> bool:
    """Match wire-equivalent encoded paths, including nested escaping."""
    for _ in range(6):
        decoded = unquote(url)
        if decoded == url:
            break
        url = decoded
    parsed = urlsplit(url.replace("\\", "/"))
    path = parsed.path + "?" + parsed.query
    return bool(AUTH_ENDPOINT.search(path) or re.search(r"(?:^|/)auth/username(?:/|$)", path, re.I)
                or parsed.path.lower().endswith("/callback/user/valid"))


def _url(value: str, field: str, name: str):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name}: {field} must be a nonempty HTTP(S) URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{name}: invalid {field}") from error
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or port is not None and not 0 < port < 65536):
        raise ValueError(f"{name}: {field} must use HTTP(S), a host, and no embedded credentials")


def policy_reason(name: str, info: dict) -> str | None:
    if name.casefold() in KNOWN_RESTRICTIONS:
        return KNOWN_RESTRICTIONS[name.casefold()]
    probe = info.get("urlProbe", info["url"])
    parsed = urlsplit(probe)
    if restricted_endpoint(probe):
        return "Authentication, registration, or availability endpoint is excluded by public-source policy"
    if parsed.hostname and parsed.hostname.endswith("hudsonrock.com"):
        return "Breach-associated lookup is outside public profile scope"
    if re.search(r"(?:^|/)auth/username(?:/|$)", parsed.path, re.I):
        return "Authentication username endpoint is excluded"
    if parsed.path.lower().endswith("/callback/user/valid"):
        return "Username validation endpoint is excluded"
    if "{}" not in info["url"]:
        return "No username-specific public profile URL is configured"
    if info.get("request_method", "GET") == "PUT":
        return "Mutating PUT methods are outside public lookup scope"
    headers = info.get("headers", {})
    if any(key.lower() in ("authorization", "cookie") for key in headers):
        return "Authenticated or cookie-dependent probes require separate source review"
    return None


def _validate(name: str, info: dict):
    if not name or not isinstance(info, dict):
        raise ValueError(f"{name!r}: target must be an object")
    for field in ("url", "urlMain"):
        if field not in info:
            raise ValueError(f"{name}: missing {field}")
        _url(info[field], field, name)
    if "urlProbe" in info:
        _url(info["urlProbe"], "urlProbe", name)
    if "errorUrl" in info:
        # Historical manifests contain bare domains in errorUrl; detector
        # comparisons remain conservative for those records.
        if not isinstance(info["errorUrl"], str) or not info["errorUrl"]:
            raise ValueError(f"{name}: errorUrl must be a nonempty string")
    types = info.get("errorType")
    types = [types] if isinstance(types, str) else types
    if not isinstance(types, list) or not types or any(t not in ("message", "response_url", "status_code") for t in types):
        raise ValueError(f"{name}: invalid or missing errorType")
    if "message" in types:
        errors = info.get("errorMsg")
        errors = [errors] if isinstance(errors, str) else errors
        if not isinstance(errors, list) or not errors or any(not isinstance(e, str) or not e for e in errors):
            raise ValueError(f"{name}: message detection requires nonempty errorMsg")
    if "errorCode" in info:
        codes = info["errorCode"]
        codes = [codes] if isinstance(codes, int) else codes
        if not isinstance(codes, list) or any(isinstance(c, bool) or not isinstance(c, int) or not 100 <= c <= 599 for c in codes):
            raise ValueError(f"{name}: invalid errorCode")
    if info.get("request_method", "GET") not in ("GET", "HEAD", "POST", "PUT"):
        raise ValueError(f"{name}: unsupported request_method")
    pattern = info.get("regexCheck")
    if pattern is not None:
        if not isinstance(pattern, str) or len(pattern) > 2048:
            raise ValueError(f"{name}: invalid regexCheck")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"{name}: invalid regexCheck: {error}") from error
    headers = info.get("headers", {})
    if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) or any(c in k + v for c in "\r\n") for k, v in headers.items()):
        raise ValueError(f"{name}: headers must be plain string values without newlines")
    if "request_payload" in info and not isinstance(info["request_payload"], dict):
        raise ValueError(f"{name}: request_payload must be an object")
    if "isNSFW" in info and not isinstance(info["isNSFW"], bool):
        raise ValueError(f"{name}: isNSFW must be a boolean")


def load_manifest(path=None, *, transport=None, offline=False, include_nsfw=False,
                  sites=None) -> Manifest:
    source = str(path) if path is not None else str(RESOURCE_DIR / "data.json")
    if source.lower().startswith(("http://", "https://")):
        if offline:
            raise OfflineError("Remote manifests are unavailable offline")
        if transport is None:
            raise ValueError("Remote manifests require the shared HTTP transport")
        response = transport.request("GET", source)
        try:
            response.raise_for_status()
            if len(response.content) > 5_000_000:
                raise ValueError("Remote manifest exceeds the 5 MB size limit")
            data = response.json()
        finally:
            response.close()
    else:
        resource = Path(source)
        if resource.stat().st_size > 5_000_000:
            raise ValueError("Manifest exceeds the 5 MB size limit")
        with resource.open(encoding="utf-8") as stream:
            data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("Manifest must contain a JSON object of target definitions")
    if len(data) > 10001:
        raise ValueError("Manifest exceeds 10,000 targets")
    available = {name: info for name, info in data.items() if name != "$schema"}
    for name, info in available.items():
        _validate(name, info)
    selected = {str(name).casefold() for name in sites} if sites else None
    if selected:
        missing = selected - {name.casefold() for name in available}
        if missing:
            raise ValueError("Unknown sites: " + ", ".join(sorted(missing)))
    loaded, skipped = {}, {}
    for name, info in available.items():
        if selected and name.casefold() not in selected:
            continue
        reason = policy_reason(name, info)
        if reason:
            skipped[name] = reason
        elif info.get("isNSFW", False) and not include_nsfw:
            skipped[name] = "NSFW target requires --nsfw"
        else:
            loaded[name] = info
    return Manifest(loaded, skipped, source)
