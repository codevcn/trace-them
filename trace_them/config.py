"""Persistent user and bundled default configuration for Trace Them."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

CONFIG_ENV_VAR = "TRACE_THEM_CONFIG"
RESOURCE_CONFIG_PATH = Path(__file__).with_name("resources") / "config.json"
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_dir_string(value: object, field: str = "html_output_dir") -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{field} must be a nonempty path without control characters")
    return value.strip()


def _validate_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _posix_fallback_html_dir() -> str:
    base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return str((base / "trace-them" / "reports").resolve())


def _normalize_effective_dir(raw: str, *, from_default: bool) -> str:
    if from_default and os.name != "nt" and _WINDOWS_DRIVE_RE.match(raw):
        return _posix_fallback_html_dir()
    return str(Path(raw).expanduser().resolve())


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".trace-them-cfg-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def get_config_path() -> Path:
    """Return the active user-writable configuration file path."""
    override = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "trace-them" / "config.json"


def load_default_config() -> dict[str, Any]:
    """Load and validate the bundled default configuration file."""
    with RESOURCE_CONFIG_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("Bundled config.json must contain a JSON object")
    raw_dir = _validate_dir_string(data.get("html_output_dir"))
    check_updates = _validate_bool(data.get("check_updates", True), "check_updates")
    return {"html_output_dir": raw_dir, "check_updates": check_updates}


def _read_user_payload(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        with config_path.open(encoding="utf-8") as stream:
            user_data = json.load(stream)
    except (OSError, ValueError) as error:
        raise ValueError(f"Invalid configuration file {config_path}: {error}") from error
    if not isinstance(user_data, dict):
        raise ValueError(f"Configuration file {config_path} must contain a JSON object")
    return user_data


def load_config() -> dict[str, Any]:
    """Load effective configuration, merging user overrides over bundled defaults."""
    defaults = load_default_config()
    default_effective = _normalize_effective_dir(defaults["html_output_dir"], from_default=True)
    default_check_updates = bool(defaults["check_updates"])
    config_path = get_config_path()
    source = "default"
    effective_dir = default_effective
    effective_check_updates = default_check_updates
    update_check: dict[str, Any] | None = None

    user_data = _read_user_payload(config_path)
    if "html_output_dir" in user_data:
        raw_user = _validate_dir_string(user_data["html_output_dir"])
        effective_dir = _normalize_effective_dir(raw_user, from_default=False)
        source = "user"
    if "check_updates" in user_data:
        effective_check_updates = _validate_bool(user_data["check_updates"], "check_updates")
        source = "user"
    if isinstance(user_data.get("update_check"), dict):
        update_check = dict(user_data["update_check"])

    return {
        "config_file": str(config_path),
        "default_config_file": str(RESOURCE_CONFIG_PATH),
        "html_output_dir": effective_dir,
        "default_html_output_dir": default_effective,
        "check_updates": effective_check_updates,
        "default_check_updates": default_check_updates,
        "update_check": update_check,
        "source": source,
    }


def get_html_output_dir() -> Path:
    """Return the configured directory where HTML visualization reports are written."""
    return Path(load_config()["html_output_dir"])


def _write_user_payload(config_path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(config_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def set_config(
    *,
    html_output_dir: str | None = None,
    check_updates: bool | None = None,
    create_html_dir: bool = True,
) -> dict[str, Any]:
    """Validate and persist one or more configuration fields into config.json."""
    config_path = get_config_path()
    try:
        payload = _read_user_payload(config_path)
    except ValueError:
        payload = {}

    if html_output_dir is not None:
        cleaned = _validate_dir_string(html_output_dir, field="--html-dir")
        target = Path(cleaned).expanduser().resolve()
        if target.exists() and not target.is_dir():
            raise ValueError(f"Configured HTML path is not a directory: {target}")
        if create_html_dir:
            target.mkdir(parents=True, exist_ok=True)
        payload["html_output_dir"] = str(target)

    if check_updates is not None:
        payload["check_updates"] = _validate_bool(check_updates, "--check-updates")

    _write_user_payload(config_path, payload)
    return load_config()


def set_html_output_dir(path_value: str, *, create: bool = True) -> dict[str, Any]:
    """Validate, persist, and return updated configuration with a new HTML folder path."""
    return set_config(html_output_dir=path_value, create_html_dir=create)


def save_update_check_state(state: dict[str, Any]) -> None:
    """Persist cached release-check metadata inside the single config.json file."""
    if not isinstance(state, dict):
        raise ValueError("update_check state must be a JSON object")
    config_path = get_config_path()
    try:
        payload = _read_user_payload(config_path)
    except ValueError:
        payload = {}
    payload["update_check"] = dict(state)
    _write_user_payload(config_path, payload)


def reset_config() -> dict[str, Any]:
    """Remove user configuration overrides and return the default configuration."""
    config_path = get_config_path()
    if config_path.exists():
        config_path.unlink()
    return load_config()
