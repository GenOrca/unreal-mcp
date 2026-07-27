"""HMAC-signed expiring single-use confirmation and undo tokens."""

import base64
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import hmac
import json
from secrets import token_urlsafe


class TokenErrorReason(StrEnum):
    INVALID = "invalid"
    EXPIRED = "expired"
    BINDING = "binding"
    USED = "used"


class TokenValidationError(ValueError):
    def __init__(self, reason: TokenErrorReason, message: str):
        self.reason = reason
        super().__init__(message)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("token encoding is invalid") from exc
    if _b64encode(decoded) != value:
        raise ValueError("token encoding is not canonical")
    return decoded


class TokenService:
    def __init__(self, *, secret: bytes, ttl: timedelta):
        if not secret:
            raise ValueError("token secret must not be empty")
        if ttl.total_seconds() <= 0:
            raise ValueError("token ttl must be positive")
        self._secret = secret
        self._ttl = ttl
        self._consumed: dict[str, float] = {}

    def issue_confirmation(
        self,
        plan_id: str,
        digest: str,
        *,
        now: datetime | None = None,
    ) -> str:
        return self._issue("confirmation", plan_id, digest, now=now)

    def consume_confirmation(
        self,
        token: str,
        plan_id: str,
        digest: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        return self._consume("confirmation", token, plan_id, digest, now=now)

    def issue_undo(
        self,
        plan_id: str,
        post_state_digest: str,
        *,
        now: datetime | None = None,
    ) -> str:
        return self._issue("undo", plan_id, post_state_digest, now=now)

    def consume_undo(
        self,
        token: str,
        plan_id: str,
        post_state_digest: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        return self._consume("undo", token, plan_id, post_state_digest, now=now)

    def _issue(
        self,
        kind: str,
        plan_id: str,
        digest: str,
        *,
        now: datetime | None,
    ) -> str:
        issued = self._now(now)
        payload = {
            "kind": kind,
            "plan_id": plan_id,
            "digest": digest,
            "issued_at": issued.timestamp(),
            "expires_at": (issued + self._ttl).timestamp(),
            "nonce": token_urlsafe(18),
        }
        encoded_payload = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        signature = hmac.new(self._secret, encoded_payload, sha256).digest()
        return f"{_b64encode(encoded_payload)}.{_b64encode(signature)}"

    def _consume(
        self,
        kind: str,
        token: str,
        plan_id: str,
        digest: str,
        *,
        now: datetime | None,
    ) -> bool:
        current = self._now(now).timestamp()
        self._prune(current)
        try:
            payload_segment, signature_segment = token.split(".")
            payload_bytes = _b64decode(payload_segment)
            supplied_signature = _b64decode(signature_segment)
        except ValueError as exc:
            raise TokenValidationError(
                TokenErrorReason.INVALID, "token format is invalid"
            ) from exc
        expected_signature = hmac.new(self._secret, payload_bytes, sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise TokenValidationError(
                TokenErrorReason.INVALID, "token signature mismatch"
            )
        try:
            payload = json.loads(payload_bytes)
        except Exception as exc:
            raise TokenValidationError(
                TokenErrorReason.INVALID, "token payload is invalid"
            ) from exc

        if current > float(payload.get("expires_at", 0)):
            raise TokenValidationError(
                TokenErrorReason.EXPIRED, "token expired"
            )
        if (
            payload.get("kind") != kind
            or payload.get("plan_id") != plan_id
            or payload.get("digest") != digest
        ):
            raise TokenValidationError(
                TokenErrorReason.BINDING, "token binding mismatch"
            )
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise TokenValidationError(
                TokenErrorReason.INVALID, "token payload is invalid"
            )
        if nonce in self._consumed:
            raise TokenValidationError(
                TokenErrorReason.USED, "token already used"
            )
        self._consumed[nonce] = float(payload["expires_at"])
        return True

    def _prune(self, now_timestamp: float) -> None:
        self._consumed = {
            nonce: expiry
            for nonce, expiry in self._consumed.items()
            if expiry >= now_timestamp
        }

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = datetime.now(UTC) if value is None else value
        if current.tzinfo is None:
            raise ValueError("token timestamps must be timezone-aware")
        return current.astimezone(UTC)
