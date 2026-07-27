"""Expiring, signed, single-use workflow token tests."""

from datetime import UTC, datetime, timedelta

import pytest

from unreal_mcp.workflows.tokens import TokenService


def test_confirmation_token_is_single_use():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=now)
    assert service.consume_confirmation(token, "plan-1", "digest-1", now=now)
    with pytest.raises(ValueError, match="already used") as caught:
        service.consume_confirmation(token, "plan-1", "digest-1", now=now)
    assert caught.value.reason == "used"


def test_confirmation_token_expires():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    issued = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=issued)
    with pytest.raises(ValueError, match="expired") as caught:
        service.consume_confirmation(
            token, "plan-1", "digest-1", now=issued + timedelta(minutes=11)
        )
    assert caught.value.reason == "expired"


def test_confirmation_token_rejects_other_digest_without_consuming_it():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=now)
    with pytest.raises(ValueError, match="mismatch") as caught:
        service.consume_confirmation(token, "plan-1", "digest-2", now=now)
    assert caught.value.reason == "binding"
    assert service.consume_confirmation(token, "plan-1", "digest-1", now=now)


def test_undo_token_is_bound_to_post_state_and_single_use():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_undo("plan-1", "post-digest-1", now=now)
    with pytest.raises(ValueError, match="mismatch"):
        service.consume_undo(token, "plan-1", "changed", now=now)
    assert service.consume_undo(token, "plan-1", "post-digest-1", now=now)
    with pytest.raises(ValueError, match="already used"):
        service.consume_undo(token, "plan-1", "post-digest-1", now=now)


def test_tampered_token_is_rejected():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=now)
    replacement = "Q" if token[-1] == "A" else "A"
    with pytest.raises(ValueError, match="signature") as caught:
        service.consume_confirmation(
            token[:-1] + replacement, "plan-1", "digest-1", now=now
        )
    assert caught.value.reason == "invalid"
