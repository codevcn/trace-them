# Trace Them implementation contract

Scope: Python >=3.10 CLI; public profiles, username and email inputs. No server/UI,
authentication enumeration, recursive identity expansion, publication or deployment.
Original files and hashes are preserved in `.work/baseline.zip` and
`.work/baseline-sha256.json` because this workspace has no Git metadata.

## Ownership

- Developer: `trace_them/models.py`, `detector.py`, `transport.py`, `engine.py`,
  `manifest.py`, and copied `trace_them/resources/data*` plus policy data/audit docs.
- Lead: CLI, resolvers, reporting, packaging, Docker/Apify/CI, general docs.
- QA: `tests/` and pytest configuration. No production code edits without handoff.
- Reviewer: read-only design and implementation review; findings with evidence.

## Shared interfaces (version 1.0)

Use dataclasses and string enums. `utc_now()` returns an ISO UTC timestamp.
`Status`: FOUND, NOT_FOUND, INVALID, BLOCKED, RATE_LIMITED, ERROR, UNKNOWN,
UNSUPPORTED, MISSING_CONFIG, BUDGET_EXHAUSTED, CANCELLED (serialized lowercase snake_case).
`Evidence(kind, source, detail, observed_at=utc_now())`.
`Candidate(username, origin='input', evidence=list[Evidence], platform=None)`.
`Finding(platform, username, profile_url, status, reason, observed_at=utc_now(),
http_status=None, evidence=list[Evidence], association='unverified',
association_evidence=list[Evidence], identifier=None, query_time=None, origin='input')`.
`Finding.to_dict()` serializes enums/evidence without confidence percentages.

`RequestBudget(limit=500)` with thread-safe `used`, `remaining`, `consume()`.
Every actual HTTP request, retry and redirect consumes the shared run budget.
`HTTPTransport(budget, timeout=(5,15), retries=1, per_domain_interval=0.25,
max_retry_after=10, offline=False, cancel_event=None)` is a context manager.
`request(method,url,**kwargs)` returns requests.Response; raises typed exceptions
for offline, exhausted budget and cancellation; `close()` closes owned resources.
Use explicit bounded redirects, cancellable waits, no hidden urllib3 retries.
Exceptions exported: OfflineError, BudgetExceeded, ScanCancelled, RetryDeferred.

`load_manifest(path=None, *, transport=None, offline=False, include_nsfw=False,
sites=None)` -> `Manifest(sites:dict, skipped:dict, source:str)`.
Bundled legacy-format manifest is default. Explicit remote manifests use transport.
No automatic update/exclusion downloads. Validate shape, patterns, methods, URLs.
Exclude auth/registration enumeration and non-profile lookup targets by policy;
explicit site selection cannot override policy. Retain original records for audit.
`detect(response, site_info)` -> `(Status, reason)`; handle error/block pages before
legacy errorType logic and preserve unknown rather than inventing absence.

`Scanner(transport, max_workers=10)`; `scan(username, sites:dict,
*, candidate=None)` -> `list[Finding]`. Profile existence evidence is separate
from identity association. Scanner must never upgrade email linkage by same handle.
Regex-invalid handles consume no budget. Do not mutate caller's manifest.

## Lead integration

`trace_them find --username ...` or `--email ...`; JSON stdout, human progress stderr.
`--offline` never uses network and emits unknown/unsupported rather than fake absence.
One shared budget covers resolver, manifest fetch and all scans.
Email resolver returns source-specific direct profiles and possible candidates.
Only explicit `--candidates` scans email-derived handles; bounded and nonrecursive.
Provider-scoped direct email links never transfer to another platform.
All exports retain origin, association and evidence. TXT is human-readable evidence,
not a bare list implying ownership. CSV/XLSX cells are literal text.

## Acceptance

Offline tests are default and deny network. Fixtures cover HTTP outcomes, evidence
scope, budget/redirect/retry/cancellation, output safety, CLI and manifest policy.
Live tests are opt-in and only use documented synthetic inputs. Build wheel/sdist,
test installed CLI outside source package path, and execute Docker if available.
Report unavailable runtime checks honestly. Reviewer findings must be resolved or
explicitly documented. No claim of registry name availability or identity proof.
