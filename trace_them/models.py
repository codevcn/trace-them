"""Versioned result vocabulary shared by the scanner and identity resolvers."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Status(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    MISSING_CONFIG = "missing_config"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"


@dataclass
class Evidence:
    kind: str
    source: str
    detail: str
    observed_at: str = field(default_factory=utc_now)


@dataclass
class Candidate:
    username: str
    origin: str = "input"
    evidence: list[Evidence] = field(default_factory=list)
    platform: str | None = None


@dataclass
class Finding:
    platform: str
    username: str
    profile_url: str
    status: Status
    reason: str
    observed_at: str = field(default_factory=utc_now)
    http_status: int | None = None
    evidence: list[Evidence] = field(default_factory=list)
    association: str = "unverified"
    association_evidence: list[Evidence] = field(default_factory=list)
    identifier: str | None = None
    query_time: float | None = None
    origin: str = "input"

    def to_dict(self) -> dict:
        value = asdict(self)
        value["status"] = self.status.value
        return value
