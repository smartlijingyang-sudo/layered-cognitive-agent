"""Artifact — immutable information carrier.

Borrowed shape from lca/contracts/atoms/ (minimal slice: digest + content + kind).
Pydantic frozen, extra=forbid per AGENTS.md C13.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ArtifactKind(StrEnum):
    TEXT = "text"
    MESSAGE = "message"  # OpenAI-style chat message
    MANIFEST = "manifest"  # frozen ContextManifest
    RECEIPT = "receipt"  # EffectReceipt
    FACT = "fact"  # appended journal fact
    INTENT = "intent"  # ToolIntent
    DIGEST = "digest"  # pointer to another artifact
    EXCEPTION = "exception"  # node failure carrier; consumed by on_error=route targets


class Artifact(BaseModel):
    """Immutable carrier. content is bytes-like or structured; digest is sha256."""

    model_config = {"frozen": True, "extra": "forbid"}

    kind: ArtifactKind
    content: Any
    schema_ref: str = "raw"
    # validate_default=True: Pydantic v2 skips field validators for omitted
    # defaults otherwise, leaving digest permanently empty.
    digest: str = Field(default="", validate_default=True)

    @field_validator("digest", mode="before")
    @classmethod
    def _compute_digest(cls, v: str, info: Any) -> str:
        """Auto-fill digest if caller left it empty."""
        if v:
            return v
        # Pydantic v2 supplies values via info.data
        data = info.data if hasattr(info, "data") else {}
        content = data.get("content")
        schema_ref = data.get("schema_ref", "raw")
        payload = repr((schema_ref, content)).encode()
        return hashlib.sha256(payload).hexdigest()

    def short_id(self) -> str:
        return self.digest[:12]


def make_text(s: str, schema_ref: str = "raw") -> Artifact:
    return Artifact(kind=ArtifactKind.TEXT, content=s, schema_ref=schema_ref)


def make_message(role: str, content: str, **extra: Any) -> Artifact:
    return Artifact(
        kind=ArtifactKind.MESSAGE,
        content={"role": role, "content": content, **extra},
        schema_ref="openai.message.v1",
    )


def make_exception(
    *,
    error_class: str,
    message: str,
    node_id: str = "",
    transient: bool = False,
    detail: Any = None,
) -> Artifact:
    """Carrier for a node's failure. Consumed by on_error=route targets.

    transient=True signals a retryable failure (network/timeout); the
    runner's on_error=retry branch will re-invoke the node up to
    config.max_retries times. transient=False (default) is treated as
    deterministic — retry refuses and routes to a deny handler.
    """
    return Artifact(
        kind=ArtifactKind.EXCEPTION,
        content={
            "error_class": error_class,
            "message": message,
            "node_id": node_id,
            "transient": transient,
            "detail": detail,
        },
        schema_ref="error.exception.v1",
    )
