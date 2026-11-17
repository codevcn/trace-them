"""Small optional network smoke; only a reserved synthetic email is used."""
import pytest

from trace_them.models import Status
from trace_them.resolvers import GravatarResolver
from trace_them.transport import HTTPTransport, RequestBudget


@pytest.mark.online
def test_gravatar_reserved_synthetic_address_has_no_public_profile():
    with HTTPTransport(RequestBudget(1), retries=0) as transport:
        result = GravatarResolver(transport).resolve('trace-them-qa-probe@example.invalid')
    assert result.status is Status.NOT_FOUND
    assert not result.findings
