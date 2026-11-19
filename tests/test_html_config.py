"""HTML visualization, persistent folder configuration, and latest-report opening tests."""

import json
import os
from pathlib import Path
import time

import pytest

from trace_them.cli import main
from trace_them.config import get_html_output_dir, load_config, load_default_config
from trace_them.html_report import find_latest_html, render_html, write_html
from trace_them.models import Candidate, Evidence, Finding, Status
from trace_them.reporting import make_report
from trace_them.resolvers import Resolution
from trace_them.site_types import get_site_types
from trace_them.transport import RequestBudget


def test_bundled_default_config_declares_expected_windows_folder():
    defaults = load_default_config()
    assert defaults["html_output_dir"] == r"D:\D-AppData\me-trace-them"


def test_config_cli_show_set_and_reset(isolate_config, tmp_path, monkeypatch, capsys):
    _, default_html_dir = isolate_config
    assert main(["config", "--show"]) == 0
    initial = json.loads(capsys.readouterr().out)
    assert Path(initial["html_output_dir"]).resolve() == default_html_dir.resolve()

    custom_dir = tmp_path / "custom-html"
    assert main(["config", "--html-dir", str(custom_dir)]) == 0
    updated_out = capsys.readouterr()
    updated = json.loads(updated_out.out)
    assert Path(updated["html_output_dir"]).resolve() == custom_dir.resolve()
    assert updated["source"] == "user"
    assert custom_dir.is_dir()
    assert "Updated HTML report folder" in updated_out.err

    # Resetting restores check_updates=True; disable update HTTP call in this offline config test.
    monkeypatch.setattr("trace_them.cli.maybe_notify_update", lambda **kwargs: None)
    assert main(["config", "--reset"]) == 0
    reset_data = json.loads(capsys.readouterr().out)
    assert reset_data["source"] == "default"
    assert load_config()["source"] == "default"


def test_config_cli_rejects_regular_file_as_html_dir(tmp_path, capsys):
    not_a_dir = tmp_path / "plain.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    assert main(["config", "--html-dir", str(not_a_dir)]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_find_writes_json_stdout_and_html_report_in_configured_dir(isolate_config, capsys):
    _, html_dir = isolate_config
    assert main(["find", "--username", "fixture", "--site", "GitHub", "--offline"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["input"]["value"] == "fixture"
    assert "Saved HTML:" in captured.err
    html_files = list(html_dir.glob("*.html"))
    assert len(html_files) == 1
    content = html_files[0].read_text(encoding="utf-8")
    assert "Trace Them" in content
    assert "GitHub" in content
    assert "unverified" in content


def test_find_no_html_skips_html_creation(isolate_config, capsys):
    _, html_dir = isolate_config
    assert main(["find", "--username", "fixture", "--site", "GitHub", "--offline", "--no-html"]) == 0
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert "Saved HTML:" not in captured.err
    assert not html_dir.exists()


def test_find_rejects_open_with_no_html():
    with pytest.raises(SystemExit) as exc:
        main(["find", "--username", "fixture", "--offline", "--no-html", "--open"])
    assert exc.value.code == 2


def test_find_open_launches_generated_html_report(isolate_config, monkeypatch, capsys):
    _, html_dir = isolate_config
    opened = []
    monkeypatch.setattr("trace_them.cli.open_html_file", lambda path: opened.append(Path(path)))
    assert main(["find", "--username", "fixture", "--site", "GitHub", "--offline", "--open"]) == 0
    capsys.readouterr()
    assert len(opened) == 1
    assert opened[0].is_file()
    assert opened[0].parent == html_dir.resolve()


def test_open_cli_selects_newest_html_and_supports_print_path(monkeypatch, capsys):
    html_dir = get_html_output_dir()
    html_dir.mkdir(parents=True, exist_ok=True)
    older = html_dir / "20261118-100000-000000-older.html"
    newer = html_dir / "20261118-100001-000000-newer.html"
    older.write_text("<html>old</html>", encoding="utf-8")
    newer.write_text("<html>new</html>", encoding="utf-8")
    now = time.time()
    os.utime(older, (now - 60, now - 60))
    os.utime(newer, (now, now))

    assert find_latest_html(html_dir) == newer
    assert main(["open", "--print-path"]) == 0
    assert Path(capsys.readouterr().out.strip()).resolve() == newer.resolve()

    launched = []
    monkeypatch.setattr("trace_them.cli.open_html_file", lambda path: launched.append(Path(path)))
    assert main(["open"]) == 0
    assert launched == [newer.resolve()]


def test_open_cli_returns_exit_code_2_when_folder_empty_or_missing(tmp_path, capsys):
    assert main(["open", "--html-dir", str(tmp_path / "missing")]) == 2
    assert "does not exist" in capsys.readouterr().err

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert main(["open", "--html-dir", str(empty_dir)]) == 2
    assert "No HTML report files" in capsys.readouterr().err


def test_html_renderer_escapes_untrusted_payloads_and_blocks_unsafe_links(tmp_path):
    xss_payload = '<script>alert("xss")</script>'
    ev = [
        Evidence("http_response", "javascript:alert(1)", f"Header {xss_payload}"),
        Evidence("http_response", "https://example.com/evidence", "Valid HTTPS evidence"),
    ]
    assoc_ev = [
        Evidence("source_reported_email_association", "https://api.gravatar.com/v3/profiles/abc", "Gravatar match"),
    ]
    findings = [
        Finding("Fixture", xss_payload, "javascript:alert(2)", Status.FOUND, f"Reason {xss_payload}",
                evidence=ev, association="unverified", query_time=0.05),
        Finding("Gravatar", "safe_slug", "https://gravatar.com/safe_slug", Status.FOUND,
                "Resolved", association="source_reported", association_evidence=assoc_ev,
                origin="public_email_resolution", http_status=200),
    ]
    candidates = [Candidate("safe_slug", origin="public_profile_username", platform="Gravatar",
                            evidence=[Evidence("source_username", "https://gravatar.com/safe_slug", "slug")])]
    resolutions = [Resolution("Gravatar", Status.FOUND, "Resolved profile", evidence=ev)]
    report = make_report("email", "fixture@example.com", findings, resolutions=resolutions,
                         candidates=candidates, budget=RequestBudget(10), warnings=["Sample warning"])

    html_doc = render_html(report)
    assert '<script>alert("xss")</script>' not in html_doc
    assert 'href="javascript:' not in html_doc
    assert 'href="https://gravatar.com/safe_slug"' in html_doc
    assert 'href="https://example.com/evidence"' in html_doc
    assert "source_reported" in html_doc
    assert "unverified" in html_doc
    assert "--ds-brand-bold: #0C66E4" in html_doc
    assert "<svg" in html_doc
    assert 'id="scroll-top-btn"' in html_doc
    assert 'id="scroll-bottom-btn"' in html_doc
    assert 'behavior: "instant"' in html_doc
    assert 'id="site-type-filter"' in html_doc
    for label in ("All Types", "Social Media", "Programming", "Gaming"):
        assert label in html_doc

    written = write_html(report, tmp_path, stem="../../escape")
    assert written.resolve().parent == tmp_path.resolve()
    assert written.suffix == ".html"


def test_site_type_classification_and_html_row_attributes():
    assert get_site_types("Instagram") == ["social"]
    assert get_site_types("github") == ["programming"]
    assert get_site_types("Minecraft") == ["gaming"]
    assert set(get_site_types("Twitch")) == {"gaming", "social"}
    assert get_site_types("UnknownOtherPlatform") == []

    findings = [
        Finding("Instagram", "u", "https://instagram.com/u", Status.FOUND, "ok"),
        Finding("GitHub", "u", "https://github.com/u", Status.FOUND, "ok"),
        Finding("Minecraft", "u", "https://minecraft.net/u", Status.NOT_FOUND, "404"),
        Finding("Wikipedia", "u", "https://en.wikipedia.org/wiki/User:u", Status.NOT_FOUND, "404"),
    ]
    html_doc = render_html(make_report("username", "u", findings))
    assert 'data-site-types="social"' in html_doc
    assert 'data-site-types="programming"' in html_doc
    assert 'data-site-types="gaming"' in html_doc
    assert 'data-site-types=""' in html_doc


@pytest.mark.parametrize("argv,expected", [
    (["--help"], ["find", "config", "open", "clean"]),
    (["find", "--help"], ["--no-html", "--html-dir", "--open"]),
    (["config", "--help"], ["--html-dir", "--show", "--reset"]),
    (["open", "--help"], ["--html-dir", "--print-path"]),
    (["clean", "--help"], ["--all", "--html-dir", "--dry-run"]),
])
def test_cli_help_documents_html_commands_and_options(argv, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for token in expected:
        assert token in help_text


def test_clean_cli_deletes_single_multiple_and_all_html_files(capsys):
    html_dir = get_html_output_dir()
    html_dir.mkdir(parents=True, exist_ok=True)
    f1 = html_dir / "one.html"
    f2 = html_dir / "two.html"
    f3 = html_dir / "three.html"
    f4 = html_dir / "four.html"
    keep_txt = html_dir / "notes.txt"
    for item in (f1, f2, f3, f4, keep_txt):
        item.write_text("data", encoding="utf-8")

    # Delete 1 file by filename
    assert main(["clean", "one.html"]) == 0
    single = json.loads(capsys.readouterr().out)
    assert single["count"] == 1
    assert not f1.exists()
    assert f2.exists()

    # Delete multiple files (mix of filename and full path inside html_dir)
    assert main(["clean", "two.html", str(f3)]) == 0
    multi = json.loads(capsys.readouterr().out)
    assert multi["count"] == 2
    assert not f2.exists() and not f3.exists()
    assert f4.exists()

    # Dry run preserves remaining file
    assert main(["clean", "--all", "--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["dry_run"] is True
    assert dry["count"] == 1
    assert f4.exists()

    # Delete all remaining HTML files without touching non-HTML files
    assert main(["clean", "--all"]) == 0
    cleared = json.loads(capsys.readouterr().out)
    assert cleared["count"] == 1
    assert not f4.exists()
    assert keep_txt.exists()

    # Clean --all on empty folder succeeds with count 0
    assert main(["clean", "--all"]) == 0
    empty_res = json.loads(capsys.readouterr().out)
    assert empty_res["count"] == 0


def test_clean_cli_rejects_unsafe_paths_and_invalid_usage(tmp_path, capsys):
    html_dir = get_html_output_dir()
    html_dir.mkdir(parents=True, exist_ok=True)
    valid = html_dir / "valid.html"
    non_html = html_dir / "config.json"
    outside = tmp_path / "outside.html"
    for item in (valid, non_html, outside):
        item.write_text("x", encoding="utf-8")

    # Path traversal / outside folder rejected
    assert main(["clean", str(outside)]) == 2
    assert "outside" in capsys.readouterr().err
    assert outside.exists()

    # Non-HTML file rejected
    assert main(["clean", "config.json"]) == 2
    assert "Only .html" in capsys.readouterr().err
    assert non_html.exists()

    # Atomic pre-validation: missing second file prevents deleting first file
    assert main(["clean", "valid.html", "missing.html"]) == 2
    assert "not found" in capsys.readouterr().err
    assert valid.exists()

    # Invalid flag combinations
    with pytest.raises(SystemExit) as exc1:
        main(["clean"])
    assert exc1.value.code == 2

    with pytest.raises(SystemExit) as exc2:
        main(["clean", "valid.html", "--all"])
    assert exc2.value.code == 2

    # Missing HTML directory
    assert main(["clean", "--all", "--html-dir", str(tmp_path / "missing-dir")]) == 2
    assert "does not exist" in capsys.readouterr().err
