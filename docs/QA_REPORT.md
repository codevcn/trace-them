# Independent QA report

Status: **passed**. Independent final verification completed after the last
production fixes and artifact rebuild. No unresolved QA blocker remains.

## Scope and isolation

QA owns `tests/`, `pytest.ini`, this report and `QA_PLAN.md`. Production fixes
were handed to the Lead/Developer. The tests use fabricated identifiers and
reserved example addresses. Default test fixtures reject socket connections
and unmocked HTTP sends. A marked synthetic Gravatar smoke requires explicit
`--run-online` and was not executed by QA.

The baseline was reviewed statically. Upstream test intent was migrated to
Trace Them interfaces: manifest/schema checks, known-positive and negative
probe cases, username syntax, Unicode failures, NSFW handling, wildcard
expansion and CLI version/usage. Unbounded live target sweeps were replaced by
offline full-manifest accounting and deterministic HTTP fixtures.

## Executed checks

- `.venv/Scripts/python -m pytest -q`: **198 passed, 1 skipped**, in 5.00 s.
- `.venv/Scripts/python -m ruff check tests`: passed.
- The artifact assertion initially detected a stale pre-fix wheel. After the
  Lead rebuilt it, the final wheel passed byte-for-byte runtime source equality,
  metadata, entry-point and bundled-resource checks.
- The sole skipped test is the explicit opt-in live Gravatar smoke. All default
  HTTP behavior tests use mocks and the network-deny guard.

Tests cover scanner outcomes, transient failures, challenge/login pages,
Unicode, regex filtering, manifest immutability, request budget across threads,
retries and redirects, domain pacing with a fake clock, cancellation, session
closure, cross-origin credential stripping and response-size limits.

Email tests cover normalization, bounded inferred candidates, source-scoped
profile associations, mismatched hashes and URLs, provider errors, offline,
budget exhaustion, and no automatic username scan. Export tests verify JSON
schema, TXT provenance, CSV/XLSX evidence, literal spreadsheet cells, contained
filenames and distinct origins for identical usernames from different sources.

Apify tests mock the full input → CLI → dataset subprocess flow, confirm literal
argument handling and exact canonical JSON preservation, and ensure failed
scans do not push data. Packaging tests inspect metadata, CLI entry point and
all required runtime resources, reject the legacy package in the wheel, and
compare the artifact's runtime bytes with current source.

Additional regressions verify query timing survives CSV/XLSX exports, email-only
lookups reject scan-specific flags that would otherwise be ignored, and a
subprocess using Windows `cp1252` stdout losslessly round-trips a non-ASCII
username through JSON without making offline requests.

## Findings addressed during collaboration

1. Candidate-origin evidence was initially stored as association evidence.
   Scanner findings now retain origin evidence while association stays
   unverified and association evidence stays empty.
2. Spreadsheet origin labels were initially joined by username alone. Direct
   source findings and inferred findings now carry their own origins.
3. Real `requests.Session.send` eagerly read redirect response bodies while
   preparing `_next`, bypassing the intended body cap. QA reproduced this at
   the HTTP adapter boundary with a 3 MiB fixture. The Developer disabled
   requests' implicit redirect preparation; the bounded-read regression passes.
4. Reviewer findings received independent regressions for encoded auth paths,
   redirect policy enforcement, provider source integrity, soft transient
   errors, password forms and authentication error JSON envelopes.
5. The Reviewer reproduced Unicode output failure under Windows legacy stdout
   encoding. The Lead changed terminal JSON escaping and diagnostic encoding;
   QA's `PYTHONIOENCODING=cp1252` subprocess regression passes.

## Limits

- No unrelated person's email was used and no broad website scan was run.
- All 481 legacy target records are accounted for statically; this does not
  establish live accuracy across all websites or geographic regions.
- Apify cloud behavior is covered by mocked subprocess integration, not an
  actual cloud deployment.
- The suite uses `.venv` CPython 3.11.15 (the global interpreter is 3.12.0).
  Runtime compatibility on every declared Python/OS
  combination depends on the configured CI matrix.
- Docker and installed-wheel runtime results are reported separately by the
  Lead; QA does not label unavailable environments as tested.
