"""Artifact contract checks complement the lead's installed-wheel smoke tests."""
from email.parser import Parser
from pathlib import Path
import zipfile

import pytest


def test_built_wheel_contains_runtime_resources_and_only_new_package():
    wheels = sorted(Path('dist').glob('trace_them-*.whl'))
    if not wheels:
        pytest.skip('Build a wheel to run artifact-content verification.')
    with zipfile.ZipFile(wheels[-1]) as wheel:
        names = set(wheel.namelist())
        assert 'trace_them/__main__.py' in names
        assert 'trace_them/resources/data.json' in names
        assert 'trace_them/resources/data.schema.json' in names
        assert 'trace_them/resources/report.schema.json' in names
        assert 'trace_them/resources/source-policy.json' in names
        assert not any(name.startswith('sherlock_project/') for name in names)
        metadata_name = next(name for name in names if name.endswith('.dist-info/METADATA'))
        metadata = Parser().parsestr(wheel.read(metadata_name).decode('utf-8'))
        assert metadata['Name'] == 'trace-them'
        assert '>=3.10' in metadata['Requires-Python']
        entry_name = next(name for name in names if name.endswith('.dist-info/entry_points.txt'))
        entry = wheel.read(entry_name).decode('utf-8')
        assert 'trace-them=trace_them.cli:main' in entry.replace(' ', '')
        for name in names:
            if name.startswith('trace_them/') and not name.endswith('/'):
                source = Path(name)
                assert source.is_file(), f'Unexpected runtime file in wheel: {name}'
                assert wheel.read(name) == source.read_bytes(), f'Rebuild stale wheel: {name}'
