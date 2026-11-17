"""Source-scoped email resolution through the public Gravatar Profiles API.

The source association describes the API response; it is not proof of mailbox
ownership. Neither a profile slug nor a matching username transfers that
association to another service.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import requests

from trace_them.models import Candidate, Evidence, Finding, Status
from trace_them.transport import BudgetExceeded, OfflineError, RetryDeferred, ScanCancelled


@dataclass
class Resolution:
    provider: str
    status: Status
    reason: str
    findings: list[Finding] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self):
        from dataclasses import asdict

        return {
            "provider": self.provider,
            "status": self.status.value,
            "reason": self.reason,
            "findings": [finding.to_dict() for finding in self.findings],
            "candidates": [asdict(candidate) for candidate in self.candidates],
            "evidence": [asdict(item) for item in self.evidence],
        }


def validate_email(value: str) -> str:
    """Accept ordinary unquoted addresses; preserve the local part verbatim."""
    value = value.strip()
    if len(value) > 254 or value.count("@") != 1:
        raise ValueError("Provide one valid email address (unquoted local part).")
    local, domain = value.rsplit("@", 1)
    if (
        not 1 <= len(local) <= 64
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise ValueError("Unsupported or invalid email local part.")
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Invalid email domain.") from exc
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("Invalid email domain.")
    normalized = f"{local}@{domain}"
    if len(normalized) > 254:
        raise ValueError("Email address is too long.")
    return normalized


def email_candidates(email: str, limit: int = 5) -> list[Candidate]:
    """Generate a small, explicit set of hypotheses, never identity assertions."""
    if not 1 <= limit <= 10:
        raise ValueError("Candidate limit must be between 1 and 10.")
    local = validate_email(email).rsplit("@", 1)[0]
    values = [local]
    if re.search(r"[._-]", local):
        values += [re.sub(r"[._-]+", separator, local) for separator in ("", "_", "-", ".")]
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(Candidate(
            username=value,
            origin="email_local_part",
            evidence=[Evidence(
                kind="inferred", source="input:email",
                detail="Hypothesis derived from email local part; no account association established.",
            )],
        ))
        if len(result) >= limit:
            break
    return result


class GravatarResolver:
    """GET a public profile by the documented SHA256 email identifier."""

    provider = "Gravatar"

    def __init__(self, transport, api_key: str | None = None):
        self.transport = transport
        self.api_key = api_key

    def resolve(self, email: str) -> Resolution:
        email = validate_email(email)
        digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        url = f"https://api.gravatar.com/v3/profiles/{digest}"
        headers = {"Accept": "application/json", "User-Agent": "TraceThem/0.1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self.transport.request("GET", url, headers=headers, allow_redirects=False)
        except OfflineError:
            return Resolution(self.provider, Status.UNSUPPORTED, "Email resolution disabled offline.")
        except BudgetExceeded:
            return Resolution(self.provider, Status.BUDGET_EXHAUSTED, "Request budget exhausted.")
        except ScanCancelled:
            return Resolution(self.provider, Status.CANCELLED, "Resolution cancelled.")
        except RetryDeferred as error:
            response = error.response
            code = response.status_code if response is not None else None
            if response is not None:
                response.close()
            return Resolution(self.provider, Status.RATE_LIMITED if code == 429 else Status.ERROR,
                              "Provider requested a longer retry wait.")
        except (requests.RequestException, UnicodeError):
            return Resolution(self.provider, Status.ERROR, "Provider request failed; association unknown.")

        try:
            return self._interpret(response, digest, url)
        finally:
            response.close()

    def _interpret(self, response, digest, url):
        if response.url != url:
            return Resolution(self.provider, Status.UNKNOWN,
                              "Response did not originate from the requested provider endpoint.",
                              evidence=[Evidence("unexpected_source", response.url or "unknown",
                                                 "Provider endpoint origin was not established.")])

        evidence = [Evidence(
            kind="provider_response", source=url,
            detail=f"Gravatar public Profiles API returned HTTP {response.status_code}.",
        )]
        code = response.status_code
        if code == 404:
            return Resolution(self.provider, Status.NOT_FOUND,
                              "No public Gravatar profile returned; other services and private profiles are unknown.",
                              evidence=evidence)
        if code == 429 or (code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"):
            return Resolution(self.provider, Status.RATE_LIMITED, "Provider rate limit reached.", evidence=evidence)
        if code == 401:
            return Resolution(self.provider, Status.MISSING_CONFIG,
                              "Provider requires a valid GRAVATAR_API_KEY for this request.", evidence=evidence)
        if code in (403, 451):
            return Resolution(self.provider, Status.BLOCKED, "Provider denied this request.", evidence=evidence)
        if code >= 500:
            return Resolution(self.provider, Status.ERROR, "Provider server error.", evidence=evidence)
        if code != 200:
            return Resolution(self.provider, Status.UNKNOWN, "Unexpected provider response.", evidence=evidence)
        try:
            data = response.json()
        except (ValueError, requests.RequestException):
            return Resolution(self.provider, Status.ERROR, "Provider returned invalid JSON.", evidence=evidence)
        if not isinstance(data, dict):
            return Resolution(self.provider, Status.UNKNOWN, "Provider profile has an unexpected shape.", evidence=evidence)
        profile_url = data.get("profile_url")
        if not isinstance(profile_url, str) or not self._valid_profile_url(profile_url):
            return Resolution(self.provider, Status.UNKNOWN, "Response lacks a valid public Gravatar profile URL.", evidence=evidence)
        if data.get("hash") != digest:
            return Resolution(self.provider, Status.UNKNOWN, "Response identifier does not match the requested email hash.", evidence=evidence)
        slug = unquote(urlsplit(profile_url).path.strip("/"))
        association = Evidence(
            kind="source_reported_email_association", source=url,
            detail="Gravatar returned this public profile for the supplied email's SHA256 identifier. "
                   "Association is scoped to Gravatar; present mailbox ownership is not verified.",
        )
        finding = Finding(
            platform=self.provider, username=slug, profile_url=profile_url,
            status=Status.FOUND, reason="Public profile returned for the requested email hash.",
            http_status=code, evidence=evidence, association="source_reported",
            association_evidence=[association], identifier=digest,
            origin="public_email_resolution",
        )
        candidate = Candidate(
            username=slug, origin="public_profile_username", platform=self.provider,
            evidence=[Evidence(kind="source_username", source=profile_url,
                               detail="Public profile slug; reuse elsewhere is an unverified hypothesis.")],
        )
        return Resolution(self.provider, Status.FOUND, "Public Gravatar profile resolved.",
                          findings=[finding], candidates=[candidate], evidence=evidence)

    @staticmethod
    def _valid_profile_url(value: str) -> bool:
        try:
            parts = urlsplit(value)
            return (
                parts.scheme == "https" and parts.netloc in ("gravatar.com", "www.gravatar.com")
                and bool(parts.path.strip("/")) and "/" not in parts.path.strip("/")
                and not parts.query and not parts.fragment
            )
        except ValueError:
            return False
