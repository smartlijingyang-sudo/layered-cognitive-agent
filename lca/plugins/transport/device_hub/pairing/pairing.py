"""RFC 8628 Device Authorization Flow for Companion Pairing (ADR-0246 M2)."""

from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass
from enum import StrEnum


class PairingStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class PairingRequest:
    device_code: str
    user_code: str
    device_id: str
    label: str
    platform: str
    created_at: float
    expires_at: float
    status: PairingStatus = PairingStatus.PENDING
    user_id: str | None = None
    workspace_id: str | None = None
    machine_token: str | None = None
    pre_authorized: bool = False

    @property
    def expires_in(self) -> int:
        return max(0, int(self.expires_at - time.time()))


@dataclass(frozen=True)
class VerifyResult:
    success: bool
    device_id: str | None = None
    label: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PollResult:
    status: str
    machine_token: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None
    error: str | None = None


class DevicePairingService:
    """Manages RFC 8628 Device Code pairing for user machines."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._by_device_code: dict[str, PairingRequest] = {}
        self._by_user_code: dict[str, PairingRequest] = {}
        self._by_machine_token: dict[str, PairingRequest] = {}

    def _normalize_user_code(self, code: str) -> str:
        return code.replace("-", "").strip().upper()

    def preauth_code(
        self,
        user_id: str,
        workspace_id: str,
        expires_in: int = 600,
    ) -> PairingRequest:
        now = time.time()
        device_code = secrets.token_urlsafe(32)

        chars = string.ascii_uppercase + string.digits
        chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
        raw_code = "".join(secrets.choice(chars) for _ in range(8))
        user_code = f"{raw_code[:4]}-{raw_code[4:]}"
        norm_code = self._normalize_user_code(user_code)

        req = PairingRequest(
            device_code=device_code,
            user_code=user_code,
            device_id="",
            label="",
            platform="",
            created_at=now,
            expires_at=now + expires_in,
            status=PairingStatus.AUTHORIZED,
            user_id=user_id,
            workspace_id=workspace_id,
            pre_authorized=True,
        )

        self._by_device_code[device_code] = req
        self._by_user_code[norm_code] = req
        return req

    def claim_preauth(
        self,
        user_code: str,
        device_id: str,
        label: str,
        platform: str = "",
    ) -> PairingRequest | None:
        norm = self._normalize_user_code(user_code)
        req = self._by_user_code.get(norm)
        if not req:
            return None

        now = time.time()
        if now > req.expires_at or req.status == PairingStatus.EXPIRED:
            req.status = PairingStatus.EXPIRED
            return None

        if not req.pre_authorized or req.status != PairingStatus.AUTHORIZED:
            return None

        token = f"mtk-{secrets.token_hex(24)}"
        req.device_id = device_id
        req.label = label
        req.platform = platform
        req.machine_token = token
        req.status = PairingStatus.COMPLETED
        req.pre_authorized = False
        self._by_machine_token[token] = req
        return req

    def request_code(
        self,
        device_id: str,
        label: str,
        platform: str = "",
        user_code: str | None = None,
    ) -> PairingRequest:
        if user_code:
            claimed = self.claim_preauth(
                user_code=user_code,
                device_id=device_id,
                label=label,
                platform=platform,
            )
            if claimed is not None:
                return claimed

        now = time.time()
        device_code = secrets.token_urlsafe(32)

        # Generate 8-character uppercase/digit code
        chars = string.ascii_uppercase + string.digits
        # Avoid ambiguous characters (0, O, 1, I)
        chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
        raw_code = "".join(secrets.choice(chars) for _ in range(8))
        user_code = f"{raw_code[:4]}-{raw_code[4:]}"
        norm_code = self._normalize_user_code(user_code)

        req = PairingRequest(
            device_code=device_code,
            user_code=user_code,
            device_id=device_id,
            label=label,
            platform=platform,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )

        self._by_device_code[device_code] = req
        self._by_user_code[norm_code] = req
        return req

    def verify_code(
        self,
        user_code: str,
        user_id: str,
        workspace_id: str,
    ) -> VerifyResult:
        norm = self._normalize_user_code(user_code)
        req = self._by_user_code.get(norm)
        if not req:
            return VerifyResult(success=False, error="invalid_code")

        now = time.time()
        if now > req.expires_at or req.status == PairingStatus.EXPIRED:
            req.status = PairingStatus.EXPIRED
            return VerifyResult(success=False, error="expired")

        if req.status != PairingStatus.PENDING:
            return VerifyResult(success=False, error=f"already_{req.status}")

        req.status = PairingStatus.AUTHORIZED
        req.user_id = user_id
        req.workspace_id = workspace_id
        return VerifyResult(success=True, device_id=req.device_id, label=req.label)

    def poll_token(self, device_code: str) -> PollResult:
        req = self._by_device_code.get(device_code)
        if not req:
            return PollResult(status="invalid_device_code", error="invalid_device_code")

        now = time.time()
        if now > req.expires_at or req.status == PairingStatus.EXPIRED:
            req.status = PairingStatus.EXPIRED
            return PollResult(status="expired", error="expired")

        if req.status == PairingStatus.PENDING:
            return PollResult(status="authorization_pending")

        if req.status == PairingStatus.AUTHORIZED:
            token = f"mtk-{secrets.token_hex(24)}"
            req.machine_token = token
            req.status = PairingStatus.COMPLETED
            self._by_machine_token[token] = req
            return PollResult(
                status="success",
                machine_token=token,
                user_id=req.user_id,
                workspace_id=req.workspace_id,
            )

        if req.status == PairingStatus.COMPLETED:
            if req.machine_token:
                self._by_machine_token[req.machine_token] = req
            return PollResult(
                status="success",
                machine_token=req.machine_token,
                user_id=req.user_id,
                workspace_id=req.workspace_id,
            )

        return PollResult(status=str(req.status))

    def get_by_machine_token(self, token: str) -> PairingRequest | None:
        return self._by_machine_token.get(token)


__all__ = [
    "DevicePairingService",
    "PairingRequest",
    "PairingStatus",
    "PollResult",
    "VerifyResult",
]
