"""Test helpers for gateway apps that need a scripted LLM resolver.

Production ``create_app`` does not accept ``llm_resolver`` — the plugin
tree owns credentials. Tests override via ``ctx.provide`` after boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gateway.app import create_app
from gateway.runs.session import RunRegistry
from tests.support.gateway_scripted import ScriptedLLMResolver

if TYPE_CHECKING:
    from starlette.applications import Starlette


def create_scripted_app(
    registry: RunRegistry | None = None,
    *,
    llm_resolver: Any | None = None,
    profile_path: str | None = None,
) -> Starlette:
    """Boot the gateway app and install a test LLM resolver on the ctx."""
    app = create_app(registry, profile_path=profile_path)
    resolver = llm_resolver if llm_resolver is not None else ScriptedLLMResolver()
    ctx = getattr(app.state, "ctx", None)
    if ctx is not None:
        ctx.provide("llm_resolver", resolver)
    return app
