"""Full Lifecycle E2E Conformance Suite for Conversational Onboarding and Assistant Naming.

Pins invariants INV-01 through INV-08:
- INV-01: Once-in-a-lifetime idempotency (pending -> completed, never asks again)
- INV-02: DB SSOT (lca_users.user_md is single source of truth across assistants)
- INV-03: Digest single-writer (all writes go via AssistantCatalog.revise_profile)
- INV-04: Auto-inheritance for subsequent assistants (assistant #2 inherits user_md)
- INV-05: Deterministic scripted opening (2 bubbles for pending; 1 greeting for completed)
- INV-06: Frozen contracts (NamingCandidate and NamingWidgetPayload validation)
- INV-07: Celebratory reaction (🎉 reaction on naming settlement)
- INV-08: Multi-tenant / user isolation (User A never pollutes User B)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lca.application.onboarding.script import (
    extract_user_name_from_user_md,
    get_onboarding_opening_messages,
)
from lca.contracts.models.onboarding.naming import NamingCandidate, NamingWidgetPayload
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore
from lca.infrastructure.tools.onboarding.naming_tools import (
    CreateNameWidgetTool,
    UpdateIdentityTool,
)
from lca.plugins.domain.assistant.catalog.handlers import _AssistantCatalogImpl


def test_inv06_frozen_contracts_validation() -> None:
    """INV-06: NamingCandidate and NamingWidgetPayload are frozen strict contracts."""
    cand = NamingCandidate(
        id="cand_xl",
        name="星澜",
        vibe="温柔敏锐",
        emoji="✨",
    )
    assert cand.name == "星澜"
    with pytest.raises(ValidationError):
        # Frozen model rejects mutation
        cand.name = "新名称"  # type: ignore[misc]

    test_token = f"tok_{'123'}"
    payload = NamingWidgetPayload(
        token=test_token,
        assistant_id="asst_123",
        candidates=(cand,),
        allow_custom=True,
    )
    assert payload.token == test_token
    assert len(payload.candidates) == 1
    assert payload.allow_custom is True


@pytest.mark.asyncio
async def test_full_conversational_onboarding_e2e_lifecycle(tmp_path: Path) -> None:
    """Full lifecycle E2E verifying INV-01 ~ INV-08 across users and assistants."""
    # 0. Setup persistence and catalog
    db_path = tmp_path / "lca.sqlite3"
    user_store = SqliteUserAssistantStore(db_path)
    assistants_root = tmp_path / "assistants"
    catalog = _AssistantCatalogImpl(root=assistants_root, user_store=user_store)

    user_alice = "u_alice_001"
    user_bob = "u_bob_002"

    user_store.ensure_user(user_alice, username="alice")
    user_store.ensure_user(user_bob, username="bob")

    # ─────────────────────────────────────────────────────────────────
    # Phase 1: Alice First Entry (INV-01, INV-05)
    # ─────────────────────────────────────────────────────────────────
    alice_state = user_store.get_onboarding_state(user_alice)
    assert alice_state == "pending"

    # INV-05: Pending user receives exact 2-bubble scripted opening
    opening_bubbles = get_onboarding_opening_messages(user_state=alice_state)
    assert len(opening_bubbles) == 2
    assert "personal agent" in opening_bubbles[0]
    assert "what’s your name" in opening_bubbles[1] or "what's your name" in opening_bubbles[1]

    # Create Alice's first assistant
    handle_1 = catalog.create(
        CreateAssistantRequest(
            name="AliceAssistant1",
            owner_user_id=user_alice,
        )
    )
    asst_id_1 = handle_1.assistant_id

    # ─────────────────────────────────────────────────────────────────
    # Phase 2: User Name Submission -> Widget Creation (INV-02, INV-03)
    # ─────────────────────────────────────────────────────────────────
    widget_tool = CreateNameWidgetTool(
        catalog=catalog,
        user_store=user_store,
        assistant_id=asst_id_1,
        user_id=user_alice,
    )

    # Execute widget creation with user name
    obs_widget = await widget_tool.execute({"user_name": "李超"})
    assert obs_widget.success is True
    assert obs_widget.payload is not None
    assert "token" in obs_widget.payload
    assert len(obs_widget.payload["candidates"]) >= 2

    # INV-02: DB SSOT updated
    assert user_store.get_user_md(user_alice) is not None
    assert "李超" in user_store.get_user_md(user_alice)

    # INV-03: Digest Single-Writer in Assistant Home
    home_path_1 = Path(handle_1.home_path)
    user_md_path_1 = home_path_1 / "USER.md"
    assert user_md_path_1.is_file()
    assert "李超" in user_md_path_1.read_text(encoding="utf-8")

    # Catalog.get() verifies digest consistency without error
    spec_1 = catalog.get(asst_id_1)
    assert spec_1.assistant_id == asst_id_1

    # ─────────────────────────────────────────────────────────────────
    # Phase 3: Assistant Naming Ceremony & Celebration Reaction (INV-01, INV-07)
    # ─────────────────────────────────────────────────────────────────
    identity_tool = UpdateIdentityTool(
        catalog=catalog,
        user_store=user_store,
        assistant_id=asst_id_1,
        user_id=user_alice,
    )

    obs_identity = await identity_tool.execute(
        {
            "name": "星澜",
            "vibe": "温柔敏锐",
            "emoji": "✨",
        }
    )
    assert obs_identity.success is True
    assert obs_identity.payload is not None

    # INV-07: Celebratory reaction included in execution receipt
    assert obs_identity.payload["reaction"] == "🎉"
    assert obs_identity.payload["onboarding_state"] == "completed"
    assert obs_identity.payload["name"] == "星澜"

    # INV-01: Onboarding state flipped to 'completed'
    assert user_store.get_onboarding_state(user_alice) == "completed"

    # Assistant Home updated and manifest digest re-calculated
    identity_md_path_1 = home_path_1 / "IDENTITY.md"
    assert identity_md_path_1.is_file()
    identity_md_content = identity_md_path_1.read_text(encoding="utf-8")
    assert "星澜" in identity_md_content
    assert "温柔敏锐" in identity_md_content

    # Profile updated
    profile_data_1 = json.loads((home_path_1 / "profile.json").read_text(encoding="utf-8"))
    assert profile_data_1["name"] == "星澜"

    # ─────────────────────────────────────────────────────────────────
    # Phase 4: Second Entry Idempotency (INV-01, INV-05)
    # ─────────────────────────────────────────────────────────────────
    # Subsequent inquiry returns 1 personalized greeting rather than onboarding
    alice_updated_state = user_store.get_onboarding_state(user_alice)
    alice_name = extract_user_name_from_user_md(user_store.get_user_md(user_alice) or "")
    subsequent_bubbles = get_onboarding_opening_messages(
        user_state=alice_updated_state,
        user_name=alice_name,
        assistant_name="星澜",
        role_title="专属助理",
    )
    assert len(subsequent_bubbles) == 1
    assert "李超" in subsequent_bubbles[0]
    assert "怎么称呼你" not in subsequent_bubbles[0]

    # ─────────────────────────────────────────────────────────────────
    # Phase 5: Second Assistant Auto-Inheritance (INV-04)
    # ─────────────────────────────────────────────────────────────────
    handle_2 = catalog.create(
        CreateAssistantRequest(
            name="AliceAssistant2",
            owner_user_id=user_alice,
        )
    )
    asst_id_2 = handle_2.assistant_id
    home_path_2 = Path(handle_2.home_path)

    # INV-04: Second assistant auto-inherits Alice's USER.md from DB SSOT
    user_md_path_2 = home_path_2 / "USER.md"
    assert user_md_path_2.is_file()
    assert "李超" in user_md_path_2.read_text(encoding="utf-8")

    # Second assistant has valid manifest digest
    spec_2 = catalog.get(asst_id_2)
    assert spec_2.assistant_id == asst_id_2

    # ─────────────────────────────────────────────────────────────────
    # Phase 6: Multi-Tenant & Session Isolation (INV-08)
    # ─────────────────────────────────────────────────────────────────
    # Bob is still pending and has NO user_md
    bob_state = user_store.get_onboarding_state(user_bob)
    assert bob_state == "pending"
    assert user_store.get_user_md(user_bob) is None

    bob_opening = get_onboarding_opening_messages(user_state=bob_state)
    assert len(bob_opening) == 2
    assert "李超" not in bob_opening[0]
    assert "李超" not in bob_opening[1]

    handle_bob = catalog.create(
        CreateAssistantRequest(
            name="BobAssistant",
            owner_user_id=user_bob,
        )
    )
    bob_user_md_path = Path(handle_bob.home_path) / "USER.md"
    # Bob's assistant does not contain Alice's name
    assert "李超" not in bob_user_md_path.read_text(encoding="utf-8")
