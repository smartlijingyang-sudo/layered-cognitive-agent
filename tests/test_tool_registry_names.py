from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry


@dataclass
class _Tool:
    name: str
    description: str = "test"
    is_idempotent: bool = True
    default_timeout_s: int = 5


@pytest.mark.parametrize("name", ["", " ", " tool"])
def test_tool_registry_rejects_unaddressable_names(name: str) -> None:
    with pytest.raises(ValueError):
        SimpleToolRegistry().register(_Tool(name))


def test_tool_registry_preserves_exact_valid_tool_name() -> None:
    registry = SimpleToolRegistry()
    tool = _Tool("crm.search")

    registry.register(tool)

    assert registry.get("crm.search") is tool
