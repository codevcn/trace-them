"""Scanner regression and identity separation tests."""
from copy import deepcopy
from threading import Event

from trace_them.engine import Scanner
from trace_them.models import Candidate, Evidence, Status
from trace_them.transport import HTTPTransport, RequestBudget


def test_invalid_username_consumes_no_budget(site, queued_http):
    site['regexCheck'] = '^[a-z]{3,10}$'
    budget = RequestBudget(5)
    with HTTPTransport(budget) as transport:
        findings = Scanner(transport).scan('*#$', {'Fixture': site})
    assert findings[0].status is Status.INVALID
    assert budget.used == 0
    assert not queued_http[1]


def test_scanner_does_not_mutate_manifest(site, queued_http):
    data = {'Fixture': site}
    original = deepcopy(data)
    queued_http[0].append(200)
    with HTTPTransport(RequestBudget(3), per_domain_interval=0) as transport:
        findings = Scanner(transport).scan('fixture', data)
    assert data == original
    assert findings[0].status is Status.FOUND
    assert findings[0].evidence
    assert findings[0].observed_at


def test_same_handle_never_transfers_email_association(site, queued_http):
    evidence = Evidence('public_email_link', 'https://example.com/source', 'Source identifies GitHub fixture')
    candidate = Candidate('fixture', origin='public_profile_username', evidence=[evidence], platform='GitHub')
    queued_http[0].append(200)
    with HTTPTransport(RequestBudget(3), per_domain_interval=0) as transport:
        finding = Scanner(transport).scan('fixture', {'Reddit': site}, candidate=candidate)[0]
    assert finding.status is Status.FOUND
    assert finding.association == 'unverified'
    assert not finding.association_evidence


def test_inferred_candidate_stays_inferred(site, queued_http):
    evidence = Evidence('inferred', 'email_local_part', 'Derived from fixture@example.com')
    candidate = Candidate('fixture', origin='email_local_part', evidence=[evidence])
    queued_http[0].append(200)
    with HTTPTransport(RequestBudget(3), per_domain_interval=0) as transport:
        finding = Scanner(transport).scan('fixture', {'Fixture': site}, candidate=candidate)[0]
    assert finding.association == 'unverified'
    assert any(item.kind.endswith('inferred') for item in finding.evidence)


def test_empty_target_set_returns_empty_list():
    with HTTPTransport(RequestBudget(1), offline=True) as transport:
        assert Scanner(transport).scan('fixture', {}) == []


def test_offline_findings_are_not_fake_absence(site, queued_http):
    budget = RequestBudget(5)
    with HTTPTransport(budget, offline=True) as transport:
        findings = Scanner(transport).scan('fixture', {'Fixture': site})
    assert findings[0].status in {Status.UNKNOWN, Status.UNSUPPORTED}
    assert findings[0].reason
    assert not queued_http[1]
    assert budget.used == 0


def test_budget_exhaustion_is_reported_for_unchecked_targets(site, queued_http):
    queued_http[0].append(200)
    budget = RequestBudget(1)
    with HTTPTransport(budget, per_domain_interval=0) as transport:
        findings = Scanner(transport, max_workers=1).scan('fixture', {'One': site, 'Two': site})
    assert len(findings) == 2
    assert {f.status for f in findings} == {Status.FOUND, Status.BUDGET_EXHAUSTED}


def test_cancelled_scans_preserve_status_without_network(site, queued_http):
    cancelled = Event()
    cancelled.set()
    with HTTPTransport(RequestBudget(5), cancel_event=cancelled) as transport:
        findings = Scanner(transport).scan('fixture', {'One': site, 'Two': site})
    assert len(findings) == 2
    assert all(finding.status is Status.CANCELLED for finding in findings)
    assert not queued_http[1]
