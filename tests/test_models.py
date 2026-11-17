from trace_them.models import Evidence, Finding, Status


def test_findings_serialize_explicit_status_and_evidence():
    finding = Finding('Fixture', 'handle', 'https://example.com/handle', Status.FOUND,
                      'Public profile responded', evidence=[Evidence('http_response', 'https://example.com', 'HTTP 200')])
    data = finding.to_dict()
    assert data['status'] == 'found'
    assert data['association'] == 'unverified'
    assert data['association_evidence'] == []
    assert data['evidence'][0]['observed_at']
    assert 'confidence' not in data


def test_status_vocabulary_distinguishes_failure_and_absence():
    assert len({Status.FOUND.value, Status.NOT_FOUND.value, Status.INVALID.value,
                Status.BLOCKED.value, Status.RATE_LIMITED.value, Status.ERROR.value,
                Status.UNKNOWN.value, Status.UNSUPPORTED.value,
                Status.BUDGET_EXHAUSTED.value, Status.CANCELLED.value}) == 10
