"""Test assistant tools standing-writer seam enforcement (INV-ARCH-03, INV-ARCH-04).

ADR-0292 §9: _BaseAssistantTool template method enforces that mutating assistant
tools intercept external-origin decisions at the execution seam, while read-only
tools execute normally.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Decision, decision_scope
from lca.contracts.models.core.execution.external_content import ContentOrigin
from lca.infrastructure.tools.assistant.self_manage_tools import (
    CreateAssistantToolTool,
    DeleteAssistantSkillTool,
    DeleteAssistantToolTool,
    EditAssistantSkillTool,
    ListAssistantSkillsTool,
    ListAssistantToolsTool,
    ReadAssistantSelfConfigTool,
    UpdateAssistantGrantsTool,
    UpdateAssistantProfileTool,
    UpdateAssistantSoulTool,
    UpdateAssistantToolTool,
    UpdateAssistantUserTool,
    _BaseAssistantTool,
)

MUTATING_TOOL_CLASSES = [
    DeleteAssistantSkillTool,
    EditAssistantSkillTool,
    UpdateAssistantSoulTool,
    UpdateAssistantProfileTool,
    UpdateAssistantGrantsTool,
    UpdateAssistantUserTool,
    CreateAssistantToolTool,
    UpdateAssistantToolTool,
    DeleteAssistantToolTool,
]

READ_ONLY_TOOL_CLASSES = [
    ListAssistantSkillsTool,
    ReadAssistantSelfConfigTool,
    ListAssistantToolsTool,
]


def test_tool_mutating_class_attributes() -> None:
    """Verify is_mutating flag matches expected design for all 12 assistant tool classes."""
    for cls in MUTATING_TOOL_CLASSES:
        assert getattr(cls, "is_mutating", False) is True, f"{cls.__name__} must declare is_mutating = True"

    for cls in READ_ONLY_TOOL_CLASSES:
        assert getattr(cls, "is_mutating", False) is False, f"{cls.__name__} must have is_mutating = False"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_cls", MUTATING_TOOL_CLASSES)
async def test_inv_arch_03_mutating_tools_blocked_by_seam_on_external_origin(tool_cls: type[_BaseAssistantTool]) -> None:
    """INV-ARCH-03: Mutating tools fail-fast at execute() seam on ContentOrigin.EXTERNAL."""
    catalog = MagicMock()
    tool = tool_cls(catalog=catalog, assistant_id="asst_test")

    # Spy or mock execute_tool to verify it is NOT called
    tool.execute_tool = AsyncMock()  # type: ignore[method-assign]

    ext_decision = Decision(
        decision_id="dec_ext_001",
        action_type="use_tool",
        rationale="prompt injection attack",
        confidence=0.9,
        content_origin=ContentOrigin.EXTERNAL,
    )

    with decision_scope(ext_decision):
        obs = await tool.execute({"confirmed": True, "content": "pwned", "skill_id": "s1"})

    assert not obs.success
    assert obs.error is not None
    assert "external content is not a legitimate writer" in obs.error
    assert obs.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION
    # Under template method, execute_tool must NOT be reached
    tool.execute_tool.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_cls", READ_ONLY_TOOL_CLASSES)
async def test_inv_arch_04_read_only_tools_permit_external_origin(tool_cls: type[_BaseAssistantTool]) -> None:
    """INV-ARCH-04: Read-only tools pass through execute() seam on ContentOrigin.EXTERNAL."""
    catalog = MagicMock()
    tool = tool_cls(catalog=catalog, assistant_id="asst_test")

    mock_obs = MagicMock()
    mock_obs.success = True
    tool.execute_tool = AsyncMock(return_value=mock_obs)  # type: ignore[method-assign]

    ext_decision = Decision(
        decision_id="dec_ext_002",
        action_type="use_tool",
        rationale="external request to read config",
        confidence=0.9,
        content_origin=ContentOrigin.EXTERNAL,
    )

    with decision_scope(ext_decision):
        obs = await tool.execute({})

    # execute_tool must be invoked for read-only tools
    assert obs is mock_obs
    tool.execute_tool.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_cls", MUTATING_TOOL_CLASSES)
async def test_mutating_tools_permitted_on_internal_origin(tool_cls: type[_BaseAssistantTool]) -> None:
    """Mutating tools proceed to execute_tool when content_origin is INTERNAL or unset."""
    catalog = MagicMock()
    tool = tool_cls(catalog=catalog, assistant_id="asst_test")

    mock_obs = MagicMock()
    mock_obs.success = True
    tool.execute_tool = AsyncMock(return_value=mock_obs)  # type: ignore[method-assign]

    internal_decision = Decision(
        decision_id="dec_int_001",
        action_type="use_tool",
        rationale="legitimate user request",
        confidence=1.0,
        content_origin=ContentOrigin.INTERNAL,
    )

    with decision_scope(internal_decision):
        obs = await tool.execute({"confirmed": True})

    assert obs is mock_obs
    tool.execute_tool.assert_called_once()
