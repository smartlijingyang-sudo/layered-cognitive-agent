"""Artifact — immutable information carrier.

Borrowed shape from lca/contracts/atoms/ (minimal slice: digest + content + kind).
Pydantic frozen, extra=forbid per AGENTS.md C13.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, field_validator


class ArtifactKind(StrEnum):
    TEXT = "text"
    MESSAGE = "message"          # OpenAI-style chat message
    MANIFEST = "manifest"        # frozen ContextManifest
    RECEIPT = "receipt"          # EffectReceipt
    FACT = "fact"                # appended journal fact
    INTENT = "intent"            # ToolIntent
    DIGEST = "digest"            # pointer to another artifact


class Artifact(BaseModel):
    """Immutable carrier. content is bytes-like or structured; digest is sha256."""

    model_config = {"frozen": True, "extra": "forbid"}

    kind: ArtifactKind
    content: Any
    schema_ref: str = "raw"
    digest: str = ""

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
