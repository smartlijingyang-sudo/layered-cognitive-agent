"""environment_awareness tool tests — model-visible environment directory."""

from __future__ import annotations

import asyncio

from lca.infrastructure.environment.catalog import CompositeEnvironmentCatalog
from lca.infrastructure.tools.environment_awareness import API_NAME, build_tools


def test_build_tools_exposes_list_environments() -> None:
    tools = build_tools(catalog=None)
    assert [tool.name for tool in tools] == [API_NAME]


def test_execute_with_empty_catalog_returns_empty() -> None:
    tool = build_tools(catalog=None)[0]
    obs = asyncio.run(tool.execute({}))
    assert obs.success
    assert obs.payload == {"current": None, "environments": []}


def test_execute_returns_current_and_environments() -> None:
    from lca.contracts.models.core.environment.model import (
        EnvironmentKind,
        ExecutionEnvironment,
    )

    catalog = CompositeEnvironmentCatalog(
        [],
        current=ExecutionEnvironment(
            kind=EnvironmentKind.SANDBOX,
            id="onlyboxes",
            label="Onlyboxes",
            platform="linux",
            online=True,
            is_current=True,
        ),
    )
    tool = build_tools(catalog=catalog)[0]
    obs = asyncio.run(tool.execute({}))
    assert obs.success
    payload = obs.payload or {}
    assert payload["current"]["id"] == "onlyboxes"
    assert payload["current"]["is_current"] is True
    assert payload["environments"][0]["id"] == "onlyboxes"
