"""Tests for release update checks, single-file config toggle, check-update, and self-update."""

import hashlib
import json
from pathlib import Path
import sys

import pytest

from trace_them import __version__
from trace_them.cli import main
from trace_them.config import load_config, load_default_config
from trace_them.updater import is_newer_version, parse_version


def _release_payload(tag="v9.9.9", assets=None):
    return {
        "tag_name": tag,
        "name": f"Trace Them {tag}",
        "html_url": f"https://github.com/codevcn/trace-them/releases/tag/{tag}",
        "published_at": "2026-11-19T10:00:00Z",
        "assets": assets or [],
    }


def test_version_comparison_handles_v_prefix_and_prereleases():
    assert parse_version("v0.2.0") > parse_version("0.1.0")
    assert is_newer_version("v0.2.0", "0.1.0") is True
    assert is_newer_version("0.1.0", "0.1.0") is False
    assert is_newer_version("v0.1.0", "0.2.0") is False
    assert is_newer_version("0.2.0", "0.2.0-rc1") is True


def test_default_config_enables_update_checks_and_uses_single_config_file(
    isolate_config, queued_http, response_factory, capsys
):
    config_file, _ = isolate_config
    assert load_default_config()["check_updates"] is True

    assert main(["config", "--check-updates", "off"]) == 0
    off_cfg = json.loads(capsys.readouterr().out)
    assert off_cfg["check_updates"] is False

    queued_http[0].append(response_factory(text=json.dumps(_release_payload(f"v{__version__}"))))
    assert main(["config", "--check-updates", "on"]) == 0
    on_cfg = json.loads(capsys.readouterr().out)
    assert on_cfg["check_updates"] is True

    # Everything stays inside the single config file (no extra update-state.json file).
    sibling_files = [item.name for item in config_file.parent.iterdir() if item.is_file()]
    assert sibling_files == [config_file.name]


def test_update_notice_prints_on_any_command_even_with_quiet_and_caches_in_config(
    isolate_config, queued_http, response_factory, capsys
):
    config_file, html_dir = isolate_config
    config_data = json.loads(config_file.read_text(encoding="utf-8"))
    config_data.pop("update_check", None)
    config_data["check_updates"] = True
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    queued_http[0].append(response_factory(text=json.dumps(_release_payload("v9.9.9"))))

    # 1) Running `find --quiet` hits GitHub once, prints notice on stderr, keeps stdout valid JSON.
    assert main(["find", "--username", "fixture", "--site", "GitHub", "--max-requests", "0", "--quiet"]) == 0
    out1 = capsys.readouterr()
    assert json.loads(out1.out)["schema_version"] == "1.0"
    assert "v9.9.9" in out1.err
    assert "trace-them update" in out1.err
    assert len(queued_http[1]) == 1

    # Cache must live inside config.json only, with zero extra files.
    persisted = json.loads(config_file.read_text(encoding="utf-8"))
    assert persisted["update_check"]["latest_version"] == "9.9.9"
    assert [p.name for p in config_file.parent.iterdir() if p.is_file()] == [config_file.name]

    # 2) Subsequent command (`clean --all --quiet`) still prints notice from config.json cache without extra HTTP.
    (html_dir / "sample.html").write_text("<html></html>", encoding="utf-8")
    assert main(["clean", "--all", "--quiet"]) == 0
    out2 = capsys.readouterr()
    assert json.loads(out2.out)["count"] == 2
    assert "v9.9.9" in out2.err
    assert len(queued_http[1]) == 1


def test_no_update_notice_when_disabled_offline_or_up_to_date(
    isolate_config, queued_http, response_factory, capsys
):
    config_file, _ = isolate_config

    # Case 1: disabled via config -> zero network requests, no notice
    assert main(["config", "--check-updates", "off", "--quiet"]) == 0
    assert main(["config", "--show", "--quiet"]) == 0
    out = capsys.readouterr()
    assert "New release available" not in out.err
    assert not queued_http[1]

    # Case 2: enabled, but --offline -> zero network requests, no notice
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    cfg["check_updates"] = True
    cfg.pop("update_check", None)
    config_file.write_text(json.dumps(cfg), encoding="utf-8")

    assert main(["find", "--username", "fixture", "--site", "GitHub", "--offline", "--quiet"]) == 0
    out_offline = capsys.readouterr()
    assert "New release available" not in out_offline.err
    assert not queued_http[1]

    # Case 3: enabled & online, but latest equals current version -> no notice
    queued_http[0].append(response_factory(text=json.dumps(_release_payload(f"v{__version__}"))))
    assert main(["config", "--show", "--quiet"]) == 0
    out_current = capsys.readouterr()
    assert "New release available" not in out_current.err
    assert len(queued_http[1]) == 1


def test_check_update_command_reports_version_link_and_command(queued_http, response_factory, capsys):
    queued_http[0].append(response_factory(text=json.dumps(_release_payload("v2.0.0"))))
    assert main(["check-update"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["current_version"] == __version__
    assert payload["latest_version"] == "2.0.0"
    assert payload["update_available"] is True
    assert payload["release_url"] == "https://github.com/codevcn/trace-them/releases/tag/v2.0.0"
    assert payload["update_command"] == "trace-them update"
    assert "v2.0.0" in captured.err
    assert "trace-them update" in captured.err


def test_check_update_offline_returns_exit_code_2(queued_http, capsys):
    assert main(["check-update", "--offline"]) == 2
    assert not queued_http[1]
    assert "offline" in capsys.readouterr().err.lower()


def test_update_command_dry_run_and_non_frozen_guard(queued_http, response_factory, capsys):
    assets = [
        {
            "name": "trace-them-setup-2.0.0.exe",
            "browser_download_url": "https://github.com/codevcn/trace-them/releases/download/v2.0.0/trace-them-setup-2.0.0.exe",
        },
        {
            "name": "SHA256SUMS.txt",
            "browser_download_url": "https://github.com/codevcn/trace-them/releases/download/v2.0.0/SHA256SUMS.txt",
        },
    ]
    queued_http[0].append(response_factory(text=json.dumps(_release_payload("v2.0.0", assets=assets))))
    assert main(["update", "--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["status"] == "dry_run"
    assert dry["asset"] == "trace-them-setup-2.0.0.exe"

    # Running without --dry-run in non-frozen venv refuses cleanly.
    queued_http[0].append(response_factory(text=json.dumps(_release_payload("v2.0.0", assets=assets))))
    assert main(["update"]) == 2
    assert "packaged Trace Them executable" in capsys.readouterr().err


def test_update_command_verifies_sha256_and_launches_installer_when_frozen(
    queued_http, response_factory, monkeypatch, capsys
):
    fake_exe = b"MZ-fake-installer-binary"
    digest = hashlib.sha256(fake_exe).hexdigest()
    assets = [
        {
            "name": "trace-them-setup-2.0.0.exe",
            "browser_download_url": "https://github.com/codevcn/trace-them/releases/download/v2.0.0/trace-them-setup-2.0.0.exe",
        },
        {
            "name": "SHA256SUMS.txt",
            "browser_download_url": "https://github.com/codevcn/trace-them/releases/download/v2.0.0/SHA256SUMS.txt",
        },
    ]
    launched = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("trace_them.updater.os.name", "nt")
    monkeypatch.setattr("trace_them.updater.subprocess.Popen", lambda cmd, **kw: launched.append((cmd, kw)))

    queued_http[0].extend([
        response_factory(text=json.dumps(_release_payload("v2.0.0", assets=assets))),
        response_factory(text=f"{digest}  trace-them-setup-2.0.0.exe\n"),
        response_factory(text=fake_exe.decode("ascii")),
    ])
    assert main(["update"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["updated"] is True
    assert out["status"] == "installer_launched"
    assert out["sha256"] == digest
    assert len(launched) == 1
    assert "/VERYSILENT" in launched[0][0]
    assert Path(launched[0][0][0]).read_bytes() == fake_exe

    # Checksum mismatch must fail before launching installer.
    launched.clear()
    queued_http[0].extend([
        response_factory(text=json.dumps(_release_payload("v2.0.0", assets=assets))),
        response_factory(text=f"{'0' * 64}  trace-them-setup-2.0.0.exe\n"),
        response_factory(text=fake_exe.decode("ascii")),
    ])
    assert main(["update"]) == 2
    assert "checksum mismatch" in capsys.readouterr().err.lower()
    assert not launched


@pytest.mark.parametrize("argv,expected", [
    (["--help"], ["check-update", "update", "config"]),
    (["config", "--help"], ["--check-updates"]),
    (["check-update", "--help"], ["--offline", "--proxy"]),
    (["update", "--help"], ["--dry-run", "--offline"]),
])
def test_update_cli_help_entries_present(argv, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for item in expected:
        assert item in out


def test_agent_skill_file_and_packaging_specs_exist():
    skill = Path("skills/trace-them/SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: trace-them\n")
    assert "trace-them find" in skill
    assert "trace-them check-update" in skill
    assert Path("devel/trace-them.spec").is_file()
    assert Path("devel/installer.iss").is_file()
    assert Path("devel/build_windows.ps1").is_file()
    assert Path("docs/images/trace-them.ico").is_file()
    assert "trace-them.ico" in Path("devel/trace-them.spec").read_text(encoding="utf-8")
    assert "SetupIconFile=" in Path("devel/installer.iss").read_text(encoding="utf-8")
    assert load_config()["check_updates"] is False  # isolated test fixture
