"""Unicode failures become explicit errors, preserving legacy regression intent."""
import pytest
import requests

from trace_them.engine import Scanner
from trace_them.models import Status
from trace_them.transport import HTTPTransport, RequestBudget


@pytest.mark.parametrize('error', [
    UnicodeDecodeError('utf-8', b'\xe9', 0, 1, 'invalid continuation byte'),
    UnicodeEncodeError('ascii', 'É', 0, 1, 'ordinal not in range'),
    requests.Timeout('fixture timeout'), requests.ConnectionError('fixture connection'),
])
def test_network_encoding_and_connection_errors_become_findings(queued_http, site, error):
    pending, _ = queued_http
    pending.append(error)
    with HTTPTransport(RequestBudget(5), retries=0, per_domain_interval=0) as transport:
        results = Scanner(transport, max_workers=1).scan('Émile', {'Fixture': site})
    assert len(results) == 1
    assert results[0].status is Status.ERROR
    assert results[0].reason


def test_unicode_username_is_percent_encoded(queued_http, site):
    pending, calls = queued_http
    pending.append(200)
    with HTTPTransport(RequestBudget(5), retries=0, per_domain_interval=0) as transport:
        Scanner(transport, max_workers=1).scan('Émile', {'Fixture': site})
    assert '%C3%89mile' in calls[0][0].url
