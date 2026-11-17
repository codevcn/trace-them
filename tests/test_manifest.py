"""Legacy manifest compatibility and public-profile policy regression tests."""
import json
from importlib.resources import files

import pytest
from jsonschema import validate

from trace_them.manifest import load_manifest


def test_manifest_matches_shipped_schema():
    resources = files('trace_them').joinpath('resources')
    data = json.loads(resources.joinpath('data.json').read_text(encoding='utf-8'))
    schema = json.loads(resources.joinpath('data.schema.json').read_text(encoding='utf-8'))
    validate(instance=data, schema=schema)
    assert len([key for key in data if not key.startswith('$')]) == 481


def test_default_manifest_uses_local_data_without_network():
    manifest = load_manifest()
    assert manifest.sites
    assert manifest.source
    assert manifest.sites['GitHub']['errorType'] == 'status_code'
    assert manifest.sites['GitLab']['errorType'] == 'message'


@pytest.mark.parametrize('target', ['Discord', 'Holopin', 'minds', 'dailykos', 'BoardGameGeek'])
def test_auth_enumeration_policy_cannot_be_overridden_by_selection(target):
    manifest = load_manifest(include_nsfw=True, sites=[target])
    assert target not in manifest.sites
    assert target in manifest.skipped
    assert manifest.skipped[target]


def test_nsfw_filtered_by_default_and_can_be_explicitly_enabled():
    default = load_manifest()
    expanded = load_manifest(include_nsfw=True)
    assert 'Xvideos' not in default.sites
    assert 'Xvideos' in expanded.sites


def test_site_selection_is_case_insensitive():
    manifest = load_manifest(sites=['github'])
    assert list(manifest.sites) == ['GitHub']


def test_custom_legacy_manifest_supported(tmp_path, site):
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps({'Fixture': site}), encoding='utf-8')
    manifest = load_manifest(str(path), offline=True)
    assert manifest.sites == {'Fixture': site}


@pytest.mark.parametrize('change', [
    {'url': 'file:///etc/passwd'},
    {'url': 'https://user:password@example.com/{}'},
    {'regexCheck': '['},
    {'errorType': 'bogus'},
    {'request_method': 'DELETE'},
    {'errorType': 'message'},
])
def test_malformed_target_is_rejected_with_context(tmp_path, site, change):
    site.update(change)
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps({'Fixture': site}), encoding='utf-8')
    with pytest.raises(ValueError, match='Fixture'):
        load_manifest(str(path))


def test_non_object_manifest_rejected(tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError):
        load_manifest(str(path))


def test_offline_remote_manifest_rejected_without_request(queued_http):
    with pytest.raises((ValueError, RuntimeError)):
        load_manifest('https://example.com/manifest.json', offline=True)
    assert not queued_http[1]


def test_custom_auth_endpoint_cannot_bypass_policy_under_another_name(tmp_path, site):
    site['urlProbe'] = 'https://example.com/api/auth/username'
    path = tmp_path / 'custom.json'
    path.write_text(json.dumps({'Innocent label': site}), encoding='utf-8')
    manifest = load_manifest(str(path))
    assert not manifest.sites
    assert 'Innocent label' in manifest.skipped


@pytest.mark.parametrize('path', ['/%72egister/%76alidate?username={}',
                                 '/%2572egister/%2576alidate?username={}'])
def test_percent_encoded_auth_paths_cannot_bypass_policy(tmp_path, site, path):
    site['urlProbe'] = 'https://example.com' + path
    resource = tmp_path / 'custom.json'
    resource.write_text(json.dumps({'Fixture': site}), encoding='utf-8')
    manifest = load_manifest(str(resource))
    assert not manifest.sites
    assert 'Fixture' in manifest.skipped
