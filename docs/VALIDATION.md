# Trace Them 0.1.0 — implementation and validation

Completed in the project workspace on 2026-11-17 Asia/Saigon.

## Team and disposition

- Lead: architecture, integration, CLI/resolvers/reporting, rebrand, packaging,
  Docker/CI/docs, independent artifact installation and final checks.
- Developer agent: scanner/detector/transport/manifest and public-source audit;
  subsequently the Apify adapter and redirect-body fix.
- QA agent: independent offline regression design and execution, export and
  subprocess checks, artifact-source equality. [QA report](QA_REPORT.md).
- Reviewer agent: independent design/source review and reproducers; all raised
  high/medium source findings were resolved. [Review](REVIEW.md).

This workspace had no `.git`. Its 56 original files and SHA-256 baseline are
preserved in `.work/baseline.zip` and `.work/baseline-sha256.json`. Original runtime
source is retained outside the active tree in `.work/upstream-sherlock`.
`.work/change-inventory.json` records changed original and new source paths.
No repository was initialized, no commits or PRs created, nothing pushed,
published or deployed. The distribution name's registry availability is unknown.

## Actual executed verification

| Check | Result |
|---|---|
| Final full default pytest suite, lead | **198 passed, 1 skipped**, 5.42s |
| Independent final QA run | **198 passed, 1 skipped**, 5.00s |
| `ruff check trace_them tests devel .actor` | Passed |
| `python -m build --no-isolation` | Wheel and sdist built successfully |
| Wheel metadata/resources and every runtime file compared with final source | Passed |
| Final wheel installed into separate `.work/wheel-env` | Passed |
| Installed `trace-them --version` | `Trace Them 0.1.0` |
| Installed username/email/candidate offline paths with sockets denied | Passed, zero requests |
| Installed JSON schema validation and TXT/CSV/XLSX exports | Passed |
| Non-ASCII username via CP1252 subprocess stdout | Passed, lossless JSON round-trip |
| Python 3.10 AST grammar check | Passed; not a 3.10 runtime test |
| Gravatar negative end-to-end CLI smoke | Source-scoped 404, exactly one request |
| Docker runtime / actual Apify platform | Not executed; Docker unavailable, no cloud deployment |

Actual test interpreter: **CPython 3.11.15** in `.venv`; global Python is 3.12.0.
The configured CI matrix covers Python 3.10–3.14 on Linux, Windows and macOS, but
that matrix was not executed locally. The skipped test requires `--run-online`.
Default tests deny sockets/unmocked HTTP and use fabricated data.

The installed-wheel smoke ran from `.work/wheel-smoke`, confirmed imports came
from the separate environment's site-packages rather than the source tree,
confirmed PySocks was installed, and compared packaged runtime bytes with source.
Final test XML is `.work/final-tests.xml`; CLI smoke reports and exports are under
`.work/` and `.work/wheel-smoke/exports-final/`.

## Delivered behavior

- `trace-them find --username ...` and `python -m trace_them`.
- Local default manifest with explicit remote loading; offline has no hidden
  update/exclusion/resolver traffic.
- Distinct observation statuses and source/timestamp/reason evidence.
- Shared request budget, bounded retries/redirects, parent-domain pacing,
  credential stripping, best-effort cancellation and 2 MiB decompressed body cap.
- JSON schema 1.0 plus provenance-preserving TXT/CSV/XLSX, safe filenames and
  literal spreadsheet cells. No promotional output.
- Gravatar public email resolver, direct source-scoped profiles and opt-in,
  bounded nonrecursive candidate scans. No identity upgrade through shared names.
- 481 retained legacy records: 11 policy exclusions, 470 eligible including NSFW,
  451 default. [Full policy and limitations](MANIFEST_POLICY.md).
- Docker builds local source; Apify consumes/pushes canonical JSON; CI defaults
  to offline checks and does not write to upstream repositories.

## Review findings fixed

Candidate evidence leaking into association fields; username-only export origin
joins; encoded restricted endpoints; auth redirects; generic login/error pages
misreported as found; provider response-origin attribution; eager redirect body
consumption inside Requests; missing SOCKS dependency; omitted export timings;
and Windows legacy-encoding JSON failures all received fixes and regression checks.

## Material limits

Detection is heuristic; all 481 external websites have not been live-certified.
Static URL policy cannot prove arbitrary API semantics. New sources require
review. HTTP connect/read limits are not a hard total request deadline; active
I/O, DNS or trickling responses may delay cancellation.

Gravatar live verification used only synthetic/documentation-example addresses
and returned negative results. Positive and error cases were fixture-tested;
no unrelated person's real email was used. A provider association is not proof of
current mailbox ownership. A provider 404 is not global account absence.
See [provider verification](EMAIL_RESOLVER.md) for sources and exact semantics.

Dockerfiles and Apify were reviewed and adapter behavior tested offline, but
successful container builds and cloud storage execution are not claimed.

## Build artifacts

- `dist/trace_them-0.1.0-py3-none-any.whl`
  SHA-256 `a2d788aae888f7497ab7e2c3c1ebf5d3269f46cf7b00be714bf81749b9829891`
- `dist/trace_them-0.1.0.tar.gz`
  SHA-256 `549bc32ca4f61d58a399ac644359807eeca9dcb5672a7e9d4170da9d2bf3058b`
