"""ADR-0256 §6:defer 目录渲染与加载协议.

B1/B3/B4/B5/B7/F1 可直接运行(断言当前实现已具备的机制);
B2/B6 断言 ADR-0256 新增行为,以 skip 锁定.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession

# ADR-0256 §3 的 8 句目录描述(中文版).
DESCRIPTIONS = {
    "core": "推理原语：按需加载工具目录",
    "file": "文件系统：列出、读取、写入、编辑、移动、搜索文件内容",
    "shell": "执行 shell 命令与脚本；危险操作会先请示你",
    "memory": "搜索与写入长期记忆",
    "skill": "技能的发现、安装与调用",
    "web": "联网搜索与网页抓取",
    "agent": "派发子任务、向用户提问",
    "ext": "第三方集成：连接与刷新外部服务",
}

NAMESPACES_8 = list(DESCRIPTIONS)


@dataclass
class FakeTool:
    name: str
    namespace: str = ""
    description: str = ""
    parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.description = self.description or f"fake tool {self.name}"
        self.parameters = self.parameters or {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _tools_8ns() -> tuple[FakeTool, ...]:
    tools = [FakeTool("tool_search", namespace="core")]
    for ns in NAMESPACES_8:
        if ns == "core":
            continue
        tools.append(FakeTool(f"{ns}_tool", namespace=ns))
    return tuple(tools)


def _session(**policy_kw: Any) -> ToolDeferSession:
    kw = {"namespace_descriptions": DESCRIPTIONS}
    kw.update(policy_kw)
    return ToolDeferSession(DeferPolicy(**kw))


def _wire_names(wire: tuple[dict[str, Any], ...]) -> list[str]:
    return [spec["function"]["name"] for spec in wire]


def test_b1_catalog_has_one_line_per_deferred_namespace():
    """目录每行一句话可读,无 'N tools:' fallback 文本(验收 1).

    8 域中 core(tool_search)是 eager 域,直接上 wire 不进目录,
    所以目录恰好 7 行.
    """
    session = _session()
    session.update_turn(_tools_8ns())
    _, catalog = session.render_turn()
    lines = [line for line in catalog.splitlines() if line.startswith("- ")]
    assert len(lines) == 7, f"期望 7 行目录,实际 {len(lines)} 行:\n{catalog}"
    assert "tools:" not in catalog
    assert "- core: " not in catalog
    assert "- tool_search: " not in catalog
    for ns in NAMESPACES_8:
        if ns == "core":
            continue
        assert f"- {ns}: {DESCRIPTIONS[ns]}" in catalog


def test_b2_missing_description_fails_fast():
    """目录描述缺失必须在 update_turn 期抛错,不许退化成 'N tools: ...'."""
    session = ToolDeferSession(DeferPolicy(namespace_descriptions={}))
    with pytest.raises(ValueError, match="namespace"):
        session.update_turn(_tools_8ns())


def test_b3_tool_search_eager_every_turn():
    """core/tool_search 每 turn 都在 wire 上(loader 缺席即死锁)."""
    session = _session()
    session.update_turn(_tools_8ns())
    for _ in range(3):
        wire, _ = session.render_turn()
        assert _wire_names(wire) == ["tool_search"]


def test_b4_unloaded_namespace_contributes_catalog_only():
    """只加载 file 域:memory/shell 等只出现在目录行,不进 wire."""
    session = _session()
    session.update_turn(_tools_8ns())
    session.load_namespace("file")
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search", "file_tool"]
    assert "- memory: " in catalog
    assert "- file: " not in catalog


def test_b5_single_namespace_load_returns_full_schemas():
    """tool_search(namespace='file') 一次返回该域全部工具的完整 schema."""
    tools = [FakeTool("tool_search", namespace="core")] + [
        FakeTool(f"f{i}", namespace="file") for i in range(9)
    ]
    session = _session()
    session.update_turn(tools)
    payload = session.load_namespace("file")
    assert payload["namespace"] == "file"
    assert payload["description"] == DESCRIPTIONS["file"]
    specs = payload["tools"]
    assert len(specs) == 9
    for spec in specs:
        fn = spec["function"]
        assert fn["name"] and fn["description"] and fn["parameters"]


def test_b6_batch_load_multiple_namespaces():
    """load_namespaces(['file','memory']) 一次往返返回两域 schema(验收 6)."""
    session = _session()
    session.update_turn(_tools_8ns())
    payload = session.load_namespaces(["file", "memory"])
    assert payload["namespaces"] == ["file", "memory"]
    names = [s["function"]["name"] for s in payload["tools"]]
    assert names == ["file_tool", "memory_tool"]  # 按传入顺序拼接
    assert session.loaded_namespaces == {"file", "memory"}


def test_b6_batch_load_dedupes_repeated_names_and_rejects_unknown():
    """重复名字只贡献一次 tools;未知名字透出 load_namespace 的 KeyError."""
    session = _session()
    session.update_turn(_tools_8ns())
    payload = session.load_namespaces(["file", "file", "memory"])
    assert payload["namespaces"] == ["file", "memory"]
    assert [s["function"]["name"] for s in payload["tools"]] == ["file_tool", "memory_tool"]
    with pytest.raises(KeyError) as exc:
        session.load_namespaces(["file", "not_a_namespace"])
    assert "not_a_namespace" in str(exc.value)


def test_b7_load_is_idempotent_and_unknown_namespace_errors():
    """重复加载幂等;未知 namespace 抛 KeyError 且错误信息列出已知域."""
    session = _session()
    session.update_turn(_tools_8ns())
    first = session.load_namespace("file")
    second = session.load_namespace("file")
    assert first == second
    with pytest.raises(KeyError) as exc:
        session.load_namespace("not_a_namespace")
    assert "file" in str(exc.value)


def test_f1_defer_disabled_restores_legacy_projection():
    """DeferPolicy(enabled=False) 时回到 legacy:全量 schema,无目录."""
    session = ToolDeferSession(DeferPolicy(enabled=False))
    session.update_turn(_tools_8ns())
    wire, catalog = session.render_turn()
    assert len(wire) == 8
    assert catalog == ""
