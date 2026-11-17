"""Offline sweeping validation replaces unbounded live manifest sweeps."""
import json
from importlib.resources import files
from urllib.parse import urlsplit

import pytest

from trace_them.manifest import load_manifest


@pytest.mark.validate_targets
def test_all_original_targets_are_accounted_for():
    data = json.loads(files('trace_them').joinpath('resources/data.json').read_text(encoding='utf-8'))
    names = {name for name in data if not name.startswith('$')}
    manifest = load_manifest(include_nsfw=True)
    assert set(manifest.sites) | set(manifest.skipped) == names
    assert not set(manifest.sites) & set(manifest.skipped)


@pytest.mark.validate_targets
def test_active_manifest_only_uses_http_profile_locations():
    manifest = load_manifest(include_nsfw=True)
    for name, site in manifest.sites.items():
        for key in ('url', 'urlMain', 'urlProbe'):
            if key in site:
                parsed = urlsplit(site[key])
                assert parsed.scheme in {'http', 'https'}, (name, key)
                assert parsed.hostname, (name, key)
                assert not parsed.username and not parsed.password, (name, key)


@pytest.mark.validate_targets
def test_manifest_profile_policy_removes_known_auth_lookup_paths():
    manifest = load_manifest(include_nsfw=True)
    forbidden = ('username-attempt', '/api/auth/username', '/register/validate', '/signup/check_nickname')
    for name, site in manifest.sites.items():
        probe = site.get('urlProbe', site['url']).lower()
        assert not any(part in probe for part in forbidden), name
