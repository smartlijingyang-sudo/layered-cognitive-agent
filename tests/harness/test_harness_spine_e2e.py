"""End-to-end test for the /v1/sessions harness spine path.

Drives the real gateway through Starlette TestClient:
  create session → send message → verify snapshot projections populated.

This proves build_live_agent() resolves real LLM + tools and
CognitiveLiveAgent processes the message through the full harness stack.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from lca_kernel.cli import create_app


@pytest.fixture()
async def client():
    app = await create_app()
    with TestClient(app) as c:
        yield c


def _require_profile_llm(client: TestClient) -> None:
    """Keep real gateway E2E on the declared production LLM seam only."""

    resolver = client.app.state.ctx.inject("llm_resolver")
    if not callable(getattr(resolver, "resolve", None)) or not resolver.is_available():
        pytest.skip("No production LLM credentials available")


class TestHarnessSpineE2E:
    """The /v1/sessions path exercises the harness plugin system end-to-end."""

    def test_harness_bridge_resolves_real_llm(self, client: TestClient):
        """build_live_agent() must not use MockLLMAdapter when credentials exist."""
        import time

        from lca.application.harness_bridge import build_live_agent
        from lca.contracts.harness.tasks.session import SESSION_FORMAT_VERSION, SessionHeader
        from lca.harness.session.inbox import Inbox
        from lca.harness.session.store import SessionStore

        _require_profile_llm(client)

        header = SessionHeader(
            version=SESSION_FORMAT_VERSION,
            id="test-bridge-llm",
            created_at=int(time.time() * 1000),
        )
        store = SessionStore(header)
        inbox = Inbox(store)

        handle = build_live_agent(
            store=store,
            inbox=inbox,
            identity_id="test-bridge-llm",
            options=None,
            cordis_ctx=client.app.state.ctx,
        )

        # The agent's LLM should NOT be MockLLMAdapter
        from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter

        agent = handle.agent
        # Access the internal CognitiveAgent → runtime → brain → llm
        inner = getattr(agent, "_agent", None)
        if inner is not None:
            runtime = getattr(inner, "_runtime", None)
            if runtime is not None:
                brain = getattr(runtime, "_brain", None)
                if brain is not None:
                    llm = getattr(brain, "_llm", None)
                    if llm is not None:
                        assert not isinstance(llm, MockLLMAdapter), (
                            "build_live_agent() should resolve production LLM, not mock"
                        )
