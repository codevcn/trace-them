"""Apify adapter preserving the canonical Trace Them report and its evidence."""

from __future__ import annotations

import json
import subprocess
import sys


def _text(value, name):
    if (not isinstance(value, str) or not value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f"{name} must be a nonempty string without control characters")
    return value


def build_command(input_data: dict) -> list[str]:
    """Validate Actor input and construct an argument array without a shell."""
    if not isinstance(input_data, dict):
        raise ValueError("Actor input must be a JSON object")
    allowed = {"usernames", "email", "candidates", "candidateLimit", "sites", "maxRequests", "offline"}
    if set(input_data) - allowed:
        raise ValueError("Actor input contains unsupported fields")
    usernames = input_data.get("usernames")
    email = input_data.get("email")
    if (usernames is not None) == (email is not None):
        raise ValueError("Supply exactly one of usernames or email")
    command = ["trace-them", "find", "--quiet"]
    if usernames is not None:
        if not isinstance(usernames, list) or not 1 <= len(usernames) <= 100:
            raise ValueError("usernames must be a list containing 1 to 100 usernames")
        for name in dict.fromkeys(_text(value, "username") for value in usernames):
            command.append("--username=" + name)
    else:
        command.append("--email=" + _text(email, "email"))
    for field in ("candidates", "offline"):
        if field in input_data and not isinstance(input_data[field], bool):
            raise ValueError(f"{field} must be a boolean")
    if input_data.get("candidates", False):
        if email is None:
            raise ValueError("candidates requires email input")
        command.append("--candidates")
    if "candidateLimit" in input_data:
        value = input_data["candidateLimit"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            raise ValueError("candidateLimit must be an integer between 1 and 10")
        command.extend(["--candidate-limit", str(value)])
    if "sites" in input_data:
        sites = input_data["sites"]
        if not isinstance(sites, list) or len(sites) > 1000:
            raise ValueError("sites must be a list of at most 1000 names")
        for site in dict.fromkeys(_text(value, "site") for value in sites):
            command.append("--site=" + site)
    if "maxRequests" in input_data:
        value = input_data["maxRequests"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100000:
            raise ValueError("maxRequests must be an integer between 0 and 100000")
        command.extend(["--max-requests", str(value)])
    if input_data.get("offline", False):
        command.append("--offline")
    return command


def run_actor(input_data=None, *, runner=subprocess.run) -> dict:
    """Read input, run one bounded scan, and store one full report as one item.

    Runner injection allows offline verification without invoking Apify or a
    cloud service. The shared CLI request budget spans all supplied usernames.
    """
    options = {"check": True, "capture_output": True, "text": True, "encoding": "utf-8"}
    if input_data is None:
        received = runner(["apify", "actor", "get-input"], **options)
        input_data = json.loads(received.stdout)
    completed = runner(build_command(input_data), **options)
    report = json.loads(completed.stdout)
    if (not isinstance(report, dict) or report.get("schema_version") != "1.0"
            or not isinstance(report.get("findings"), list)
            or not isinstance(report.get("input"), dict)):
        raise ValueError("Trace Them did not return a supported canonical report")
    payload = json.dumps(report, ensure_ascii=False)
    # Official current CLI supports reading JSON from stdin when item is omitted.
    runner(["apify", "actor", "push-data"], input=payload, **options)
    return report


def main() -> int:
    try:
        run_actor()
    except (ValueError, OSError, subprocess.SubprocessError):
        # Do not print input, email, captured command lines, tokens or API errors.
        print("Trace Them Actor failed to validate input, execute the scan, or store its report.", file=sys.stderr)
        return 1
    print("Trace Them Actor stored one canonical report.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
