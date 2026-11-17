"""Shared request accounting and lifecycle tests at the HTTP send boundary."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import io

import pytest
import requests

from trace_them.transport import (
    BudgetExceeded, HTTPTransport, OfflineError, RequestBudget, RetryDeferred, ScanCancelled,
)

ORIGINAL_SESSION_SEND = requests.Session.send


def test_single_actual_attempt_counts_budget_and_timeout(queued_http):
    pending, calls = queued_http
    pending.append(200)
    budget = RequestBudget(3)
    with HTTPTransport(budget, timeout=(2, 7), per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/u/test')
    assert response.status_code == 200
    assert budget.used == 1
    assert budget.remaining == 2
    assert calls[0][1]['timeout'] == (2, 7)


def test_budget_prevents_extra_actual_send(queued_http):
    pending, calls = queued_http
    pending.extend([200, 200])
    budget = RequestBudget(1)
    with HTTPTransport(budget, per_domain_interval=0) as transport:
        transport.request('GET', 'https://example.com/first')
        with pytest.raises(BudgetExceeded):
            transport.request('GET', 'https://example.com/second')
    assert len(calls) == budget.used == 1


def test_redirect_hop_consumes_separate_budget(queued_http, response_factory):
    pending, calls = queued_http
    pending.extend([response_factory(302, headers={'Location': '/final'}), response_factory()])
    budget = RequestBudget(2)
    with HTTPTransport(budget, retries=0, per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/start')
    assert response.status_code == 200
    assert len(calls) == budget.used == 2
    assert calls[1][0].url == 'https://example.com/final'


def test_redirect_cannot_bypass_request_budget(queued_http, response_factory):
    pending, calls = queued_http
    pending.append(response_factory(302, headers={'Location': '/final'}))
    with HTTPTransport(RequestBudget(1), retries=0, per_domain_interval=0) as transport:
        with pytest.raises(BudgetExceeded):
            transport.request('GET', 'https://example.com/start')
    assert len(calls) == 1


def test_redirect_disabled_for_response_url_probe(queued_http, response_factory):
    pending, calls = queued_http
    pending.append(response_factory(302, headers={'Location': '/missing'}))
    with HTTPTransport(RequestBudget(3), per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/start', allow_redirects=False)
    assert response.status_code == 302
    assert len(calls) == 1


@pytest.mark.parametrize('code', [429, 503])
def test_retry_consumes_shared_budget(queued_http, response_factory, code):
    pending, calls = queued_http
    pending.extend([response_factory(code, headers={'Retry-After': '0'}), response_factory()])
    budget = RequestBudget(2)
    with HTTPTransport(budget, retries=1, per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/test')
    assert response.status_code == 200
    assert len(calls) == budget.used == 2


def test_retries_stop_at_configured_limit(queued_http, response_factory):
    pending, calls = queued_http
    pending.extend([response_factory(429, headers={'Retry-After': '0'}) for _ in range(3)])
    budget = RequestBudget(10)
    with HTTPTransport(budget, retries=1, per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/test')
    assert response.status_code == 429
    assert len(calls) == budget.used == 2


def test_offline_never_attempts_network(queued_http):
    _, calls = queued_http
    budget = RequestBudget(10)
    with HTTPTransport(budget, offline=True) as transport:
        with pytest.raises(OfflineError):
            transport.request('GET', 'https://example.com/test')
    assert budget.used == 0
    assert not calls


def test_already_cancelled_never_attempts_network(queued_http):
    _, calls = queued_http
    cancelled = Event()
    cancelled.set()
    budget = RequestBudget(10)
    with HTTPTransport(budget, cancel_event=cancelled) as transport:
        with pytest.raises(ScanCancelled):
            transport.request('GET', 'https://example.com/test')
    assert budget.used == 0
    assert not calls


def test_request_budget_is_thread_safe(queued_http):
    pending, calls = queued_http
    pending.extend([200] * 5)
    budget = RequestBudget(5)
    with HTTPTransport(budget, per_domain_interval=0) as transport:
        def send(index):
            try:
                transport.request('GET', f'https://example.com/{index}')
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(send, range(30)))
    assert sum(results) == len(calls) == budget.used == 5


def test_context_manager_closes_sessions(monkeypatch, queued_http):
    import requests
    closed = []
    original_close = requests.Session.close

    def close(session):
        closed.append(session)
        original_close(session)

    monkeypatch.setattr(requests.Session, 'close', close)
    queued_http[0].append(200)
    with HTTPTransport(RequestBudget(1), per_domain_interval=0) as transport:
        transport.request('GET', 'https://example.com/test')
    assert closed


def test_retry_after_above_bound_is_deferred_without_sleep(queued_http, response_factory):
    pending, calls = queued_http
    pending.append(response_factory(429, headers={'Retry-After': '99999'}))
    with HTTPTransport(RequestBudget(3), retries=1, max_retry_after=0, per_domain_interval=0) as transport:
        with pytest.raises(RetryDeferred) as error:
            transport.request('GET', 'https://example.com/test')
    assert error.value.response.status_code == 429
    assert len(calls) == 1


def test_same_parent_domain_is_paced_without_real_sleep(monkeypatch, queued_http):
    import trace_them.transport as module
    clock = [0.0]
    waits = []

    class ClockEvent:
        cancelled = False

        def is_set(self):
            return self.cancelled

        def wait(self, delay):
            waits.append(delay)
            clock[0] += delay
            return False

        def set(self):
            self.cancelled = True

    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    queued_http[0].extend([200, 200, 200])
    with HTTPTransport(RequestBudget(3), per_domain_interval=0.25, cancel_event=ClockEvent()) as transport:
        transport.request('GET', 'https://www.example.com/first')
        transport.request('GET', 'https://api.example.com/second')
        transport.request('GET', 'https://unrelated.test/third')
    assert sum(waits) >= 0.25
    assert len(queued_http[1]) == 3


def test_cancellation_interrupts_retry_wait(queued_http, response_factory):
    cancelled = Event()

    def cancel_on_wait(delay):
        cancelled.set()
        return True

    cancelled.wait = cancel_on_wait
    queued_http[0].append(response_factory(429, headers={'Retry-After': '1'}))
    with HTTPTransport(RequestBudget(3), retries=1, cancel_event=cancelled, per_domain_interval=0) as transport:
        with pytest.raises(ScanCancelled):
            transport.request('GET', 'https://example.com/test')
    assert len(queued_http[1]) == 1


def test_cross_origin_redirect_drops_explicit_credentials(queued_http, response_factory):
    pending, calls = queued_http
    pending.extend([response_factory(302, headers={'Location': 'https://different.test/final'}), response_factory()])
    headers = {'Authorization': 'Bearer fixture-secret', 'Cookie': 'session=fixture', 'Host': 'example.com'}
    with HTTPTransport(RequestBudget(3), retries=0, per_domain_interval=0) as transport:
        transport.request('GET', 'https://example.com/start', headers=headers)
    assert calls[0][0].headers['Authorization'] == 'Bearer fixture-secret'
    assert 'Authorization' not in calls[1][0].headers
    assert 'Cookie' not in calls[1][0].headers
    assert 'Host' not in calls[1][0].headers


def test_redirect_loop_has_finite_hop_limit(queued_http, response_factory):
    import requests
    queued_http[0].extend([response_factory(302, headers={'Location': '/again'}) for _ in range(10)])
    budget = RequestBudget(10)
    with HTTPTransport(budget, retries=0, per_domain_interval=0) as transport:
        with pytest.raises(requests.TooManyRedirects):
            transport.request('GET', 'https://example.com/start')
    assert len(queued_http[1]) <= 6
    assert budget.used == len(queued_http[1])


def test_oversized_response_is_error_and_not_retried(queued_http, response_factory):
    import requests
    queued_http[0].append(response_factory(text='x' * (2 * 1024 * 1024 + 1)))
    with HTTPTransport(RequestBudget(3), retries=1, per_domain_interval=0) as transport:
        with pytest.raises(requests.exceptions.ContentDecodingError):
            transport.request('GET', 'https://example.com/huge')
    assert len(queued_http[1]) == 1


def test_closed_transport_cannot_send_more_requests(queued_http):
    transport = HTTPTransport(RequestBudget(3))
    transport.close()
    with pytest.raises(ScanCancelled):
        transport.request('GET', 'https://example.com/test')
    assert not queued_http[1]


def test_invalid_protocol_consumes_no_budget(queued_http):
    import requests
    budget = RequestBudget(3)
    with HTTPTransport(budget) as transport:
        with pytest.raises(requests.exceptions.InvalidURL):
            transport.request('GET', 'file:///private')
    assert budget.used == 0
    assert not queued_http[1]


def test_redirect_body_limit_applies_at_real_requests_adapter_boundary(monkeypatch):
    """Session.send can eagerly consume redirect bodies even with redirects off."""
    body = io.BytesIO(b'x' * (3 * 1024 * 1024))
    consumed = [0]

    class Raw:
        def read(self, size):
            chunk = body.read(size)
            consumed[0] += len(chunk)
            return chunk

        def close(self):
            body.close()

    def adapter_send(adapter, request, **kwargs):
        response = requests.Response()
        response.status_code = 302
        response.headers['Location'] = '/next'
        response.url = request.url
        response.request = request
        response.raw = Raw()
        return response

    monkeypatch.setattr(requests.Session, 'send', ORIGINAL_SESSION_SEND)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', adapter_send)
    with HTTPTransport(RequestBudget(2), retries=0, per_domain_interval=0) as transport:
        with pytest.raises(requests.exceptions.ContentDecodingError):
            transport.request('GET', 'https://example.com/start', allow_redirects=False)
    assert consumed[0] <= 2 * 1024 * 1024 + 65536


def test_redirect_into_auth_endpoint_stops_before_second_request(queued_http, response_factory, site):
    from trace_them.detector import detect
    from trace_them.models import Status
    queued_http[0].append(response_factory(302, headers={'Location': '/%72egister/%76alidate?username=fixture'}))
    budget = RequestBudget(3)
    with HTTPTransport(budget, retries=0, per_domain_interval=0) as transport:
        response = transport.request('GET', 'https://example.com/u/fixture')
    assert len(queued_http[1]) == budget.used == 1
    assert detect(response, site)[0] is Status.BLOCKED
