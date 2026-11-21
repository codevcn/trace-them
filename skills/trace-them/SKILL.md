---
name: trace-them
description: Evidence-aware public profile discovery by exact username or email using the trace-them CLI, plus managing HTML visualization reports, configuration, and updates. Use whenever the user asks to check where a username/handle exists online, resolve an email via public Gravatar profile API, inspect/open/clean HTML OSINT reports, or manage trace-them settings and updates.
---

# Trace Them CLI Skill

Operate `trace-them` reliably as an AI Agent. All structured outputs are written as JSON on `stdout`, while progress logs and release-update notices are written to `stderr`.

## Core Rules for Agents

1. **Always parse `stdout` as JSON; keep `stderr` separate.**
   - Pass `--quiet` during automated scans to suppress scan progress on `stderr`.
   - Note that if `check_updates` is enabled and a newer release exists, a short notice still appears on `stderr` — never treat `stderr` as JSON.
2. **Never upgrade profile existence into identity proof.**
   - `status: "found"` only means a public endpoint responded positively according to heuristics.
   - `association: "unverified"` means handle reuse across sites is **not** proof the same person owns those accounts.
   - `association: "source_reported"` appears only on direct provider matches (e.g., Gravatar email hash resolution) and remains scoped to that provider.
   - Treat `blocked`, `rate_limited`, `error`, `unknown`, `budget_exhausted`, and `cancelled` honestly as inconclusive — never report them as "account does not exist".
3. **Keep request budgets bounded.**
   - Default `--max-requests` is `500` shared across resolver, redirects, retries, and all sites/candidates.
   - When targeting specific platforms or doing quick checks, pass `--site <Name>` (repeatable, case-insensitive) and an explicit `--max-requests`.
4. **Control HTML report side effects intentionally.**
   - By default, `trace-them find` writes an Atlassian-styled HTML report to the configured folder (`D:\D-AppData\me-trace-them` on Windows by default).
   - Pass `--no-html` when running purely programmatic lookups that do not need a saved HTML file.
   - Pass `--open` (or run `trace-them --open-html` afterward) when the user wants to view the report visually in a browser.
5. **Respect privacy and offline constraints.**
   - Only scan `--candidates` from an email when the user explicitly wants inferred username expansion (`--candidates`, capped by `--candidate-limit 1..10`).
   - Use `--offline` whenever network calls must be disabled.

## Command Reference

### 1. Discover Profiles (`find`)

```bash
# Scan specific platforms for an exact username (JSON on stdout + HTML saved)
trace-them find --username <handle> --site GitHub --site GitLab --quiet

# Scan across default 451 targets (or add --nsfw for +19 NSFW targets)
trace-them find --username <handle> --max-requests 250 --quiet

# Explicit pattern expansion ({?} expands strictly to _, -, .)
trace-them find --username "first{?}last" --site GitHub --quiet

# Direct email lookup (Gravatar Public Profiles API v3; does not scan other sites)
trace-them find --email user@example.com --quiet

# Email + bounded nonrecursive candidate scan
trace-them find --email user@example.com --candidates --candidate-limit 3 --site GitHub --max-requests 20 --quiet

# Headless JSON-only scan (skip HTML file) or open HTML immediately
trace-them find --username <handle> --site GitHub --no-html --quiet
trace-them find --username <handle> --site GitHub --open --quiet

# Export extra formats alongside JSON/HTML
trace-them find --username <handle> --site GitHub --json out.json --csv --xlsx --txt --output-dir reports --quiet
```

### 2. Inspect & Open HTML Reports (`--open-html`)

```bash
# Open the newest HTML report in the default browser
trace-them --open-html

# Get the newest HTML file path without launching a browser
trace-them --open-html --print-path
```

### 3. Clean HTML Reports (`clean`)

```bash
# Preview what would be deleted without deleting
trace-them clean --all --dry-run

# Delete one or multiple specific HTML files
trace-them clean report1.html report2.html

# Delete all .html files in the configured HTML folder (non-HTML files are untouched)
trace-them clean --all
```

### 4. Configure Settings (`config`)

```bash
# Show current config file path, html_output_dir, check_updates, and cached release metadata
trace-them config --show

# Change HTML report storage directory
trace-them config --html-dir "D:\MyReports\trace-them"

# Toggle automatic release checks (default: on)
trace-them config --check-updates off
trace-them config --check-updates on

# Restore bundled defaults
trace-them config --reset
```

### 5. Check Version & Updates (`-v`, `check-update`, `update`)

```bash
# Print the installed Trace Them version
trace-them -v
trace-them --version

# Force a live version check against GitHub Releases
trace-them check-update

# Download, verify SHA-256, and run the Windows installer if a newer release exists
trace-them update
```

## Interpreting JSON Output

Inspect these fields from `stdout`:
- `summary`: counts per `Status` (`found`, `not_found`, `invalid`, `blocked`, `rate_limited`, `error`, `unknown`, `unsupported`, `missing_config`, `budget_exhausted`, `cancelled`).
- `findings[]`: each item contains `platform`, `username`, `profile_url`, `status`, `reason`, `association`, `origin`, `http_status`, `query_time`, `evidence`, `association_evidence`.
- `resolutions[]`: provider-level email lookup outcome (e.g., `Gravatar`).
- `candidates[]`: generated handles and their provenance (`input`, `explicit_pattern`, `public_profile_username`, `email_local_part`).
- `manifest.skipped`: targets excluded by public-source policy or missing `--nsfw`.
- `request_budget`: `limit`, `used`, `remaining`.
