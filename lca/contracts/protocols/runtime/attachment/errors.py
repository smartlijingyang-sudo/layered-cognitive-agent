"""Closed error vocabulary for attachment / FileRef seams (ADR-0121).

Each error carries a stable ``code`` so the Journal and downstream tests can
match without parsing message text. The codes are part of the public contract;
adding a new code requires a new ADR-level entry, not a free addition.
"""

from __future__ import annotations

from enum import Enum


class AttachmentErrorCode(str, Enum):
    """Closed vocabulary for attachment / FileRef failures."""

    UNRESOLVED_REF = "attachment.unresolved_ref"
    AMBIGUOUS_REF = "attachment.ambiguous_ref"
    MISSING_ATTACHMENT = "attachment.missing_attachment"
    POLICY_REJECTED = "attachment.policy_rejected"
    STAGE_FAILED = "attachment.stage_failed"
    RENDERER_NOT_REGISTERED = "attachment.renderer_not_registered"
    SANDBOX_BACKEND_UNAVAILABLE = "attachment.sandbox_backend_unavailable"


class AttachmentError(RuntimeError):
    """One failure of an attachment seam; always carry ``code``."""

    code: AttachmentErrorCode

    def __init__(
        self,
        code: AttachmentErrorCode,
        message: str = "",
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.context: dict[str, object] = context or {}


class UnresolvedFileRefError(AttachmentError):
    """Caller handed us a path / URL we could not map to a :class:`FileRef`."""

    def __init__(self, raw: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(
            AttachmentErrorCode.UNRESOLVED_REF,
            f"could not resolve path to FileRef: {raw!r}",
            context={"raw": raw, **(context or {})},
        )


class AmbiguousFileRefError(AttachmentError):
    """Caller handed us a string that matches multiple FileRefs."""

    def __init__(self, raw: str, matches: tuple[str, ...]) -> None:
        super().__init__(
            AttachmentErrorCode.AMBIGUOUS_REF,
            f"path {raw!r} matches multiple attachments: {matches!r}",
            context={"raw": raw, "matches": matches},
        )


__all__ = [
    "AmbiguousFileRefError",
    "AttachmentError",
    "AttachmentErrorCode",
    "UnresolvedFileRefError",
]
