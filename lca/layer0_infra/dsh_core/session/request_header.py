"""1:1 port of ``@deepseek-ai/dsh-session/request-header``.

Request-header reconstruction utilities over full ``request/header`` session
events.
"""

from __future__ import annotations

import json

from lca.layer0_infra.dsh_core.session._llm_types import (
    ToolSchema,
    call_config_equals,
)
from lca.layer0_infra.dsh_core.session.types import EpochHeader, SessionEvent


def canonical_header(header: EpochHeader) -> EpochHeader:
    """Normalize a header to canonical form.

    An empty system prompt and empty tool list become absent fields, matching
    how requests are built.
    """
    adapter_defaults = header.adapterDefaults
    has_adapter_defaults = (
        adapter_defaults is not None
        and (
            getattr(adapter_defaults, "reasoningEffort", False) is True
            or getattr(adapter_defaults, "maxTokens", False) is True
        )
    )
    return EpochHeader(
        config=header.config,
        adapterDefaults=adapter_defaults if has_adapter_defaults else None,
        system=header.system if header.system is not None and len(header.system) > 0 else None,
        tools=header.tools if header.tools is not None and len(header.tools) > 0 else None,
    )


def _same_schema(a: ToolSchema, b: ToolSchema) -> bool:
    """Canonical JSON equality for tool schemas."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def header_equals(a: EpochHeader, b: EpochHeader) -> bool:
    """Field-wise equality over canonical headers."""
    if not call_config_equals(a.config, b.config):
        return False
    a_ad = a.adapterDefaults
    b_ad = b.adapterDefaults
    if getattr(a_ad, "reasoningEffort", None) != getattr(b_ad, "reasoningEffort", None):
        return False
    if getattr(a_ad, "maxTokens", None) != getattr(b_ad, "maxTokens", None):
        return False
    if a.system != b.system:
        return False
    at = a.tools or []
    bt = b.tools or []
    if len(at) != len(bt):
        return False
    return all(_same_schema(at[i], bt[i]) for i in range(len(at)))


def fold_request_header(
    events: list[SessionEvent],
    from_: EpochHeader | None = None,
) -> EpochHeader | None:
    """Fold the header events of a log into the EpochHeader in force after the
    last snapshot.

    Non-header events are skipped.  This is the pure offline reconstruction
    path.
    """
    state = from_
    for event in events:
        if event.type == "request/header":
            data = event.data
            header = data.header if hasattr(data, "header") else data.get("header") if isinstance(data, dict) else None
            if header is not None:
                state = canonical_header(header)
    return state
