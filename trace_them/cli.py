"""Trace Them command line: explicit inputs, bounded work, JSON-first output, and HTML reports."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

import requests

from trace_them import __version__
from trace_them.config import (
    get_html_output_dir,
    load_config,
    reset_config,
    set_config,
)
from trace_them.engine import Scanner
from trace_them.html_report import delete_html_files, find_latest_html, open_html_file, write_html
from trace_them.manifest import load_manifest
from trace_them.models import Candidate
from trace_them.reporting import make_report, write_json, write_reports
from trace_them.resolvers import GravatarResolver, email_candidates, validate_email
from trace_them.transport import (
    BudgetExceeded, HTTPTransport, OfflineError, RequestBudget, RetryDeferred, ScanCancelled,
)
from trace_them.updater import check_for_update, format_update_notice, maybe_notify_update, run_self_update


def _integer(minimum, maximum=None):
    def parse(value):
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Expected an integer.") from exc
        if number < minimum or (maximum is not None and number > maximum):
            raise argparse.ArgumentTypeError(f"Expected {minimum}..{maximum or 'unbounded'}.")
        return number
    return parse


def _number(value, *, zero=False):
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a finite number.") from exc
    if not math.isfinite(number) or number < 0 or (not zero and number == 0):
        raise argparse.ArgumentTypeError("Expected a finite positive number." if not zero
                                         else "Expected a finite nonnegative number.")
    return number


def _parse_toggle(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("on", "true", "1", "yes"):
        return True
    if normalized in ("off", "false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("Expected one of: on, off, true, false, 1, 0.")


def _clean_dir_arg(value: str, flag: str) -> Path:
    if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{flag} must be a nonempty path without control characters")
    return Path(value.strip()).expanduser().resolve()


def _progress(message: str, *, quiet: bool) -> None:
    if not quiet:
        encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
        print(message.encode(encoding, "backslashreplace").decode(encoding), file=sys.stderr)


def _parser():
    parser = argparse.ArgumentParser(
        prog="trace-them",
        description=(
            "Discover public profiles with explicit evidence, write Atlassian-styled HTML "
            "reports to the configured folder, and manage settings and updates."
        ),
        epilog=(
            "Examples:\n"
            "  trace-them find --username example --site GitHub\n"
            "  trace-them find --email user@example.com --candidates --open\n"
            "  trace-them config --html-dir \"D:\\D-AppData\\me-trace-them\"\n"
            "  trace-them config --check-updates off\n"
            "  trace-them --open-html\n"
            "  trace-them --open-html --print-path\n"
            "  trace-them clean report1.html report2.html\n"
            "  trace-them clean --all\n"
            "  trace-them check-update\n"
            "  trace-them update"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"Trace Them {__version__}")
    parser.add_argument("--open-html", action="store_true", help="Open the newest HTML report in the configured folder.")
    parser.add_argument("--html-dir", default=None, metavar="PATH", help="Override the configured HTML folder when using --open-html.")
    parser.add_argument("--print-path", action="store_true", help="With --open-html, print the newest HTML report path without launching a browser.")
    parser.add_argument("--quiet", action="store_true", help="Suppress status messages on stderr when using --open-html.")
    commands = parser.add_subparsers(dest="command", required=False)

    find = commands.add_parser(
        "find",
        help="Check exact usernames or resolve an email; print JSON to stdout and save an HTML report.",
        description=(
            "Check exact usernames or resolve an email through public sources. "
            "Canonical JSON is printed to stdout, and an HTML visualization report is "
            "created in the configured HTML folder unless --no-html is passed."
        ),
    )
    identities = find.add_mutually_exclusive_group(required=True)
    identities.add_argument("--username", action="append", help="Exact username; repeat for multiple usernames.")
    identities.add_argument("--email", help="Email for source-scoped public profile resolution.")
    find.add_argument("--candidates", action="store_true", help="Explicitly scan hypotheses derived from an email.")
    find.add_argument("--candidate-limit", type=_integer(1, 10), default=5)
    find.add_argument("--site", action="append", default=[], help="Select a platform; repeatable, case-insensitive.")
    find.add_argument("--manifest", help="Legacy-compatible local JSON manifest or explicit HTTP(S) URL.")
    find.add_argument("--offline", "--local", action="store_true", help="Disable all network; use local definitions only.")
    find.add_argument("--nsfw", action="store_true", help="Include NSFW public profile targets.")
    find.add_argument("--proxy", help="Explicit HTTP(S)/SOCKS proxy; environment proxies are not used.")
    find.add_argument("--max-requests", type=_integer(0), default=500, help="Shared wire-request budget, including retries/redirects.")
    find.add_argument("--workers", type=_integer(1, 32), default=10)
    find.add_argument("--timeout", type=_number, default=15, help="Read timeout in seconds.")
    find.add_argument("--connect-timeout", type=_number, default=5)
    find.add_argument("--retries", type=_integer(0, 5), default=1)
    find.add_argument("--domain-interval", type=lambda v: _number(v, zero=True), default=0.25)
    find.add_argument("--max-retry-after", type=lambda v: _number(v, zero=True), default=10)
    find.add_argument("--json", nargs="?", const="-", default="-", metavar="PATH", help="Also save canonical JSON to PATH; stdout is always JSON.")
    find.add_argument("--txt", action="store_true")
    find.add_argument("--csv", action="store_true")
    find.add_argument("--xlsx", action="store_true")
    find.add_argument("--output-dir", default=".", help="Directory for requested TXT/CSV/XLSX exports.")
    find.add_argument("--no-html", action="store_true", help="Disable automatic HTML visualization report generation.")
    find.add_argument("--html-dir", metavar="PATH", help="Override the configured HTML report folder for this run.")
    find.add_argument("--open", action="store_true", help="Open the generated HTML report in the default browser.")
    find.add_argument("--quiet", action="store_true", help="Suppress scan progress on stderr (release notices still print).")

    config_cmd = commands.add_parser(
        "config",
        help="Inspect or update HTML folder path and automatic update-check settings.",
        description=(
            "Inspect or update persistent Trace Them settings stored in config.json, "
            "including the HTML report folder path and automatic release-check behavior."
        ),
    )
    config_cmd.add_argument("--show", action="store_true", help="Show the active configuration (default).")
    config_cmd.add_argument("--html-dir", metavar="PATH", help="Change and persist the folder path for HTML reports.")
    config_cmd.add_argument("--check-updates", type=_parse_toggle, metavar="{on,off}", help="Enable or disable automatic release checks on CLI runs (default: on).")
    config_cmd.add_argument("--reset", action="store_true", help="Reset configuration back to bundled defaults.")
    config_cmd.add_argument("--quiet", action="store_true", help="Suppress status messages on stderr.")

    clean_cmd = commands.add_parser(
        "clean",
        help="Delete one, multiple, or all HTML reports in the configured folder.",
        description=(
            "Delete one or more specified .html reports, or delete all .html reports "
            "inside the configured HTML folder. Non-HTML files and files outside the "
            "target folder are never removed."
        ),
    )
    clean_cmd.add_argument("files", nargs="*", metavar="FILE", help="One or more HTML filenames (or paths inside the folder) to delete.")
    clean_cmd.add_argument("--all", action="store_true", help="Delete all .html files inside the configured HTML folder.")
    clean_cmd.add_argument("--html-dir", metavar="PATH", help="Clean PATH instead of the configured HTML folder.")
    clean_cmd.add_argument("--dry-run", action="store_true", help="List HTML files that would be deleted without removing them.")
    clean_cmd.add_argument("--quiet", action="store_true", help="Suppress status messages on stderr.")

    check_update_cmd = commands.add_parser(
        "check-update",
        help="Check whether a newer Trace Them release is available on GitHub.",
        description=(
            "Check GitHub Releases to see whether the installed Trace Them version "
            "needs updating, printing version details, release URL, and update command."
        ),
    )
    check_update_cmd.add_argument("--proxy", help="Explicit HTTP(S)/SOCKS proxy; environment proxies are not used.")
    check_update_cmd.add_argument("--timeout", type=_number, default=10, help="Request timeout in seconds.")
    check_update_cmd.add_argument("--offline", "--local", action="store_true", help="Disable all network access.")
    check_update_cmd.add_argument("--quiet", action="store_true", help="Suppress human summary on stderr.")

    update_cmd = commands.add_parser(
        "update",
        help="Download, verify, and install the latest Trace Them release if available.",
        description=(
            "Fetch the latest Trace Them release from GitHub, verify its SHA-256 checksum, "
            "and launch the Windows installer when a newer version is available."
        ),
    )
    update_cmd.add_argument("--proxy", help="Explicit HTTP(S)/SOCKS proxy; environment proxies are not used.")
    update_cmd.add_argument("--timeout", type=_number, default=30, help="Request timeout in seconds.")
    update_cmd.add_argument("--offline", "--local", action="store_true", help="Disable all network access.")
    update_cmd.add_argument("--dry-run", action="store_true", help="Inspect the available update asset without downloading or installing.")
    update_cmd.add_argument("--quiet", action="store_true", help="Suppress status messages on stderr.")

    return parser


def _run_find(parser, args) -> int:
    if args.candidates and args.email is None:
        parser.error("--candidates requires --email.")
    if args.email and not args.candidates and (args.site or args.manifest or args.nsfw):
        parser.error("--site, --manifest and --nsfw apply to username scans; add --candidates for email-derived scans.")
    if args.open and args.no_html:
        parser.error("--open cannot be used with --no-html.")
    if args.username and any(not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)
                             for value in args.username):
        parser.error("Usernames must be nonempty and contain no control characters.")
    try:
        if args.email is not None:
            args.email = validate_email(args.email)
    except ValueError as error:
        parser.error(str(error))

    budget = RequestBudget(args.max_requests)
    findings, resolutions, candidates, warnings = [], [], [], []
    manifest = None
    try:
        html_target_dir = None
        if not args.no_html:
            html_target_dir = (
                _clean_dir_arg(args.html_dir, "--html-dir")
                if args.html_dir is not None
                else get_html_output_dir()
            )

        with HTTPTransport(budget, timeout=(args.connect_timeout, args.timeout),
                           retries=args.retries, per_domain_interval=args.domain_interval,
                           max_retry_after=args.max_retry_after, offline=args.offline,
                           proxy=args.proxy) as transport:
            # A plain email lookup needs no username manifest or scanner.
            if args.username or args.candidates:
                manifest = load_manifest(args.manifest, transport=transport, offline=args.offline,
                                         include_nsfw=args.nsfw, sites=args.site)
                if manifest.skipped:
                    warnings.append(f"{len(manifest.skipped)} selected/default targets skipped; see manifest.skipped.")
                if not manifest.sites:
                    warnings.append("No eligible public-profile targets selected.")
            if args.email:
                _progress("Resolving public Gravatar profile; associations remain source-scoped.", quiet=args.quiet)
                resolution = GravatarResolver(transport, os.environ.get("GRAVATAR_API_KEY")).resolve(args.email)
                resolutions.append(resolution)
                findings.extend(resolution.findings)
                if args.candidates:
                    offered = resolution.candidates + email_candidates(args.email, args.candidate_limit)
                    seen = set()
                    for candidate in offered:
                        if candidate.username in seen:
                            continue
                        seen.add(candidate.username)
                        candidates.append(candidate)
                        if len(candidates) >= args.candidate_limit:
                            break
                else:
                    # Expose available hypotheses without executing them.
                    candidates.extend(resolution.candidates)
            else:
                for username in dict.fromkeys(args.username):
                    if "{?}" in username:
                        candidates.extend(Candidate(username.replace("{?}", symbol), origin="explicit_pattern")
                                          for symbol in ("_", "-", "."))
                    else:
                        candidates.append(Candidate(username))
            if args.username or args.candidates:
                # De-duplicate explicit patterns and repeated usernames too.
                candidates = list({candidate.username: candidate for candidate in candidates}.values())
                tasks = len(candidates) * len(manifest.sites)
                _progress(
                    f"Planned: {len(candidates)} username(s) x {len(manifest.sites)} sites = "
                    f"{tasks} checks before regex filtering; {budget.remaining} wire requests remain. "
                    "Retries and redirects share this budget.",
                    quiet=args.quiet,
                )
                if tasks > budget.remaining and not args.offline:
                    warnings.append("Planned checks exceed remaining request budget; unqueried checks will be marked budget_exhausted.")
                scanner = Scanner(transport, max_workers=args.workers)
                for candidate in candidates:
                    findings.extend(scanner.scan(candidate.username, manifest.sites, candidate=candidate))
            value = args.email if args.email else list(dict.fromkeys(args.username))
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            report = make_report("email" if args.email else "username", value, findings,
                                 resolutions=resolutions, candidates=candidates, budget=budget,
                                 manifest=manifest, warnings=warnings)
        if args.json != "-":
            write_json(report, args.json)
            _progress(f"Saved JSON: {args.json}", quiet=args.quiet)
        formats = [fmt for fmt in ("txt", "csv", "xlsx") if getattr(args, fmt)]
        if formats:
            for path in write_reports(report, args.output_dir, formats):
                _progress(f"Saved {path}", quiet=args.quiet)
        if html_target_dir is not None:
            html_path = write_html(report, html_target_dir)
            _progress(f"Saved HTML: {html_path}", quiet=args.quiet)
            if args.open:
                open_html_file(html_path)
        # ASCII escapes preserve Unicode data even in legacy Windows pipes.
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Trace Them cancelled; active network I/O may finish after the cancellation request.", file=sys.stderr)
        return 130
    except (ValueError, OSError, requests.RequestException, OfflineError,
            BudgetExceeded, ScanCancelled, RetryDeferred) as error:
        # Exception strings can contain proxy credentials or URLs; keep diagnostics bounded.
        message = str(error) if isinstance(error, (ValueError, OfflineError)) else type(error).__name__
        print(f"Trace Them error: {message}", file=sys.stderr)
        return 2


def _run_config(parser, args) -> int:
    modifying = args.html_dir is not None or args.check_updates is not None
    if args.show and (args.reset or modifying):
        parser.error("--show cannot be combined with --reset, --html-dir, or --check-updates.")
    if args.reset and modifying:
        parser.error("--reset cannot be combined with --html-dir or --check-updates.")
    try:
        if args.reset:
            cfg = reset_config()
            _progress(f"Reset configuration to defaults: {cfg['html_output_dir']}", quiet=args.quiet)
        elif modifying:
            cfg = set_config(html_output_dir=args.html_dir, check_updates=args.check_updates)
            if args.html_dir is not None:
                _progress(f"Updated HTML report folder: {cfg['html_output_dir']}", quiet=args.quiet)
            if args.check_updates is not None:
                state = "enabled" if cfg["check_updates"] else "disabled"
                _progress(f"Automatic update checks {state}.", quiet=args.quiet)
        else:
            cfg = load_config()
        print(json.dumps(cfg, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(f"Trace Them error: {error}", file=sys.stderr)
        return 2


def _run_open(args) -> int:
    try:
        target_dir = (
            _clean_dir_arg(args.html_dir, "--html-dir")
            if args.html_dir is not None
            else get_html_output_dir()
        )
        latest = find_latest_html(target_dir)
        if args.print_path:
            print(str(latest))
        else:
            open_html_file(latest)
            _progress(f"Opened HTML report: {latest}", quiet=args.quiet)
        return 0
    except (ValueError, FileNotFoundError, OSError) as error:
        print(f"Trace Them error: {error}", file=sys.stderr)
        return 2


def _run_clean(parser, args) -> int:
    if args.all and args.files:
        parser.error("Cannot combine specific FILE arguments with --all.")
    if not args.all and not args.files:
        parser.error("Provide one or more HTML filenames or pass --all.")
    try:
        target_dir = (
            _clean_dir_arg(args.html_dir, "--html-dir")
            if args.html_dir is not None
            else get_html_output_dir()
        )
        deleted = delete_html_files(
            target_dir,
            args.files,
            delete_all=args.all,
            dry_run=args.dry_run,
        )
        payload = {
            "html_output_dir": str(target_dir),
            "dry_run": args.dry_run,
            "deleted": [str(path) for path in deleted],
            "count": len(deleted),
        }
        action_word = "Would delete" if args.dry_run else "Deleted"
        _progress(f"{action_word} {len(deleted)} HTML file(s) in {target_dir}.", quiet=args.quiet)
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, FileNotFoundError, OSError) as error:
        print(f"Trace Them error: {error}", file=sys.stderr)
        return 2


def _run_check_update(args) -> int:
    try:
        info = check_for_update(
            force=True,
            offline=args.offline,
            proxy=args.proxy,
            timeout=args.timeout,
        )
        output = {key: value for key, value in info.items() if key != "assets"}
        if info["update_available"]:
            _progress(
                f"Update available: v{info['latest_version']} (current: {info['current_version']}). "
                f"Release: {info['release_url']} | Run: {info['update_command']}",
                quiet=args.quiet,
            )
        else:
            _progress(
                f"Trace Them {info['current_version']} is up to date (latest: v{info['latest_version']}). "
                f"Release: {info['release_url']}",
                quiet=args.quiet,
            )
        print(json.dumps(output, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, OSError, requests.RequestException, OfflineError) as error:
        message = str(error) if isinstance(error, (ValueError, OfflineError)) else type(error).__name__
        print(f"Trace Them error: {message}", file=sys.stderr)
        return 2


def _run_update(args) -> int:
    try:
        result = run_self_update(
            offline=args.offline,
            proxy=args.proxy,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
        if result["status"] == "up_to_date":
            _progress(
                f"Trace Them {result['current_version']} is already up to date (latest: v{result['latest_version']}).",
                quiet=args.quiet,
            )
        elif result["status"] == "dry_run":
            _progress(
                f"Dry run: would download {result['asset']} for v{result['latest_version']} from {result['download_url']}.",
                quiet=args.quiet,
            )
        else:
            _progress(
                f"Verified SHA-256 and launched installer for v{result['latest_version']}. Exiting current process.",
                quiet=args.quiet,
            )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, requests.RequestException, OfflineError) as error:
        message = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError, OfflineError))
            else type(error).__name__
        )
        print(f"Trace Them error: {message}", file=sys.stderr)
        return 2


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.open_html:
        if args.command is not None:
            parser.error("--open-html cannot be combined with a subcommand.")
        code = _run_open(args)
    elif args.command is None:
        if args.html_dir is not None or args.print_path:
            parser.error("--html-dir and --print-path at the top level require --open-html.")
        parser.error("A command or --open-html is required.")
    elif args.command == "find":
        code = _run_find(parser, args)
    elif args.command == "config":
        code = _run_config(parser, args)
    elif args.command == "clean":
        code = _run_clean(parser, args)
    elif args.command == "check-update":
        code = _run_check_update(args)
    elif args.command == "update":
        code = _run_update(args)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    if args.command not in ("check-update", "update") and not getattr(args, "offline", False):
        notice = maybe_notify_update(offline=False, proxy=getattr(args, "proxy", None))
        if notice is not None:
            # Always notify about newer releases on stderr even when --quiet is set.
            _progress(format_update_notice(notice), quiet=False)

    return code
