"""Structural tests: infrastructure must not import agent (AGENTS.md §2.1).

``FileRoleLibrary`` is a file scanner; it lives in
``lca.infrastructure.roles.role_library`` so infrastructure adapters and domain
consumers depend on infrastructure, not on the L3 agent package.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_infrastructure_tools_assistant_does_not_import_agent() -> None:
    source = (
        REPO / "lca" / "infrastructure" / "tools" / "assistant" / "role_card_resolver.py"
    ).read_text(encoding="utf-8")
    assert "lca.agent" not in source
    assert "lca.infrastructure.roles.role_library" in source


def test_agent_package_has_no_role_library_module() -> None:
    assert not (REPO / "lca" / "agent" / "role_library.py").exists()
    assert (REPO / "lca" / "infrastructure" / "roles" / "role_library.py").exists()


def test_role_library_importable_from_infrastructure() -> None:
    from lca.infrastructure.roles import FileRoleLibrary

    assert FileRoleLibrary is not None
