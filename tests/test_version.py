"""Installed and module entry points must use the new brand."""
from pathlib import Path
import subprocess
import sys

import trace_them


def test_module_version_matches_package_version():
    run = subprocess.run([sys.executable, '-m', 'trace_them', '--version'],
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert trace_them.__version__ in run.stdout
    assert 'Trace Them' in run.stdout


def test_packaging_declares_new_cli_and_package():
    text = Path('pyproject.toml').read_text(encoding='utf-8')
    assert 'trace-them' in text
    assert 'trace_them' in text
    assert 'sherlock_project.sherlock:main' not in text
