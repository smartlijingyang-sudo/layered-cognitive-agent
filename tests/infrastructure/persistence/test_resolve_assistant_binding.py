"""RA-141 pins: ``resolve_assistant_binding`` owns the agt_* -> asst_* precedence.

Ownership store first, LobeHub ``agents.agency_config->>'lcaAssistantId'``
fallback second (ADR-0187 §3 D7 truth unchanged); a miss on both returns
``None`` and the seam never raises. These paths were only exercisable through
the HTTP endpoint before (``decode_create_run`` hand-chained them).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from lca.infrastructure.persistence.assistant_binding import (
    resolve_assistant_binding,
)

if TYPE_CHECKING:
    import pytest


class _Ownership:
    def __init__(self, bound: str | None) -> None:
        self._bound = bound

    def assistant_id_for_agent(self, agent_id: str) -> str | None:
        return self._bound


def _unexpected_fallback(agent_id: str) -> str | None:
    raise AssertionError("fallback must not run when ownership maps the agent")


def test_ownership_hit_wins() -> None:
    assert (
        resolve_assistant_binding(
            "agt_owned", _Ownership("asst_owned"), lobehub_fallback=_unexpected_fallback
        )
        == "asst_owned"
    )


def test_lobehub_hit_on_ownership_miss() -> None:
    assert (
        resolve_assistant_binding(
            "agt_run_created",
            _Ownership(None),
            lobehub_fallback=lambda agent_id: "asst_lobehub",
        )
        == "asst_lobehub"
    )


def test_double_miss_returns_none() -> None:
    assert (
        resolve_assistant_binding(
            "agt_unknown", _Ownership(None), lobehub_fallback=lambda _a: None
        )
        is None
    )


def test_ownership_none_still_consults_fallback() -> None:
    assert (
        resolve_assistant_binding(
            "agt_run_created", None, lobehub_fallback=lambda _a: "asst_lobehub"
        )
        == "asst_lobehub"
    )


def test_raising_fallback_never_raises() -> None:
    def _boom(agent_id: str) -> str | None:
        raise RuntimeError("db down")

    assert (
        resolve_assistant_binding(
            "agt_x", _Ownership(None), lobehub_fallback=_boom
        )
        is None
    )


def test_broken_lobehub_import_degrades_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RA-135 boundary at seam level: a broken ``lobehub_agents`` import must
    not break resolution — it degrades to ``None`` (fail-soft)."""
    monkeypatch.setitem(sys.modules, "lca.infrastructure.persistence.lobehub_agents", None)
    assert resolve_assistant_binding("agt_x", None) is None


def test_default_fallback_is_the_real_impl() -> None:
    """Without an injected fallback the seam wires the real lobehub reader."""
    import lca.infrastructure.persistence.assistant_binding as binding_module

    assert binding_module.resolve_assistant_binding("agt_x", _Ownership("asst_owned")) == (
        "asst_owned"
    )
    # No DB URL in this environment -> real impl returns None, never raises.
    assert resolve_assistant_binding("agt_x", _Ownership(None)) is None
