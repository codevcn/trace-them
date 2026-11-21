<p align="center">
  <img src="docs/images/trace-them-logo.svg" alt="Trace Them — Orbital Footprint logo" width="96" height="96">
</p>

# Trace Them

Evidence-aware public profile discovery by exact username or email, with
self-contained Atlassian-styled HTML reports, strict public-source policy, and
a Windows installer bundling global AI Agent skills.

Results distinguish account existence from an association with the input. Trace
Them is an independent MIT-licensed derivative of
[Sherlock](https://github.com/sherlock-project/sherlock); see [NOTICE](NOTICE).

## Install

### Windows Installer (recommended for CLI + AI Agents)

Download `trace-them-setup-<version>.exe` from
[GitHub Releases](https://github.com/codevcn/trace-them/releases) and verify its
checksum against `SHA256SUMS.txt`. The Inno Setup installer packages the
`--onedir` binary, adds `trace-them` to your user `PATH`, registers a standard
Windows Uninstaller, and installs the global `trace-them` skill
([skills/trace-them/SKILL.md](skills/trace-them/SKILL.md)) for:

- **Antigravity**: `~/.gemini/config/skills/trace-them/`
- **Codex**: `~/.codex/skills/trace-them/`
- **Claude Code**: `~/.claude/skills/trace-them/`

### Install from source checkout

Requires Python **3.10–3.14**. The distribution name has not been checked or
published on PyPI. Install the local source:

```console
python -m pip install .
trace-them -v
trace-them --version
python -m trace_them --help
```

To build the Windows `--onedir` bundle and Inno Setup installer from source:

```console
powershell -ExecutionPolicy Bypass -File devel\build_windows.ps1
```

For development:

```console
python -m pip install -e . pytest pytest-xdist ruff build
```

This project also uses Poetry's dev group: `poetry install --with dev` is supported.

## Uninstall

### Windows Installer

Uninstall via **Windows Settings → Apps → Installed apps → Trace Them → Uninstall**,
the **Uninstall Trace Them** Start Menu shortcut, or by running `unins000.exe` in
your installation folder (default `%LocalAppData%\Programs\Trace Them`):

```console
"%LocalAppData%\Programs\Trace Them\unins000.exe"
```

The uninstaller removes:
- The installed `trace-them.exe` binary, `_internal` runtime, and Start Menu shortcuts.
- The Trace Them entry added to your user `PATH`.
- Managed global `trace-them` skill folders containing `.trace-them-managed` under
  `~/.gemini/config/skills/trace-them/`, `~/.codex/skills/trace-them/`, and
  `~/.claude/skills/trace-them/` (other skills and parent folders are untouched).

Your saved HTML reports (default `D:\D-AppData\me-trace-them`) and user config
(`%APPDATA%\trace-them\config.json`) are preserved so you do not lose past
observations and can reinstall cleanly anytime.

### Installed via pip

```console
python -m pip uninstall trace-them
```

## Usage

```console
trace-them find --username example --site GitHub
trace-them find --username first --username second --max-requests 100
trace-them find --username "first{?}last" --site GitHub
trace-them find --email user@example.com
trace-them find --email user@example.com --candidates --candidate-limit 3 --site GitHub --max-requests 20
trace-them find --username example --offline
trace-them find --username example --site GitHub --json result.json --txt --csv --xlsx --output-dir reports
trace-them find --username example --site GitHub --no-html
trace-them config --show
trace-them config --html-dir "D:\D-AppData\me-trace-them"
trace-them config --check-updates off
trace-them --open-html
trace-them --open-html --print-path
trace-them clean report1.html report2.html
trace-them clean --all
trace-them check-update
trace-them update
```

- JSON is always written to stdout; progress is written to stderr. `--quiet`
  suppresses scan progress (release update notices still print to stderr when
  enabled and online). `--json PATH` saves another copy. Each `find` run also
  writes a self-contained HTML visualization report into the configured HTML
  folder (pass `--no-html` to skip or `--open` to launch immediately). TXT/CSV/XLSX
  creation still requires `--txt`, `--csv`, or `--xlsx`.
- Bundled default settings live in `trace_them/resources/config.json` (default
  Windows folder `D:\D-AppData\me-trace-them`, POSIX fallback
  `~/.local/share/trace-them/reports`, and `check_updates: true`). All user
  overrides and cached release-check metadata are stored in the single
  `config.json` (`TRACE_THEM_CONFIG` overrides its path). Use
  `trace-them config --html-dir PATH` to change the HTML folder,
  `trace-them config --check-updates on|off` to toggle automatic release checks,
  `trace-them config --reset` to restore defaults, `trace-them --open-html` to open the
  newest HTML report (with optional `--print-path`), and `trace-them clean` (`FILE...` or `--all`, plus
  optional `--dry-run`) to delete `.html` reports safely inside the folder.
- **Release update checks & self-update:** When online and `check_updates` is
  enabled (default), running CLI subcommands checks GitHub Releases
  (`codevcn/trace-them`, cached inside `config.json` for 12 hours) and prints a
  notice to `stderr` if a newer version is available (even when `--quiet` is
  passed). Use `trace-them check-update` to force a live version check (showing
  current version, latest version, release URL, and update command) and
  `trace-them update` (for packaged Windows `.exe` installs) to download,
  verify SHA-256, and run the latest installer silently. No update checks run
  under `--offline`.
- Exact usernames are the default. The explicit `{?}` pattern expands only to
  `_`, `-`, and `.`. There is no broad fuzzy search.
- `--offline` (alias `--local`) disables **all network**, including resolvers,
  remote manifests, and release update checks. It validates local configuration
  and marks profiles unknown; it does not search cached profiles or manufacture
  negative results.
- Bundled site definitions are used by default. `--manifest PATH_OR_URL` accepts
  legacy Sherlock JSON; remote loading is explicit and budgeted. There are no
  implicit exclusion downloads. NSFW sites require `--nsfw`.
- `--site` is repeatable and case-insensitive. Public-source policy exclusions
  cannot be overridden by selecting a site explicitly.
- `--max-requests` defaults to 500 for the **whole run**: resolver calls, remote
  manifest requests, retries and redirect hops all count. Planned candidate checks
  are shown before scanning. Unqueried work is marked `budget_exhausted`.
- `--workers` defaults to 10 (maximum 32); `--domain-interval` defaults to 0.25s.
  Parent-domain grouping is deliberately conservative. Connect/read timeouts
  default to 5/15s; at most one retry, five redirects, bounded Retry-After waits.
- Set `--proxy URL` explicitly for a proxy. Automatic environment proxies and
  netrc credentials are disabled. No anti-bot bypass is performed.
- Ctrl+C cancels queued work, interrupts retry/throttle waits and checks cancellation
  between response chunks. Active network I/O may delay exit: connect/read timeouts
  are inactivity limits, not a hard wall-clock deadline (DNS and trickling reads
  can take longer). Cancellation exit status is 130. Input/configuration/export errors use exit status 2.
  A completed observation report uses 0 even if individual sources fail; inspect
  finding and resolver statuses. There is no promotional output.

## Email scope and evidence

The first resolver uses the
[Gravatar public Profiles API](https://docs.gravatar.com/rest-api/).
It hashes the provider-normalized email with SHA-256, calls the profile endpoint,
and retains only the relevant public profile metadata and observation evidence.
An optional `GRAVATAR_API_KEY` environment variable supplies a Bearer token.
Limited anonymous access is supported; provider policy/rate limits can change.

A returned profile is a **source-reported association on Gravatar**. It is not
proof of present mailbox ownership. A 404 means no public profile was returned by
this provider; it says nothing about other services, hidden profiles or secondary
email addresses. A generated hash or avatar image alone never counts as a match.

Email lookup returns direct profiles without scanning their usernames elsewhere.
Only `--candidates` enables that extra work. Candidates from the public profile
slug and email local part are de-duplicated and capped at 1–10 (default 5). Local
part separator variants are hypotheses, not verified associations. No recursive
expansion occurs. Email parsing supports unquoted ASCII local parts and IDNA
domains; it preserves local-part case except for Gravatar's documented hashing.

For example, an email-associated Gravatar profile named `example` and a GitHub
account named `example` remain distinct observations. The scanner does not transfer
the Gravatar association to GitHub. Reports keep `origin`, `association`,
`association_evidence`, source URLs and timestamps separately. There are no
unvalidated percentage confidence scores.

The resolver was checked against official documentation and two small live
synthetic/documentation-example lookups returning 404. Positive cases are tested
with fixtures, not unrelated people's email addresses. See
[provider verification](docs/EMAIL_RESOLVER.md).

## Results and exports

Schema version `1.0` contains input, tool version, observation time, manifest
selection/skips, request budget, summary, findings, resolver outcomes, candidates
and warnings. See `trace_them/resources/report.schema.json`.

Finding statuses are `found`, `not_found`, `invalid`, `blocked`, `rate_limited`,
`error`, `unknown`, `unsupported`, `missing_config`, `budget_exhausted`, `cancelled`.
HTTP 429, server failures and access challenges never establish absence.
Successful HTTP/message heuristics are described as heuristics; a public response
does not prove a person's identity. Detection cannot perfectly recognize every
site's login wall or changing error page.

TXT retains the complete canonical evidence report. CSV/XLSX use finding,
resolution and candidate records and preserve provenance/run metadata, including
when there are no matches. CSV formula prefixes are escaped; XLSX cells are
explicit strings without formulas/hyperlinks. Generated filenames are contained,
Windows-safe and carry a hash to avoid normalization collisions. XLSX exports
reject overlong cells rather than silently truncating evidence; use JSON for
large reports.

## Manifest policy and coverage

The original 481 target records remain bundled and compatible. Definitions are
configuration, not proof of live reliability. Authentication/registration
enumeration, breach lookups and verification-cookie probes are excluded. The same
rules apply to renamed/custom/remote definitions. See
[manifest audit](docs/MANIFEST_POLICY.md) for exact counts and limitations.

## Verification and containers

```console
python -m pytest
ruff check trace_them tests devel
python -m build
docker build -t trace-them:local .
docker run --rm trace-them:local --version
docker run --rm trace-them:local find --username example --offline
```

Offline tests deny real network by default. Live tests are opt-in, marked `online`,
and synthetic-only: `python -m pytest -m online --run-online`. Site-wide live sweeps are not
part of default CI. Docker installs this checkout, never a released PyPI copy.
The [Apify wrapper](.actor/README.md) consumes canonical JSON and preserves evidence.

Design/ownership: [implementation contract](docs/IMPLEMENTATION.md).
Review and validation limits are recorded in `docs/REVIEW.md` and
`docs/VALIDATION.md` when available.
