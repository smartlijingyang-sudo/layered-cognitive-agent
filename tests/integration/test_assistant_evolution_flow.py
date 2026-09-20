"""助理演化全流程确定性集成测试（Assistant Evolution Flow Deterministic Integration Test）。

覆盖闭环契约：
- Turn 0: 创建助理并初始化隔离 Home 结构（SOUL/USER/AGENTS/goals.yaml/skills/memory）
- Turn 1: 助理自感知 —— PerceiveObserve 节点合并 assistant.bootstrap 投影
- Turn 2: 对话修改用户画像 —— AssistantMemory 捕获身份与偏好，自动触发 ProfileBackfill 回填 USER.md
- Turn 3: 跨轮感知刷新 —— PerceiveObserve 重新投影出最新回填的用户画像
- Turn 4: 助理自主创建 Skill —— create_assistant_skill 经 0067 三闸校验安装至 skills/ 目录
- Turn 5: 激活并读取 Skill —— overlay.activate 成功激活并获取代码审查 SOP

无外部网络依赖，无 LLM API Token 开销，100% 确定性毫秒级执行。
"""

# ruff: noqa: ASYNC240

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool
from lca.nodes.perceive.observe.observe import PerceiveObserveExecutor
from lca.plugins.assistant.profile.profile import make_backfill_callback
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


class _StubPerceiveHub:
    """提供空基础上下文清单的 Hub。"""

    def __init__(self, manifest: ContextManifest | None = None) -> None:
        self._manifest = manifest or ContextManifest(items=())

    async def perceive(self, state: object) -> ContextManifest:
        del state
        return self._manifest


@pytest.mark.asyncio
async def test_assistant_evolution_flow_full_cycle(tmp_path: Path) -> None:
    # ── Turn 0: 创建助理并初始化 Home 结构 ─────────────────────────────────
    assistants_root = tmp_path / "assistants"
    catalog = AssistantCatalogImpl(root=assistants_root)

    handle = catalog.create(
        CreateAssistantRequest(
            name="流程测试演化助理",
            description="验证自感知、记忆知识层与自主技能演化流程",
        )
    )
    assistant_id = handle.assistant_id
    home_path = Path(handle.home_path)

    assert assistant_id, "必须生成合法 assistant_id"
    assert home_path.is_dir(), "必须物化 Home 目录"

    # 断言必要配置面与目录已齐全
    assert (home_path / "SOUL.md").is_file(), "Home 缺失 SOUL.md"
    assert (home_path / "USER.md").is_file(), "Home 缺失 USER.md"
    assert (home_path / "AGENTS.md").is_file(), "Home 缺失 AGENTS.md"
    assert (home_path / "goals.yaml").is_file(), "Home 缺失 goals.yaml"
    assert (home_path / "skills").is_dir(), "Home 缺失 skills 目录"
    assert (home_path / "memory").is_dir(), "Home 缺失 memory 目录"

    initial_user_md = (home_path / "USER.md").read_text(encoding="utf-8")
    assert initial_user_md.strip(), "初始 USER.md 不允许为空 (ADR-0242)"
    assert "架构师李超" not in initial_user_md, "初始 USER.md 不应包含尚未输入的用户信息"

    # ── Turn 1: 助理自我感知验证（Bootstrap 投影注入感知） ──────────────────
    from lca.plugins.assistant.bootstrap.bootstrap import _BootstrapProjectionService

    bootstrap_service = _BootstrapProjectionService(catalog=catalog)
    observe_executor = PerceiveObserveExecutor()

    runtime_ctx: dict[str, Any] = {
        "perceive_hub": _StubPerceiveHub(),
        "assistant_bootstrap": bootstrap_service,
        "assistant_id": assistant_id,
    }
    node_context = NodeContext(runtime=runtime_ctx, metadata={}, budget=None)
    output = await observe_executor.node_execute(
        node_context, NodeInput(port_values={"state": None})
    )

    manifest = output.port_values["manifest"]
    assert isinstance(manifest, ContextManifest)

    # 校验 bootstrap 投影合并效果
    agent_instructions = [
        item
        for item in manifest.items
        if item.kind == "workspace_instructions" and item.payload.get("name") == "AGENTS.md"
    ]
    assert len(agent_instructions) == 1, "Perceive 必须合并来自 Home 的 AGENTS.md 指南"
    assert agent_instructions[0].provenance == f"assistant.bootstrap.{assistant_id}"

    user_artifacts = [
        item
        for item in manifest.items
        if item.kind == "workspace_artifacts" and item.payload.get("name") == "USER.md"
    ]
    assert len(user_artifacts) == 1, "Perceive 必须合并来自 Home 的 USER.md"
    assert user_artifacts[0].provenance == f"assistant.bootstrap.{assistant_id}"

    # ── Turn 2: 对话修改用户画像并触发 USER.md 自动回填 ──────────────────────
    # 挂接由 AssistantCatalog 驱动的真实 ProfileBackfillService 回调
    backfill_callback = make_backfill_callback(catalog)
    memory = AssistantMemory(home_path, profile_backfill=backfill_callback)

    state = AgentState(
        trace_id="trace_turn2",
        task="我是系统架构师李超，主要技术栈是 Python 和 Rust。请记住我：后续方案回复必须简洁扼要、优先给出代码示例与架构图，不要客套话。",
        budget=Budget(),
    )
    obs = Observation(observation_id="obs_turn2", success=True, payload=None)
    reflection = Reflection(
        reflection_id="refl_turn2",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={
            "memory_candidates": [
                {
                    "category": MemoryCategory.IDENTITY.value,
                    "content": "用户身份：系统架构师李超，主要技术栈是 Python 和 Rust",
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "identity:lichao",
                },
                {
                    "category": MemoryCategory.PREFERENCE.value,
                    "content": "用户偏好：回复简洁扼要、优先给出代码示例与架构图、无客套话",
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "preference:concise",
                },
            ]
        },
    )

    # memory.update 触发写入落盘并自动调用 profile_backfill
    await memory.update(state, obs, reflection)

    # 验证物理落盘与回填结果
    updated_user_md = (home_path / "USER.md").read_text(encoding="utf-8")
    assert "## 身份" in updated_user_md, "USER.md 回填后必须包含 身份 段落"
    assert "系统架构师李超" in updated_user_md, "USER.md 回填后必须包含用户姓名与身份"
    assert "Python 和 Rust" in updated_user_md, "USER.md 回填后必须包含技术栈"
    assert "## 偏好" in updated_user_md, "USER.md 回填后必须包含 偏好 段落"
    assert "简洁扼要" in updated_user_md, "USER.md 回填后必须包含简洁偏好"
    assert "代码示例与架构图" in updated_user_md, "USER.md 回填后必须包含代码/架构图偏好"

    # 验证 catalog revision 递增
    spec_after_user = catalog.get(assistant_id)
    assert spec_after_user.revision_seq >= 1, "回填 USER.md 必须递增 catalog revision_seq"

    # ── Turn 3: 跨轮感知刷新验证（读取更新后的 USER.md） ─────────────────────
    output_t3 = await observe_executor.node_execute(
        node_context, NodeInput(port_values={"state": None})
    )
    manifest_t3 = output_t3.port_values["manifest"]
    user_item_t3 = next(
        item
        for item in manifest_t3.items
        if item.kind == "workspace_artifacts" and item.payload.get("name") == "USER.md"
    )
    assert "系统架构师李超" in user_item_t3.payload.get("text", ""), (
        "跨轮新感知中注入的 USER.md 必须包含回填后的最新身份信息"
    )

    # ── Turn 4: 助理自主创建并安装 Skill ───────────────────────────────────
    overlay = AssistantSkillOverlayImpl(catalog=catalog)
    create_skill_tool = AssistantCreateSkillTool(overlay=overlay, assistant_id=assistant_id)

    skill_source_md = (
        "---\n"
        "name: code-review-helper\n"
        "description: 专用于代码审查的辅助技能与标准规范 SOP\n"
        "references: []\n"
        "---\n"
        "# 代码审查助手\n\n"
        "## 代码审查五步 SOP\n"
        "1. 检查契约与不变量\n"
        "2. 检查边界条件与异常处理\n"
        "3. 检查资源释放与文件句柄泄露防护（必须使用上下文管理器）\n"
        "4. 检查日志与可观测性\n"
        "5. 给出改进建议与重构代码示例\n"
    )

    create_obs = await create_skill_tool.execute({"skill_md": skill_source_md})
    assert create_obs.success is True, f"create_assistant_skill 工具执行失败: {create_obs.error}"
    assert create_obs.payload["skill_id"] == "code-review-helper"

    # 检查物理落盘
    installed_skill_md_path = home_path / "skills" / "code-review-helper" / "SKILL.md"
    assert installed_skill_md_path.is_file(), "Skill 必须成功落盘到 Home skills/ 目录"
    assert "代码审查五步 SOP" in installed_skill_md_path.read_text(encoding="utf-8")

    # 检查 manifest 验证状态
    manifest_json = json.loads((home_path / "manifest.json").read_text(encoding="utf-8"))
    skills_map = manifest_json.get("skills", {})
    assert "code-review-helper" in skills_map
    assert skills_map["code-review-helper"]["artifact_state"] == "verified"

    # ── Turn 5: 激活并读取 Skill（供执行代码审查） ─────────────────────────
    activation_receipt = overlay.activate(
        assistant_id, "code-review-helper", actor="agent:code-reviewer"
    )
    assert activation_receipt.skill_id == "code-review-helper"
    assert activation_receipt.artifact_state == "verified"
    assert activation_receipt.actor == "agent:code-reviewer"

    # 验证技能包已在 Home 激活可读
    active_skill_text = (home_path / "skills" / activation_receipt.skill_id / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "检查资源释放与文件句柄泄露防护" in active_skill_text
    assert "给出改进建议与重构代码示例" in active_skill_text
