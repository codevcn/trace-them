"""Trace Them command line: explicit inputs, bounded work and JSON-first output."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import requests

from trace_them import __version__
from trace_them.engine import Scanner
from trace_them.manifest import load_manifest
from trace_them.models import Candidate
from trace_them.reporting import make_report, write_json, write_reports
from trace_them.resolvers import GravatarResolver, email_candidates, validate_email
from trace_them.transport import (
    BudgetExceeded, HTTPTransport, OfflineError, RequestBudget, RetryDeferred, ScanCancelled,
)


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


def _parser():
    parser = argparse.ArgumentParser(prog="trace-them", description="Discover public profiles with explicit evidence.")
    parser.add_argument("--version", action="version", version=f"Trace Them {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("find", help="Check exact usernames or resolve an email through public sources.")
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
    find.add_argument("--quiet", action="store_true", help="Suppress progress on stderr.")
    return parser


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.candidates and args.email is None:
        parser.error("--candidates requires --email.")
    if args.email and not args.candidates and (args.site or args.manifest or args.nsfw):
        parser.error("--site, --manifest and --nsfw apply to username scans; add --candidates for email-derived scans.")
    if args.username and any(not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)
                             for value in args.username):
        parser.error("Usernames must be nonempty and contain no control characters.")
    try:
        if args.email is not None:
            args.email = validate_email(args.email)
    except ValueError as error:
        parser.error(str(error))

    def progress(message):
        if not args.quiet:
            encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
            print(message.encode(encoding, "backslashreplace").decode(encoding), file=sys.stderr)

    budget = RequestBudget(args.max_requests)
    findings, resolutions, candidates, warnings = [], [], [], []
    manifest = None
    try:
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
                progress("Resolving public Gravatar profile; associations remain source-scoped.")
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
                progress(f"Planned: {len(candidates)} username(s) x {len(manifest.sites)} sites = "
                         f"{tasks} checks before regex filtering; {budget.remaining} wire requests remain. "
                         "Retries and redirects share this budget.")
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
            progress(f"Saved JSON: {args.json}")
        formats = [fmt for fmt in ("txt", "csv", "xlsx") if getattr(args, fmt)]
        if formats:
            for path in write_reports(report, args.output_dir, formats):
                progress(f"Saved {path}")
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
