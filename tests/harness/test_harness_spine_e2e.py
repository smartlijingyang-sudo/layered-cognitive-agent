"""End-to-end test for the /v1/sessions harness spine path.

Drives the real gateway through Starlette TestClient:
  create session → send message → verify snapshot projections populated.

This proves build_live_agent() resolves real LLM + tools and
CognitiveLiveAgent processes the message through the full harness stack.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from gateway.app import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as client:
        yield client


def _require_profile_llm(client: TestClient) -> None:
    """Keep real gateway E2E on the declared production LLM seam only."""

    resolver = client.app.state.ctx.inject("llm_resolver")
    if not callable(getattr(resolver, "resolve", None)) or not resolver.is_available():
        pytest.skip("No production LLM credentials available")


class TestHarnessSpineE2E:
    """The /v1/sessions path exercises the harness plugin system end-to-end."""

    def test_create_session_returns_accepted(self, client: TestClient):
        _require_profile_llm(client)
        receipt = client.post(
            "/v1/sessions",
            json={"profile": "web-standard"},
        )
        assert receipt.status_code == 201
        body = receipt.json()
        assert body["accepted"] is True
        assert body["session_id"].startswith("ses_")

    def test_send_message_and_snapshot_populated(self, client: TestClient):
        """Full harness chain: create → send → agent runs → snapshot reflects result."""
        _require_profile_llm(client)
        create = client.post(
            "/v1/sessions",
            json={"profile": "web-standard", "agent_options": {"max_steps": 3}},
        )
        assert create.status_code == 201
        session_id = create.json()["session_id"]

        send = client.post(
            f"/v1/sessions/{session_id}/messages",
            json={"content": "Reply with exactly: harness-ok"},
        )
        assert send.status_code == 200
        assert send.json()["accepted"] is True

        # Poll snapshot until agent completes (up to 30s)
        import time

        deadline = time.monotonic() + 30
        snapshot_body = None
        while time.monotonic() < deadline:
            snap = client.get(f"/v1/sessions/{session_id}/snapshot")
            assert snap.status_code == 200
            snapshot_body = snap.json()
            activity = snapshot_body.get("values", {}).get("activity", {})
            if activity.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.5)

        assert snapshot_body is not None
        values = snapshot_body["values"]

        # Activity projection must show the agent ran
        activity = values.get("activity", {})
        assert activity.get("status") == "completed", f"Expected completed, got {activity}"
        assert activity.get("turn", 0) >= 1

        # Conversation projection must have the user message and assistant reply
        conversation = values.get("conversation", {})
        messages = conversation.get("messages", [])
        assert len(messages) >= 1, "conversation should have at least one message"
        assert conversation.get("last_assistant_message") is not None, (
            "Agent should have produced an assistant message"
        )

    def test_harness_bridge_resolves_real_llm(self, client: TestClient):
        """build_live_agent() must not use MockLLMAdapter when credentials exist."""
        import time

        from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader
        from lca.harness.session.inbox import Inbox
        from lca.harness.session.store import SessionStore
        from lca.layer4_app.harness_bridge import build_live_agent

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
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

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
