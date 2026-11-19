"""Explicit and cached GitHub release checks and verified Windows self-update."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit

import requests

from trace_them import __version__
from trace_them.config import load_config, save_update_check_state
from trace_them.models import utc_now
from trace_them.transport import HTTPTransport, OfflineError, RequestBudget

GITHUB_REPO = "codevcn/trace-them"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
UPDATE_CHECK_TTL_SECONDS = 12 * 3600
ERROR_COOLDOWN_SECONDS = 15 * 60
MAX_INSTALLER_BYTES = 200 * 1024 * 1024

_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(?:[-._+]?([A-Za-z0-9.-]+))?$")
_SHA256_LINE_RE = re.compile(r"^\s*([0-9a-fA-F]{64})\s+[* ]?(.+?)\s*$")


def parse_version(value: str) -> tuple[tuple[int, ...], int, str]:
    """Parse a semantic-like version string for reliable ordering."""
    match = _VERSION_RE.match((value or "").strip())
    if not match:
        raise ValueError(f"Unsupported version format: {value!r}")
    numbers = tuple(int(part) for part in match.group(1).split("."))
    prerelease = match.group(2) or ""
    # Stable releases (1) sort higher than prereleases (0) with same numeric prefix.
    stability = 0 if prerelease else 1
    return numbers, stability, prerelease.lower()


def normalize_version(value: str) -> str:
    """Return a normalized version string without leading 'v'."""
    text = (value or "").strip()
    return text[1:] if text.lower().startswith("v") else text


def is_newer_version(latest: str, current: str = __version__) -> bool:
    """Return True if latest is strictly newer than current."""
    try:
        latest_nums, latest_stable, latest_pre = parse_version(latest)
        current_nums, current_stable, current_pre = parse_version(current)
    except ValueError:
        return False
    width = max(len(latest_nums), len(current_nums))
    l_pad = latest_nums + (0,) * (width - len(latest_nums))
    c_pad = current_nums + (0,) * (width - len(current_nums))
    if l_pad != c_pad:
        return l_pad > c_pad
    if latest_stable != current_stable:
        return latest_stable > current_stable
    return latest_pre > current_pre


def _is_trusted_github_url(url: object) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "github.com"
        or host.endswith(".github.com")
        or host.endswith(".githubusercontent.com")
    )


def _seconds_since(iso_timestamp: object) -> float | None:
    if not isinstance(iso_timestamp, str) or not iso_timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except ValueError:
        return None


def _build_status(
    *,
    latest_version: str,
    release_name: str,
    release_url: str,
    published_at: str | None,
    assets: list[dict[str, Any]] | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    available = is_newer_version(latest_version, __version__)
    return {
        "current_version": __version__,
        "latest_version": normalize_version(latest_version),
        "update_available": available,
        "release_name": release_name,
        "release_url": release_url,
        "published_at": published_at,
        "update_command": "trace-them update" if available else None,
        "cached": cached,
        "assets": assets or [],
    }


def _fetch_latest_release(*, proxy: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    budget = RequestBudget(10)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with HTTPTransport(
        budget,
        timeout=(min(5.0, timeout), timeout),
        retries=0,
        per_domain_interval=0.0,
        proxy=proxy,
    ) as transport:
        response = transport.request("GET", LATEST_RELEASE_URL, headers=headers)
        try:
            response.raise_for_status()
            data = response.json()
        finally:
            response.close()
    if not isinstance(data, dict):
        raise ValueError("GitHub release API returned an unexpected payload")
    tag_name = data.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise ValueError("GitHub release response is missing tag_name")
    # Validate version shape upfront.
    parse_version(tag_name)
    html_url = data.get("html_url")
    release_url = html_url if _is_trusted_github_url(html_url) else RELEASES_PAGE_URL
    release_name = str(data.get("name") or tag_name)
    published_at = str(data["published_at"]) if data.get("published_at") else None
    raw_assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    assets = []
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        dl_url = item.get("browser_download_url")
        if isinstance(name, str) and _is_trusted_github_url(dl_url):
            assets.append({"name": name, "url": dl_url, "size": item.get("size")})
    return {
        "latest_version": normalize_version(tag_name),
        "release_name": release_name,
        "release_url": release_url,
        "published_at": published_at,
        "assets": assets,
    }


def check_for_update(
    *,
    force: bool = False,
    offline: bool = False,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Check GitHub Releases for a newer Trace Them release, respecting cache & offline."""
    if offline:
        raise OfflineError("Update checks are disabled in offline mode")

    cfg = load_config()
    cached_state = cfg.get("update_check") or {}

    if not force:
        age = _seconds_since(cached_state.get("last_checked_at"))
        cached_ver = cached_state.get("latest_version")
        if age is not None and age < UPDATE_CHECK_TTL_SECONDS and isinstance(cached_ver, str):
            return _build_status(
                latest_version=cached_ver,
                release_name=str(cached_state.get("release_name") or cached_ver),
                release_url=str(cached_state.get("release_url") or RELEASES_PAGE_URL),
                published_at=cached_state.get("published_at"),
                cached=True,
            )
        err_age = _seconds_since(cached_state.get("last_error_at"))
        if err_age is not None and err_age < ERROR_COOLDOWN_SECONDS:
            if isinstance(cached_ver, str):
                return _build_status(
                    latest_version=cached_ver,
                    release_name=str(cached_state.get("release_name") or cached_ver),
                    release_url=str(cached_state.get("release_url") or RELEASES_PAGE_URL),
                    published_at=cached_state.get("published_at"),
                    cached=True,
                )
            raise requests.exceptions.ConnectionError("Update check skipped during error cooldown")

    try:
        fetched = _fetch_latest_release(proxy=proxy, timeout=timeout)
    except Exception as error:
        if not force:
            new_state = dict(cached_state)
            new_state["last_error_at"] = utc_now()
            new_state["last_error"] = type(error).__name__
            try:
                save_update_check_state(new_state)
            except OSError:
                pass
        raise

    persisted = {
        "last_checked_at": utc_now(),
        "latest_version": fetched["latest_version"],
        "release_name": fetched["release_name"],
        "release_url": fetched["release_url"],
        "published_at": fetched["published_at"],
    }
    try:
        save_update_check_state(persisted)
    except OSError:
        pass

    return _build_status(
        latest_version=fetched["latest_version"],
        release_name=fetched["release_name"],
        release_url=fetched["release_url"],
        published_at=fetched["published_at"],
        assets=fetched["assets"],
        cached=False,
    )


def format_update_notice(info: dict[str, Any]) -> str:
    """Format a concise stderr notice when a newer release exists."""
    return (
        f"[Trace Them] New release available: v{info['latest_version']} "
        f"(current: {info['current_version']}). "
        f"Release: {info['release_url']} | Run: {info['update_command']}"
    )


def maybe_notify_update(*, offline: bool = False, proxy: str | None = None) -> dict[str, Any] | None:
    """Check for updates if enabled and return info only when a newer release exists."""
    if offline:
        return None
    try:
        cfg = load_config()
    except (ValueError, OSError):
        return None
    if not cfg.get("check_updates", True):
        return None
    try:
        info = check_for_update(force=False, offline=False, proxy=proxy, timeout=2.5)
    except (ValueError, OSError, requests.RequestException, OfflineError):
        return None
    if info.get("update_available"):
        return info
    return None


def _select_installer_asset(assets: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    setup_asset = None
    sums_asset = None
    for item in assets:
        name = item.get("name", "")
        lower = name.lower()
        if lower == "sha256sums.txt":
            sums_asset = item
        elif lower.startswith("trace-them-setup") and lower.endswith(".exe"):
            setup_asset = item
    if setup_asset is None:
        raise ValueError("Latest release does not contain a Windows installer asset (trace-them-setup-*.exe)")
    if sums_asset is None:
        raise ValueError("Latest release does not contain SHA256SUMS.txt for verification")
    return setup_asset, sums_asset


def _parse_sha256_for(sums_text: str, filename: str) -> str:
    target = filename.lower()
    for line in sums_text.splitlines():
        match = _SHA256_LINE_RE.match(line)
        if not match:
            continue
        digest, name = match.group(1).lower(), Path(match.group(2).strip()).name.lower()
        if name == target:
            return digest
    raise ValueError(f"SHA256SUMS.txt does not contain a checksum for {filename}")


def run_self_update(
    *,
    offline: bool = False,
    proxy: str | None = None,
    timeout: float = 30.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Download, verify SHA-256, and launch the latest Windows installer if available."""
    info = check_for_update(force=True, offline=offline, proxy=proxy, timeout=timeout)
    if not info["update_available"]:
        return {
            "updated": False,
            "status": "up_to_date",
            "current_version": info["current_version"],
            "latest_version": info["latest_version"],
            "release_url": info["release_url"],
        }

    setup_asset, sums_asset = _select_installer_asset(info.get("assets", []))
    if dry_run:
        return {
            "updated": False,
            "status": "dry_run",
            "current_version": info["current_version"],
            "latest_version": info["latest_version"],
            "release_url": info["release_url"],
            "asset": setup_asset["name"],
            "download_url": setup_asset["url"],
            "checksum_url": sums_asset["url"],
        }

    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "Binary self-update only applies to the packaged Trace Them executable. "
            "Update this source/venv environment with 'git pull' or 'pip install --upgrade .'."
        )
    if os.name != "nt":
        raise RuntimeError("Installer self-update is only supported on Windows.")

    budget = RequestBudget(20)
    with HTTPTransport(
        budget,
        timeout=(min(10.0, timeout), timeout),
        retries=1,
        per_domain_interval=0.0,
        proxy=proxy,
    ) as transport:
        sums_resp = transport.request("GET", sums_asset["url"])
        try:
            sums_resp.raise_for_status()
            expected_sha = _parse_sha256_for(sums_resp.text, setup_asset["name"])
        finally:
            sums_resp.close()

        transport.max_response_bytes = MAX_INSTALLER_BYTES
        installer_resp = transport.request("GET", setup_asset["url"])
        try:
            installer_resp.raise_for_status()
            payload = installer_resp.content
        finally:
            installer_resp.close()

    actual_sha = hashlib.sha256(payload).hexdigest().lower()
    if actual_sha != expected_sha:
        raise ValueError(
            f"SHA-256 checksum mismatch for {setup_asset['name']}: expected {expected_sha}, got {actual_sha}"
        )

    staging_dir = Path(tempfile.mkdtemp(prefix="trace-them-update-"))
    installer_path = staging_dir / Path(setup_asset["name"]).name
    installer_path.write_bytes(payload)

    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            str(installer_path),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
        ],
        close_fds=True,
        creationflags=creationflags,
    )
    return {
        "updated": True,
        "status": "installer_launched",
        "current_version": info["current_version"],
        "latest_version": info["latest_version"],
        "release_url": info["release_url"],
        "asset": setup_asset["name"],
        "sha256": actual_sha,
        "installer_path": str(installer_path),
    }
