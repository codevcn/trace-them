# Independent implementation review

Review scope: models, detector, transport, engine, manifest policy, email resolver,
canonical reports/exporters, CLI, schema and packaging. Original project is
available in `.work/baseline.zip`; this workspace does not contain Git metadata.

## Findings raised during review

| ID | Priority | Finding | Verification / disposition |
| --- | --- | --- | --- |
| R1 | High | Encoded custom probe paths bypassed auth/registration policy. `/%72egister/%76alidate` passed policy but Requests normalized the wire URL to `/register/validate`. | Fixed. Independent reproducer now rejects the encoded probe; regression suite covers encoded paths and blocked redirect hops. |
| R2 | High | A concise password/login-only form with a generic title, or JSON `{ "status": "error", "message": "Authentication required" }`, was interpreted as FOUND. | Fixed. Independent reproducers now return BLOCKED/UNKNOWN; regression cases pass. |
| R3 | Medium | Gravatar accepted matching JSON from an unexpected final response origin and attributed it to the original API URL. | Fixed. Provider redirects disabled; independent `_interpret` reproducer now returns UNKNOWN for an unexpected response URL. |
| R4 | Medium | CLI advertised SOCKS proxies but distribution lacked PySocks. | Dependency declaration fixed to `requests[socks]`. Lead must rebuild/reinstall final artifacts to verify dependency metadata and installed runtime. |
| R5 | Low | CSV/XLSX fields omitted `Finding.query_time`, retaining less observation data than JSON/TXT and the original CSV output. | Fixed. `query_time` is now an exported column and regression cases pass. |
| R6 | Medium | Non-ASCII usernames made JSON stdout fail on a Windows CP1252 pipe because of `ensure_ascii=False`. | Fixed. JSON stdout uses lossless ASCII escapes; independent CP1252 stream test preserves `nguy\u1ec5n` and exits zero. QA also added a subprocess regression. |

The QA agent independently identified eager redirect-body consumption inside
`requests.Session.send`, before the application body cap. This was fixed with
`_ManualRedirectSession`; the adapter-boundary bounded-body regression passes.

## Independent checks performed

- Read production modules and contract separately from agent summaries.
- Ran no-network reproducers for R1, R2, R3 and dependency availability.
- Ran the then-current full default suite: **168 passed, 1 skipped, 1 failed,
  13 errors**. All failure/error cases were confined to the Apify wrapper which
  was still explicitly under implementation; these are not final suite results.
- Checked that scanner-origin evidence is prefixed as candidate provenance and
  cannot populate cross-platform `association_evidence`.
- Checked literal spreadsheet cells, filename containment, bounded redirects,
  shared request accounting and local-default/offline paths.
- Re-ran the source suite after fixes, excluding stale-artifact validation:
  **196 passed, 1 skipped** (`pytest -q --ignore=tests/test_packaging.py`). The
  skipped test is the opt-in live provider smoke; no live requests were made by
  the reviewer.
- Ran `ruff check trace_them tests devel .actor`: **all checks passed**.
- Reviewed final Apify argument-array/JSON adapter, strict input validation,
  source-based multi-stage Docker definitions, offline-first CI, and README.
  Apify stores the canonical report rather than reducing it to profile URLs.
- Independently re-ran original reproducers for encoded policy, generic login
  page/error envelope, unexpected provider origin and CP1252 output. All passed
  their corrected assertions.

## Source review disposition and remaining validation

No unresolved high/medium source blocker was found after these fixes. This is a
source-level signoff, not certification that every external website is currently
accurate or that email profiles belong to the same person.

The lead must rebuild the final wheel/sdist and re-run installed-artifact checks
after the latest source changes. The reviewer intentionally excluded stale wheel
comparison from the final source run. Docker is unavailable locally and Apify
cloud execution was not performed. Provider live checks recorded by the lead were
negative synthetic/documentation-example cases; positive behavior remains
fixture-tested. No unrelated real email was queried.

The static endpoint policy cannot prove arbitrary API semantics; new providers
still require review. Detection remains heuristic. Requests connect/read timeouts
are inactivity/connect limits rather than a hard total wall-clock deadline:
active I/O cancellation is best effort, especially during DNS or a continuously
trickling response. The lead was asked to describe that limitation accurately.

No production files or tests were modified by the reviewer. Review documents were
the only files written under this role.
