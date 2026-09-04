"""ToolSchema.from_manifest 桥 —— ToolManifest → ToolSchema 单向投影。

锁语义（D3 收口）：
- LobeHub 风格 ``ToolManifest`` 与 OpenAI 风格 ``ToolSchema`` 之间的唯一
  桥接方向是 ``ToolSchema.from_manifest``；
- 多 api manifest 必须显式选名，否则拒收；
- renderer 侧概念（ParameterSpec / ui_hint）不进入 LLM 边界 schema。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.tool import ParameterSpec, ToolApi, ToolManifest
from lca.contracts.observability.loop_cursor_payloads import ToolSchema


def _manifest(*apis: ToolApi, identifier: str = "demo.tool") -> ToolManifest:
    return ToolManifest(identifier=identifier, type="builtin", api=apis)


def test_from_manifest_projects_single_api() -> None:
    manifest = _manifest(
        ToolApi(name="run", description="Run it", parameters={"type": "object"}),
    )
    schema = ToolSchema.from_manifest(manifest)
    assert schema.name == "run"
    assert schema.description == "Run it"
    assert schema.parameters == {"type": "object"}
    assert schema._extras == {"identifier": "demo.tool"}


def test_from_manifest_selects_named_api() -> None:
    manifest = _manifest(
        ToolApi(name="a", description="A", parameters={}),
        ToolApi(name="b", description="B", parameters={"type": "object"}),
    )
    schema = ToolSchema.from_manifest(manifest, api_name="b")
    assert schema.name == "b"
    assert schema.to_openai_dict()["function"]["name"] == "b"


def test_from_manifest_rejects_multi_api_without_name() -> None:
    manifest = _manifest(
        ToolApi(name="a", description="A", parameters={}),
        ToolApi(name="b", description="B", parameters={}),
    )
    with pytest.raises(ValueError, match="api_name"):
        ToolSchema.from_manifest(manifest)


def test_from_manifest_rejects_unknown_api_name() -> None:
    manifest = _manifest(ToolApi(name="a", description="A", parameters={}))
    with pytest.raises(ValueError, match="no api"):
        ToolSchema.from_manifest(manifest, api_name="missing")


def test_from_manifest_excludes_renderer_side_parameters_spec() -> None:
    """ParameterSpec / ui_hint 是 renderer 概念，不出现在 LLM 边界 schema。"""
    manifest = ToolManifest(
        identifier="demo.tool",
        type="builtin",
        api=(ToolApi(name="run", description="", parameters={"type": "object"}),),
        parameters={"path": ParameterSpec(type="string", ui_hint="path")},
    )
    schema = ToolSchema.from_manifest(manifest)
    assert "ui_hint" not in schema.to_openai_dict()["function"]
    assert schema.parameters == {"type": "object"}
