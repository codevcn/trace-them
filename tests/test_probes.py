"""Deterministic replacements for legacy live known-positive/negative tests."""
import pytest

from trace_them.detector import detect
from trace_them.models import Status


@pytest.mark.parametrize('method', ['status_code', 'response_url'])
def test_known_positive(response_factory, site, method):
    site['errorType'] = method
    status, reason = detect(response_factory(), site)
    assert status is Status.FOUND
    assert reason


@pytest.mark.parametrize('code', [404, 410])
def test_explicit_absence(response_factory, site, code):
    status, reason = detect(response_factory(code), site)
    assert status is Status.NOT_FOUND
    assert reason


def test_message_present_is_absence(response_factory, site):
    site.update(errorType='message', errorMsg=['User does not exist', 'Profile missing'])
    status, _ = detect(response_factory(text='<html>Profile missing</html>'), site)
    assert status is Status.NOT_FOUND


@pytest.mark.parametrize('code,expected', [(429, Status.RATE_LIMITED), (500, Status.ERROR),
                                         (502, Status.ERROR), (503, Status.ERROR),
                                         (403, Status.BLOCKED), (401, Status.BLOCKED)])
@pytest.mark.parametrize('method', ['status_code', 'message', 'response_url'])
def test_failures_are_not_absence(response_factory, site, code, expected, method):
    site.update(errorType=method, errorMsg='missing')
    status, reason = detect(response_factory(code, text='Temporary failure'), site)
    assert status is expected
    assert reason


@pytest.mark.parametrize('body', [
    '<html><title>Just a moment...</title><span id="challenge-error-text">captcha</span></html>',
    '<html><title>Verify you are human</title></html>',
    '<html><title>Sign in</title><form><input type="password"></form></html>',
])
def test_soft_block_pages_never_count_as_found(response_factory, site, body):
    site.update(errorType='message', errorMsg='User not found')
    status, _ = detect(response_factory(text=body), site)
    assert status in {Status.BLOCKED, Status.UNKNOWN}


def test_redirect_to_login_is_not_identity_absence(response_factory, site):
    site['errorType'] = 'response_url'
    status, _ = detect(response_factory(302, headers={'Location': '/login'}), site)
    assert status in {Status.BLOCKED, Status.UNKNOWN}


def test_message_on_ambiguous_page_never_creates_false_positive(response_factory, site):
    site.update(errorType='message', errorMsg='User does not exist')
    status, _ = detect(response_factory(text=''), site)
    assert status is Status.UNKNOWN


def test_unknown_detector_preserves_unknown(response_factory, site):
    site['errorType'] = 'unrecognized'
    status, reason = detect(response_factory(), site)
    assert status in {Status.UNKNOWN, Status.ERROR, Status.UNSUPPORTED}
    assert reason


def test_combined_detectors_require_all_rules(response_factory, site):
    site.update(errorType=['message', 'status_code'], errorMsg='No such user')
    status, _ = detect(response_factory(text='No such user'), site)
    assert status is Status.NOT_FOUND


def test_login_redirect_history_remains_blocked_after_return_to_profile(response_factory, site):
    response = response_factory()
    response.history = [response_factory(302, url='https://example.com/login',
                                         headers={'Location': '/u/test'})]
    status, _ = detect(response, site)
    assert status is Status.BLOCKED


def test_head_without_body_cannot_evaluate_negative_message(response_factory, site):
    site.update(request_method='HEAD', errorType='message', errorMsg='User not found')
    status, _ = detect(response_factory(text=''), site)
    assert status is Status.UNKNOWN


def test_arbitrary_redirect_is_unknown(response_factory, site):
    site.update(errorType='response_url', errorUrl='https://example.com/missing')
    status, _ = detect(response_factory(302, headers={'Location': '/unrelated'}), site)
    assert status is Status.UNKNOWN


def test_configured_missing_redirect_is_explicit_absence(response_factory, site):
    site.update(errorType='response_url', errorUrl='https://example.com/missing')
    status, _ = detect(response_factory(302, headers={'Location': '/missing'}), site)
    assert status is Status.NOT_FOUND


@pytest.mark.parametrize('body', ['Rate limit exceeded. Please try again later.',
                                 'Internal server error', 'Service temporarily unavailable'])
def test_soft_transient_error_body_cannot_be_found_or_absent(response_factory, site, body):
    site.update(errorType='message', errorMsg='User not found')
    status, _ = detect(response_factory(text=body), site)
    assert status in {Status.RATE_LIMITED, Status.ERROR, Status.UNKNOWN}


@pytest.mark.parametrize('body', ['<html><title>Continue</title><form><input type="password"></form></html>',
                                 '{"status":"error","message":"authentication required"}'])
def test_authentication_without_login_title_never_becomes_found(response_factory, site, body):
    site.update(errorType='message', errorMsg='User not found')
    status, _ = detect(response_factory(text=body), site)
    assert status in {Status.BLOCKED, Status.UNKNOWN, Status.ERROR}
