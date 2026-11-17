"""Apify wrapper integration uses mocked subprocesses and canonical JSON."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from trace_them.reporting import make_report


@pytest.fixture
def actor_module():
    path = Path('.actor/run_actor.py')
    assert path.is_file(), 'Apify Python wrapper must exist'
    spec = importlib.util.spec_from_file_location('trace_them_actor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actor_builds_argument_array_without_shell_interpretation(actor_module):
    command = actor_module.build_command({'usernames': ['fixture', '--help', '$(touch bad)']})
    assert command[:2] == ['trace-them', 'find']
    assert '--username=fixture' in command
    assert '--username=--help' in command
    assert '--username=$(touch bad)' in command
    assert '--quiet' in command


def test_actor_email_and_candidate_options_are_explicit(actor_module):
    command = actor_module.build_command({'email': 'fixture@example.com', 'candidates': True,
                                         'sites': ['GitHub'], 'maxRequests': 5, 'offline': True})
    assert '--email=fixture@example.com' in command
    assert '--candidates' in command
    assert '--offline' in command
    assert any('GitHub' in value for value in command)
    assert '5' in command or any(value.endswith('=5') for value in command)


@pytest.mark.parametrize('data', [{}, {'usernames': []}, {'usernames': 'fixture'},
                                  {'usernames': ['']}, {'email': 'fixture@example.com', 'usernames': ['fixture']},
                                  {'email': 'fixture@example.com', 'maxRequests': -1},
                                  {'email': 'fixture@example.com', 'offline': 'yes'},
                                  {'email': 'fixture@example.com', 'candidates': 'true'}])
def test_invalid_actor_input_is_rejected(actor_module, data):
    with pytest.raises(ValueError):
        actor_module.build_command(data)


def test_actor_pushes_exact_canonical_report_without_parsing_txt(actor_module):
    report = make_report('username', 'fixture', [])
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        assert not kwargs.get('shell', False)
        stdout = json.dumps(report) if command[0] == 'trace-them' else ''
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

    result = actor_module.run_actor({'usernames': ['fixture']}, runner=runner)
    assert result == report
    assert calls[0][0][0] == 'trace-them'
    assert calls[1][0] == ['apify', 'actor', 'push-data']
    assert json.loads(calls[1][1]['input']) == report


def test_actor_reads_input_then_scans_then_pushes(actor_module):
    report = make_report('email', 'fixture@example.com', [])
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command == ['apify', 'actor', 'get-input']:
            stdout = json.dumps({'email': 'fixture@example.com'})
        elif command[0] == 'trace-them':
            stdout = json.dumps(report)
        else:
            stdout = ''
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')

    assert actor_module.run_actor(runner=runner) == report
    assert len(calls) == 3


def test_actor_scan_failure_never_pushes_partial_data(actor_module):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(2, command, output='', stderr='fixture failure')

    with pytest.raises(subprocess.CalledProcessError):
        actor_module.run_actor({'usernames': ['fixture']}, runner=runner)
    assert len(calls) == 1


def test_actor_configuration_is_valid_json():
    for name in ('actor.json', 'input_schema.json', 'dataset_schema.json'):
        data = json.loads(Path('.actor', name).read_text(encoding='utf-8'))
        assert isinstance(data, dict)
