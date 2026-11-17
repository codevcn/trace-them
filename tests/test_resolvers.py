"""Email is source-scoped data, never a global identity assertion."""
import hashlib
import json

import pytest
import requests

from trace_them.models import Status
from trace_them.resolvers import GravatarResolver, email_candidates, validate_email
from trace_them.transport import HTTPTransport, RequestBudget


EMAIL = 'Fixture.Name@example.com'


def public_profile(email=EMAIL):
    return {'hash': hashlib.sha256(email.lower().encode()).hexdigest(),
            'profile_url': 'https://gravatar.com/fixture-name', 'display_name': 'Fixture'}


def test_email_normalization_preserves_local_part():
    assert validate_email(' Fixture.Name+tag@EXAMPLE.COM ') == 'Fixture.Name+tag@example.com'
    assert validate_email('fixture@bücher.example') == 'fixture@xn--bcher-kva.example'


@pytest.mark.parametrize('value', ['missing-at', 'a@@example.com', '.a@example.com',
                                  'a..b@example.com', 'a.@example.com', 'a@example',
                                  'a@-example.com', 'a\nb@example.com', '"a b"@example.com'])
def test_invalid_email_is_rejected(value):
    with pytest.raises(ValueError):
        validate_email(value)


def test_candidates_are_bounded_deduplicated_and_inferred():
    candidates = email_candidates('fixture.name@example.com', limit=3)
    assert len(candidates) <= 3
    assert len({candidate.username for candidate in candidates}) == len(candidates)
    assert candidates[0].username == 'fixture.name'
    assert all(candidate.origin == 'email_local_part' for candidate in candidates)
    assert all(candidate.evidence[0].kind == 'inferred' for candidate in candidates)


@pytest.mark.parametrize('limit', [0, 11, -1])
def test_candidate_limits_are_validated(limit):
    with pytest.raises(ValueError):
        email_candidates(EMAIL, limit=limit)


def test_public_profile_has_source_scoped_association(queued_http, response_factory):
    pending, calls = queued_http
    pending.append(response_factory(text=json.dumps(public_profile())))
    budget = RequestBudget(5)
    with HTTPTransport(budget, retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    digest = hashlib.sha256(EMAIL.lower().encode()).hexdigest()
    assert result.status is Status.FOUND
    assert calls[0][0].url == f'https://api.gravatar.com/v3/profiles/{digest}'
    assert EMAIL not in calls[0][0].url
    finding = result.findings[0]
    assert finding.platform == 'Gravatar'
    assert finding.association == 'source_reported'
    assert finding.association_evidence
    assert finding.identifier == digest
    assert result.candidates[0].platform == 'Gravatar'
    assert 'confidence' not in result.to_dict()


@pytest.mark.parametrize('code,expected', [(404, Status.NOT_FOUND), (429, Status.RATE_LIMITED),
                                         (401, Status.MISSING_CONFIG), (403, Status.BLOCKED),
                                         (500, Status.ERROR)])
def test_provider_status_is_explicit_and_scoped(queued_http, response_factory, code, expected):
    queued_http[0].append(response_factory(code))
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is expected
    assert result.findings == []
    assert result.reason
    if code == 404:
        assert 'Gravatar' in result.reason
        assert 'unknown' in result.reason.lower()


@pytest.mark.parametrize('change', [{'hash': 'different'}, {'hash': None},
                                  {'profile_url': 'https://evil.example/fixture'},
                                  {'profile_url': 'https://gravatar.com/one/two'},
                                  {'profile_url': 'javascript:alert(1)'}])
def test_unsafe_or_mismatched_profile_is_not_association(queued_http, response_factory, change):
    data = public_profile()
    data.update(change)
    queued_http[0].append(response_factory(text=json.dumps(data)))
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is Status.UNKNOWN
    assert not result.findings


def test_provider_malformed_json_is_error(queued_http, response_factory):
    queued_http[0].append(response_factory(text='invalid json'))
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is Status.ERROR
    assert not result.findings


def test_offline_resolution_makes_no_request(queued_http):
    budget = RequestBudget(3)
    with HTTPTransport(budget, offline=True) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is Status.UNSUPPORTED
    assert not result.findings
    assert budget.used == 0
    assert not queued_http[1]


def test_resolution_shares_run_budget(queued_http):
    with HTTPTransport(RequestBudget(0)) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is Status.BUDGET_EXHAUSTED
    assert not queued_http[1]


def test_provider_connection_failure_never_means_no_account(queued_http):
    queued_http[0].append(requests.ConnectionError('fixture'))
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status is Status.ERROR
    assert not result.findings


def test_retry_after_server_failure_does_not_become_email_absence(queued_http, response_factory):
    queued_http[0].append(response_factory(503, headers={'Retry-After': '99999'}))
    with HTTPTransport(RequestBudget(3), retries=1, max_retry_after=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert result.status in {Status.ERROR, Status.RATE_LIMITED}
    assert not result.findings


def test_gravatar_redirect_is_not_followed_to_external_profile(queued_http, response_factory):
    queued_http[0].append(response_factory(302, headers={'Location': 'https://external.example/profile'}))
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        result = GravatarResolver(transport).resolve(EMAIL)
    assert len(queued_http[1]) == 1
    assert result.status is Status.UNKNOWN
    assert not result.findings


def test_valid_profile_payload_from_wrong_final_source_is_rejected(response_factory):
    response = response_factory(text=json.dumps(public_profile()), url='https://unrelated.example/result')

    class Transport:
        def request(self, method, url, **kwargs):
            assert kwargs['allow_redirects'] is False
            return response

    result = GravatarResolver(Transport()).resolve(EMAIL)
    assert result.status is Status.UNKNOWN
    assert not result.findings
