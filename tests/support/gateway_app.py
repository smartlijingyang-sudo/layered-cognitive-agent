"""Test helpers for gateway apps that need a scripted LLM resolver.

Production ``create_app`` does not accept ``llm_resolver`` — the plugin
tree owns credentials. Tests override via a *test-only lifespan* that
wraps the profile lifespan and installs the scripted resolver after
boot completes, before any request is served.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from gateway.runs.session import RunRegistry
from lca.harness.profile.lifespan import profile_lifespan
from tests.support.gateway_scripted import ScriptedLLMResolver

if TYPE_CHECKING:
    from starlette.applications import Starlette


def create_scripted_app(
    registry: RunRegistry | None = None,
    *,
    llm_resolver: Any | None = None,
    profile_path: str | None = None,
) -> Starlette:
    """Build a gateway app whose profile lifespan also installs a scripted LLM.

    Each call returns a fresh app with its own boot — no shared state
    across tests. The scripted resolver is installed by a test-only
    lifespan that wraps the production profile lifespan; boot and
    resolver injection both run on Starlette's startup loop, so no
    side-thread hack and no module-level cache pollution.
    """
    # ``test_gateway_lazy_reexport`` intentionally reloads ``gateway.app``.
    # Resolve the factory at call time so route handlers and any patched
    # module globals belong to the same live module instance.
    from gateway.app import create_app

    resolver = llm_resolver if llm_resolver is not None else ScriptedLLMResolver()

    @asynccontextmanager
    async def _scripted_lifespan(app: Starlette) -> AsyncIterator[None]:
        async with profile_lifespan(profile_path or "profiles/web-standard.yaml") as state:
            state["ctx"].provide("llm_resolver", resolver)
            app.state.ctx = state["ctx"]
            yield

    return create_app(registry=registry, profile_path=profile_path, lifespan=_scripted_lifespan)
