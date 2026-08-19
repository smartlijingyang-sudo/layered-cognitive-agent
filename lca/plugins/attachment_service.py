"""Attachment Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin

from lca.contracts.protocols.infra import AttachmentIdentity


class AttachmentService:
    """Service Definition for attachment identity.

    Holds a registry of AttachmentIdentity providers. The active one is
    selected at boot time; the provider used at run time is `current()`.
    """

    def __init__(self) -> None:
        self._providers: dict[str, AttachmentIdentity] = {}
        self._active: str | None = None

    def register(self, name: str, provider: AttachmentIdentity, *, activate: bool = False) -> None:
        self._providers[name] = provider
        if activate or self._active is None:
            self._active = name

    def current(self) -> AttachmentIdentity | None:
        if self._active is None:
            return None
        return self._providers.get(self._active)


@plugin(name="lca-attachment-service")
async def setup(ctx, config) -> None:
    ctx.provide("attachment", AttachmentService())
