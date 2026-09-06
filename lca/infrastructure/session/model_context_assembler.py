"""Default ModelContextAssembler — Session projection fabric read path (ADR-0193)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.session.model_context import (
    ModelContextAssembler,
    ModelVisibleRequest,
    SessionReader,
)


def _header_field(header: object | None, name: str) -> Any:
    if header is None:
        return None
    if isinstance(header, Mapping):
        return header.get(name)
    return getattr(header, name, None)


class DefaultModelContextAssembler:
    """Session fold → model-visible request (DSH deriveMessages + header)."""

    def assemble(self, session: SessionReader, *, step: int) -> ModelVisibleRequest:
        del step  # reserved for step-scoped compaction; full-log fold for Wave A
        messages = list(session.derive_messages())
        header = session.request_header()
        tools_raw = _header_field(header, "tools")
        tools: tuple[dict[str, Any], ...] = ()
        if isinstance(tools_raw, (list, tuple)):
            tools = tuple(dict(item) for item in tools_raw if isinstance(item, Mapping))
        config_raw = _header_field(header, "config")
        config = dict(config_raw) if isinstance(config_raw, Mapping) else None
        system_raw = _header_field(header, "system")
        system = system_raw if isinstance(system_raw, str) and system_raw else None
        return ModelVisibleRequest(
            messages=messages,
            system=system,
            config=config,
            tools=tools,
        )


def default_model_context_assembler() -> ModelContextAssembler:
    return DefaultModelContextAssembler()


__all__ = ["DefaultModelContextAssembler", "default_model_context_assembler"]
