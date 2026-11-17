"""Offline-first independent test fixtures."""
import socket

import pytest
import requests


def pytest_addoption(parser):
    parser.addoption('--run-online', action='store_true', help='Enable explicitly marked live tests.')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--run-online'):
        return
    for item in items:
        if 'online' in item.keywords:
            item.add_marker(pytest.mark.skip(reason='Live tests require --run-online.'))


@pytest.fixture(autouse=True)
def deny_network(request, monkeypatch):
    monkeypatch.delenv('GRAVATAR_API_KEY', raising=False)
    if request.node.get_closest_marker('online') and request.config.getoption('--run-online'):
        return

    def deny(*args, **kwargs):
        raise AssertionError('Unexpected network access in offline test')

    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(requests.Session, 'send', deny)


@pytest.fixture
def response_factory():
    def make(status=200, text='<html><title>Public profile</title></html>', url='https://example.com/u/test', headers=None):
        response = requests.Response()
        response.status_code = status
        response._content = text.encode('utf-8')
        response._content_consumed = True
        response.encoding = 'utf-8'
        response.url = url
        response.headers.update(headers or {})
        response.request = requests.Request('GET', url).prepare()
        return response
    return make


@pytest.fixture
def site():
    return {'url': 'https://example.com/u/{}', 'urlMain': 'https://example.com/',
            'username_claimed': 'fixture', 'errorType': 'status_code'}


@pytest.fixture
def queued_http(monkeypatch, response_factory):
    """Intercept actual send attempts, including redirects and retries."""
    pending = []
    calls = []

    def send(session, request, **kwargs):
        calls.append((request, kwargs))
        if not pending:
            raise AssertionError('Unexpected extra HTTP attempt')
        result = pending.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, int):
            result = response_factory(result)
        result.request = request
        result.url = request.url
        return result

    monkeypatch.setattr(requests.Session, 'send', send)
    return pending, calls
