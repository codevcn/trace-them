"""CLI behavior from user-visible JSON, stderr and files."""
import hashlib
import json
import os
import subprocess
import sys

import pytest

from trace_them.cli import main


@pytest.mark.parametrize('args', [[], ['find'], ['find', '--username', 'x', '--email', 'x@example.com'],
                                 ['find', '--username', 'x', '--candidates'],
                                 ['find', '--username', ''], ['find', '--email', 'invalid'],
                                 ['find', '--username', 'x', '--timeout', 'nan'],
                                 ['find', '--username', 'x', '--workers', '0'],
                                 ['find', '--email', 'x@example.com', '--candidate-limit', '100'],
                                 ['find', '--email', 'x@example.com', '--site', 'GitHub'],
                                 ['find', '--email', 'x@example.com', '--manifest', 'custom.json'],
                                 ['find', '--email', 'x@example.com', '--nsfw']])
def test_invalid_usage_fails_before_network(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_offline_username_outputs_json_and_stderr_progress(capsys):
    assert main(['find', '--username', 'fixture', '--site', 'GitHub', '--offline']) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['input'] == {'type': 'username', 'value': 'fixture'}
    assert report['request_budget']['used'] == 0
    assert report['findings'][0]['status'] == 'unknown'
    assert 'Planned' in output.err


def test_quiet_suppresses_progress_and_keeps_json(capsys):
    assert main(['find', '--username', 'fixture', '--site', 'GitHub', '--offline', '--quiet']) == 0
    output = capsys.readouterr()
    assert output.err == ''
    assert json.loads(output.out)['schema_version'] == '1.0'


def test_local_alias_is_fully_offline(capsys):
    assert main(['find', '--username', 'fixture', '--site', 'GitHub', '--local']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['request_budget']['used'] == 0


def test_offline_email_has_explicit_unsupported_resolution(capsys):
    assert main(['find', '--email', 'fixture@example.com', '--offline']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['resolutions'][0]['status'] == 'unsupported'
    assert report['findings'] == []
    assert report['request_budget']['used'] == 0


def test_email_lookup_does_not_automatically_scan_any_username(queued_http, response_factory, capsys):
    email = 'fixture@example.com'
    data = {'hash': hashlib.sha256(email.encode()).hexdigest(), 'profile_url': 'https://gravatar.com/fixture'}
    queued_http[0].append(response_factory(text=json.dumps(data)))
    assert main(['find', '--email', email, '--retries', '0']) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(queued_http[1]) == 1
    assert report['manifest']['source'] is None
    assert len(report['findings']) == 1
    assert report['findings'][0]['platform'] == 'Gravatar'
    assert report['findings'][0]['association'] == 'source_reported'


def test_candidate_expansion_is_bounded_and_shares_resolver_budget(queued_http, response_factory, capsys):
    queued_http[0].append(response_factory(404))
    args = ['find', '--email', 'fixture.name@example.com', '--candidates', '--candidate-limit', '2',
            '--site', 'GitHub', '--max-requests', '1', '--retries', '0', '--domain-interval', '0']
    assert main(args) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert len(report['candidates']) == 2
    assert report['request_budget']['used'] == len(queued_http[1]) == 1
    assert {item['status'] for item in report['findings']} <= {'invalid', 'budget_exhausted'}
    assert any(item['status'] == 'budget_exhausted' for item in report['findings'])
    assert all(item['association'] == 'unverified' for item in report['findings'])
    assert '2 username(s)' in output.err


def test_explicit_wildcard_keeps_legacy_three_variants(capsys):
    args = ['find', '--username', 'test{?}test', '--site', 'GitHub', '--offline']
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert [item['username'] for item in report['candidates']] == ['test_test', 'test-test', 'test.test']
    assert all(item['origin'] == 'explicit_pattern' for item in report['candidates'])


def test_repeated_usernames_are_deduplicated(capsys):
    assert main(['find', '--username', 'fixture', '--username', 'fixture', '--site', 'GitHub', '--offline']) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report['findings']) == len(report['candidates']) == 1


def test_all_output_formats_use_requested_directory(tmp_path, capsys):
    json_path = tmp_path / 'explicit.json'
    output_dir = tmp_path / 'exports'
    args = ['find', '--username', '../../fixture', '--site', 'GitHub', '--offline',
            '--json', str(json_path), '--txt', '--csv', '--xlsx', '--output-dir', str(output_dir)]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert json.loads(json_path.read_text(encoding='utf-8')) == report
    exports = list(output_dir.iterdir())
    assert {path.suffix for path in exports} == {'.txt', '.csv', '.xlsx'}
    assert all(path.resolve().parent == output_dir.resolve() for path in exports)


def test_auth_target_selection_cannot_reenable_endpoint(capsys):
    assert main(['find', '--username', 'fixture', '--site', 'Discord', '--offline']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['findings'] == []
    assert 'Discord' in report['manifest']['skipped']


def test_no_advertising_or_update_request_in_default_cli(capsys):
    assert main(['find', '--username', 'fixture', '--site', 'GitHub', '--offline']) == 0
    output = capsys.readouterr()
    assert 'OSINTSearch' not in output.out + output.err
    assert 'Update available' not in output.out + output.err


def test_non_ascii_username_survives_legacy_windows_stdout_encoding():
    environment = dict(os.environ, PYTHONIOENCODING='cp1252')
    username = 'Émile漢字'
    completed = subprocess.run(
        [sys.executable, '-m', 'trace_them', 'find', '--username', username,
         '--site', 'GitHub', '--offline'],
        capture_output=True, text=True, encoding='cp1252', env=environment, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report['input']['value'] == username
    assert report['findings'][0]['username'] == username
    assert report['request_budget']['used'] == 0
