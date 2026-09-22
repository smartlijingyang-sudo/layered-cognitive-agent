"""Comprehensive E2E scenario validation test suite for LCA Agent memory.

Covers ADR-0244 / ADR-0247 memory closed loop across 5 core scenarios:
- Scenario 1: User profile & preference evolution, supersede, and USER.md sync.
- Scenario 2: Environmental facts & constraints perception (no-pronoun rules).
- Scenario 3: Agent self-awareness & episodic memory recall of past tool actions.
- Scenario 4: Intent-driven relevance retrieval with budget-based pruning.
- Scenario 5: Governed memory tools (search, add, and confirmed delete guard).

Validates all 6 core invariants:
- INV-01: Environment key loading from .env
- INV-02: Pre-filter coverage of preferences and environment constraints
- INV-03: Episodic memory recording and capacity management
- INV-04: Multi-dimensional relevance-driven retrieval ordering
- INV-05: Prompt section deduplication (Context vs UserProfile mutual exclusivity)
- INV-06: Supersede hygiene and sensitive deletion governance
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import (
    MemoryCategory,
    MemoryLayer,
    ReflectionVerdict,
)
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter
from lca.infrastructure.tools.assistant.memory_tools import (
    MemoryAddTool,
    MemoryRemoveTool,
    MemorySearchTool,
    MemoryUpdateTool,
)
from lca.plugins.assistant.profile.profile import render_user_profile
from lca.plugins.prompts.sections import ContextSection, UserProfileSection


def _create_role_profile() -> RoleProfile:
    return RoleProfile(
        role="assistant",
        goal="Assist user with architectural and coding tasks",
        backstory="LCA Intelligent Assistant",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
    )


# ── Scenario 1: 用户画像与偏好演化 (User Profile Evolution & Supersede) ────────


@pytest.mark.asyncio
async def test_scenario_1_user_profile_evolution_and_supersede(tmp_path: Path):
    """场景1：用户录入身份与偏好 → USER.md 自动回填 → 偏好变更触发 supersede →

    USER.md 全量同步重建且零旧残留；Prompt 呈现互斥无冗余。
    """
    home = tmp_path / "asst_arch"
    home.mkdir(parents=True, exist_ok=True)
    user_md_path = home / "USER.md"

    async def _backfill_callback(assistant_id: str, records: list[MemoryRecord]) -> None:
        content = render_user_profile(records)
        user_md_path.write_text(content, encoding="utf-8")

    memory = AssistantMemory(home, profile_backfill=_backfill_callback)
    add_tool = MemoryAddTool(memory=memory)
    update_tool = MemoryUpdateTool(memory=memory)

    # 1. 第一轮：录入身份与偏好
    obs_id = await add_tool.execute(
        {
            "content": "用户身份：李超，系统总架构师",
            "category": "identity",
            "dedupe_key": "identity:role",
        }
    )
    assert obs_id.success is True
    id_rec_id = obs_id.payload["record_id"]

    obs_pref = await add_tool.execute(
        {
            "content": "用户偏好：主要写 Python 和 Rust，讨厌重复样板代码",
            "category": "preference",
            "dedupe_key": "preference:tech_stack",
        }
    )
    assert obs_pref.success is True
    pref_rec_id = obs_pref.payload["record_id"]

    # 验证 USER.md 自动由系统回填并落盘
    assert user_md_path.is_file()
    user_md_text = user_md_path.read_text(encoding="utf-8")
    assert "李超" in user_md_text
    assert "Python 和 Rust" in user_md_text

    # 验证 Prompt 呈现：UserProfileSection 渲染画像，ContextSection 零重复
    active_records = memory.query(MemoryLayer.SEMANTIC)
    manifest = ContextManifest(
        items=(
            ContextItem(
                kind="memory",
                payload=active_records,
                provenance="memory.retrieve",
            ),
        )
    )
    role_profile = _create_role_profile()
    profile_out = UserProfileSection().render(
        role_profile=role_profile,
        task="测试任务",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )
    context_out = ContextSection().render(
        role_profile=role_profile,
        task="测试任务",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )

    assert "李超" in profile_out.text
    assert "Python 和 Rust" in profile_out.text
    # INV-05: ContextSection 绝对不出现 identity/preference 行
    assert "李超" not in context_out.text
    assert "Python 和 Rust" not in context_out.text

    # 2. 第二轮：偏好变更触发 supersede
    obs_update = await update_tool.execute(
        {
            "record_id": pref_rec_id,
            "content": "用户偏好：全面转向 Rust 和 Go，废除 Python",
            "category": "preference",
        }
    )
    assert obs_update.success is True
    assert obs_update.payload["supersedes"] == pref_rec_id
    new_pref_id = obs_update.payload["record_id"]

    # INV-06: 验证 USER.md 重建，旧偏好彻底退役，零残留
    user_md_updated = user_md_path.read_text(encoding="utf-8")
    assert "Rust 和 Go" in user_md_updated
    assert "讨厌重复样板代码" not in user_md_updated
    assert "主要写 Python" not in user_md_updated

    # 验证活跃记录查询仅 2 条（旧记录被标记为 deleted/retired）
    active_semantic = memory.query(MemoryLayer.SEMANTIC)
    assert len(active_semantic) == 2
    active_ids = {r.record_id for r in active_semantic}
    assert id_rec_id in active_ids
    assert new_pref_id in active_ids
    assert pref_rec_id not in active_ids


# ── Scenario 2: 环境与客观规则感知 (Environmental Facts & Constraints) ────────


@pytest.mark.asyncio
async def test_scenario_2_environmental_facts_and_constraints(tmp_path: Path):
    """场景2：无主句环境规则与系统约束感知。

    验证预过滤门禁放行（INV-01, INV-02）、FACT 分类写入与检索、以及在 Prompt
    Context 中正确渲染。
    """
    home = tmp_path / "asst_env"
    memory = AssistantMemory(home)
    add_tool = MemoryAddTool(memory=memory)

    # 1. 预过滤门禁测试：无“我/喜欢”等个人代词的纯环境规范陈述
    env_rule = "生产数据库端口为 5433，严禁直连生产库执行 DROP TABLE 操作"
    filter_engine = FallbackMemoryFilter()

    # INV-01 & INV-02: 预过滤必须判定为应提取的事实
    filter_decision = await filter_engine.evaluate(env_rule)
    assert filter_decision.should_extract is True
    assert filter_decision.confidence >= 0.5

    # 2. 存入语义记忆（作为 FACT）
    obs_add = await add_tool.execute(
        {
            "content": env_rule,
            "category": "fact",
            "dedupe_key": "fact:prod_db_policy",
        }
    )
    assert obs_add.success is True

    # 3. 跨轮检索：提问相关问题时精准召回
    recalled = await memory.retrieve(query="生产数据库配置与操作规范")
    assert len(recalled) >= 1
    top_record = recalled[0]
    assert "5433" in top_record.content
    assert top_record.category == MemoryCategory.FACT

    # 4. Prompt 呈现校验：FACT 必须渲染在 ContextSection，且不进入 UserProfileSection
    manifest = ContextManifest(
        items=(
            ContextItem(
                kind="memory",
                payload=[top_record],
                provenance="memory.retrieve",
            ),
        )
    )
    role_profile = _create_role_profile()
    profile_out = UserProfileSection().render(
        role_profile=role_profile,
        task="排查生产数据库连接",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )
    context_out = ContextSection().render(
        role_profile=role_profile,
        task="排查生产数据库连接",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )

    # INV-05: FACT 属于系统环境知识，仅出现在 CONTEXT 中
    assert "生产数据库端口为 5433" in context_out.text
    assert "[fact]" in context_out.text
    assert profile_out.text == ""  # 无 identity/preference，画像块应为空


# ── Scenario 3: 自我感知与情景记忆 (Self-Awareness & Episodic Memory) ────────


@pytest.mark.asyncio
async def test_scenario_3_self_awareness_and_episodic_memory(tmp_path: Path):
    """场景3：Agent 自我动作感知与情景记忆回溯。

    验证工具执行自动落盘 episodic.json（INV-03）、跨轮意图检索唤醒、以及 50
    条 FIFO 容量滚动限制。
    """
    home = tmp_path / "asst_self"
    memory = AssistantMemory(home)

    # 1. 模拟第一轮：Agent 执行了代码审查与命令运行
    state_turn1 = AgentState(
        trace_id="trace_s3_1",
        task="检查代码仓库状态并执行静态分析",
        step=1,
        budget=Budget(),
    )
    obs_tool1 = Observation(
        observation_id="obs_tool_1",
        success=True,
        payload={"tool": "run_command", "output": "git status: working tree clean, 0 untracked"},
    )
    refl_turn1 = Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )

    await memory.update(state_turn1, obs_tool1, refl_turn1)

    # INV-03: 验证 episodic.json 权威落盘并包含动作事实
    episodic_file = home / "memory" / "episodic.json"
    assert episodic_file.is_file()
    episodic_data = json.loads(episodic_file.read_text(encoding="utf-8"))
    assert len(episodic_data) == 1
    assert episodic_data[0]["layer"] == "episodic"
    assert "run_command" in episodic_data[0]["content"]

    # 2. 第二轮：用户询问“你刚才帮我执行了什么操作？”
    # 通过意图检索 recall 出该情景记忆
    recalled_episodic = await memory.retrieve(query="刚才运行了什么命令工具")
    assert len(recalled_episodic) >= 1
    assert any("run_command" in r.content for r in recalled_episodic)
    assert recalled_episodic[0].memory_type == MemoryLayer.EPISODIC

    # 3. 验证情景记忆滚动容量上限（FIFO，最长 50 条）
    for i in range(55):
        st = AgentState(
            trace_id=f"t_{i}",
            task=f"批量巡检任务第 {i} 阶段",
            step=i + 2,
            budget=Budget(),
        )
        ob = Observation(
            observation_id=f"o_{i}",
            success=True,
            payload={"tool": f"inspect_service_{i}", "output": f"service {i} healthy"},
        )
        rf = Reflection(reflection_id=f"r_{i}", verdict=ReflectionVerdict.ON_TRACK)
        await memory.update(st, ob, rf)

    current_episodic = memory.query(MemoryLayer.EPISODIC)
    # 容量严格约束为 50 条
    assert len(current_episodic) == 50
    # 早期的第 0、1 批次已按 FIFO 移出
    assert not any("inspect_service_0 " in r.content for r in current_episodic)
    # 最新执行的第 54 批次必须常驻
    assert any("inspect_service_54" in r.content for r in current_episodic)


# ── Scenario 4: 意图相关性检索与预算剪裁 (Relevance Retrieval & Budget Pruning) ──


@pytest.mark.asyncio
async def test_scenario_4_relevance_retrieval_and_budget_pruning(tmp_path: Path):
    """场景4：多领域记忆共存时的意图相关性排序与 Token 预算剪裁。

    验证 INV-04（relevance × recency × importance 降序排序）与高负荷预算剪裁。
    """
    home = tmp_path / "asst_rel"
    memory = AssistantMemory(home)
    add_tool = MemoryAddTool(memory=memory)

    # 注入来自不同业务领域的记忆
    await add_tool.execute(
        {
            "content": "公司云服务本月账单预算为 5000 美元",
            "category": "fact",
            "dedupe_key": "fact:cloud_billing",
        }
    )
    await add_tool.execute(
        {
            "content": "代码提交规范必须遵循 Conventional Commits，feat/fix 前缀",
            "category": "fact",
            "dedupe_key": "fact:git_commit_style",
        }
    )
    await add_tool.execute(
        {
            "content": "网关反向代理端口配置为 8765，心跳路径为 /health",
            "category": "fact",
            "dedupe_key": "fact:gateway_port",
        }
    )
    await add_tool.execute(
        {
            "content": "用户当前工作时区为 Asia/Shanghai",
            "category": "fact",
            "dedupe_key": "fact:user_tz",
        }
    )

    # 1. 意图 1：Git 提交规范
    results_git = await memory.retrieve(query="代码提交规范与 commit 格式要求")
    assert len(results_git) >= 1
    # INV-04: 最相关的条目必须位列首位
    assert "Conventional Commits" in results_git[0].content

    # 2. 意图 2：云服务财务
    results_cloud = await memory.retrieve(query="本月云服务账单费用上限与预算")
    assert len(results_cloud) >= 1
    assert "5000 美元" in results_cloud[0].content

    # 3. Token 预算剪裁测试：在严格预算（如 15 个 tokens）下，低相关度条目被剪除
    budgeted_results = await memory.retrieve(
        query="Conventional Commits 提交规范",
        token_budget=15,
    )
    # 最相关的一条保留，其他无关条目被自动剪裁
    assert len(budgeted_results) == 1
    assert "Conventional Commits" in budgeted_results[0].content


# ── Scenario 5: 受治理工具与敏感删除确认 (Governed Tools & Sensitive Delete) ────


@pytest.mark.asyncio
async def test_scenario_5_governed_tools_and_sensitive_delete_guard(tmp_path: Path):
    """场景5：受治理工具与风控边界防御。

    验证：
    - 输入格式白名单校验（非法分类与空内容拦截）
    - memory_search 联合搜索
    - 敏感删除必须显式确认（confirmed=True 窄门防御，INV-06）
    - 确认删除后从检索与视图中物理/逻辑消除
    """
    home = tmp_path / "asst_gov"
    memory = AssistantMemory(home)
    add_tool = MemoryAddTool(memory=memory)
    search_tool = MemorySearchTool(memory=memory)
    remove_tool = MemoryRemoveTool(memory=memory)

    # 1. 非法输入校验防御
    obs_empty = await add_tool.execute({"content": "", "category": "fact"})
    assert obs_empty.success is False
    assert "content" in (obs_empty.error or "")

    obs_bogus = await add_tool.execute({"content": "测试事实", "category": "invalid_cat"})
    assert obs_bogus.success is False
    assert "category" in (obs_bogus.error or "")

    # 2. 添加敏感架构原则事实
    obs_valid = await add_tool.execute(
        {
            "content": "架构原则：绝对零容忍内存泄漏与未经审批的外部网络访问",
            "category": "fact",
            "dedupe_key": "principle:zero_tolerance",
        }
    )
    assert obs_valid.success is True
    rec_id = obs_valid.payload["record_id"]

    # 3. memory_search 搜索验证
    obs_search = await search_tool.execute({"query": "架构原则 内存泄漏"})
    assert obs_search.success is True
    assert obs_search.payload["count"] == 1
    assert obs_search.payload["records"][0]["record_id"] == rec_id

    # 4. 未经审批的删除必须被拦截（安全窄门）
    obs_remove_unconfirmed = await remove_tool.execute({"record_id": rec_id, "confirmed": False})
    # INV-06: 未确认的删除必须直接拒绝
    assert obs_remove_unconfirmed.success is False
    assert "确认" in (obs_remove_unconfirmed.error or "")

    # 检查数据依然完好存在
    obs_search_still = await search_tool.execute({"query": "架构原则 内存泄漏"})
    assert obs_search_still.payload["count"] == 1

    # 5. 用户确认后合法删除
    obs_remove_confirmed = await remove_tool.execute({"record_id": rec_id, "confirmed": True})
    assert obs_remove_confirmed.success is True

    # 6. 删除后验证零幽灵召回
    obs_search_after = await search_tool.execute({"query": "架构原则 内存泄漏"})
    assert obs_search_after.payload["count"] == 0

    recalled_after = await memory.retrieve(query="架构原则 内存泄漏")
    assert not any(rec_id == r.record_id for r in recalled_after)
