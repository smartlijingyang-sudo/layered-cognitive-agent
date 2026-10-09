"""代码规范健身函数 —— 命名禁用词、文件行数、层职责、术语覆盖。

与 test_architecture_conformance.py（分层维度）并列，
覆盖"合理性 / 命名 / 目录"维度的微观治理。

ADR-0291 Phase A（2026-10-05，tests lane 一次重写）：
- 修正 `_PROJECT_ROOT` 指针（原误指 tests/scenario/，致四个测试全部空心）
  + C2 路径指针自检（TestRepoRootPointer；实测发现 tests/lca/ 真实存在，
  单 `lca/` 标记会误通过，故要求 pyproject.toml + lca/contracts 双标记）
- 层 docstring 测试语义重写：`layer*` glob（lca/ 下无此布局，恒空）
  → 显式五层清单（contracts/infrastructure/cognition/runtime/agent）
- reverse 扫描包去掉已不存在的 `lca.plugins.loop.phase`
  → 换现行 `lca.plugins.loop.{control,driver,graph,reducer}`
- C1 基数门：文件扫描 ≥2500 / 类扫描 ≥700（banned+forward）/
  reverse 类扫描 ≥1700，0 基数直接 fail（fail-closed）
- `_LINE_COUNT_EXEMPT` 死键清理：52 → 23（包化搬迁跟随改键、重复登记合并、
  已删除/已降到限额下/后继不明的条目删除；理由原文保留）

Phase A 落地后 ①③④ 预期红（真实债务信号，钉住即是进步）：
① 约 130+ 文件超 250 行待 Phase C 豁免审计；③ 约 69 类词根待 Phase B 补词条；
④ 现役术语缺类待 Phase B 移入「已废弃主名」表。② 按新语义执行。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
import types
import unittest
from pathlib import Path

# ADR-0291 Phase A：修正为仓库根（本文件在 tests/scenario/code/ 下，需上溯四级）。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LCA_ROOT = _PROJECT_ROOT / "lca"
_GLOSSARY_PATH = _PROJECT_ROOT / "docs" / "specs" / "glossary.md"


class TestRepoRootPointer(unittest.TestCase):
    """C2 路径指针自检：仓库根指针必须能命中仓库特征标记。

    指针漂移 = 直接红，不许恒绿/恒 skip。本测试是其他四个测试的
    fail-closed 前哨：若指针错误，C1 基数门会连带打红。

    注：单 `lca/` 目录不足以做标记 —— tests/lca/ 真实存在（按 lca 包布局
    镜像的测试目录，git 跟踪中），`_PROJECT_ROOT` 误指 tests/ 时朴素的
    `lca/` 存在性检查会误通过（2026-10-05 Phase A 实测捕获）。
    故要求 pyproject.toml 与 lca/contracts 同时存在。
    """

    def test_repo_root_markers_exist(self) -> None:
        self.assertTrue(
            (_PROJECT_ROOT / "pyproject.toml").is_file(),
            f"_PROJECT_ROOT 指针漂移：{_PROJECT_ROOT} 下找不到 pyproject.toml",
        )
        self.assertTrue(
            (_LCA_ROOT / "contracts").is_dir(),
            f"_PROJECT_ROOT 指针漂移：{_LCA_ROOT / 'contracts'} 不是目录"
            "（tests/lca/ 等镜像目录不能冒充仓库根）",
        )


# C1 基数门（ADR-0291 §4）：扫描基数为 0 即 fail，禁止静默 pass/skip。
# 阈值取 2026-10-05 Phase A 实测略低于实际值（防抖动）：
#   文件扫描实测 2613 → 门 2500；scan5 类扫描实测 757 → 门 700；
#   reverse 类扫描实测 1845 → 门 1700。
# 注：ADR-0291 §5③ 曾建议 800/400；实测 scan5 类仅 757
# （≥800 会在健康基线上误红），文件实测 2613（≥400 形同虚设），
# 故按"略低于实际"原则取实测值钉住。
_MIN_FILE_SCAN_COUNT = 2500
_MIN_CLASS_SCAN_COUNT = 700
_MIN_REVERSE_CLASS_SCAN_COUNT = 1700

# ── 命名禁用词 ──────────────────────────────────────────────────────────
_BANNED_CLASS_PATTERN = re.compile(
    r"(Manager|Util|Utils|Helper|Handler|Processor|Advanced)"
    r"|(Data|Info)$",
)

# 显式豁免清单（参照 docs/design/naming-constitution.md，命名宪法 ADR-0106）
_NAME_EXEMPT: dict[str, str] = {
    # Action 策略类：Operation 后缀表达策略模式插槽，非禁用词 Manager/Helper
    "RespondOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "UseToolOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "DelegateOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "HandoffOperation": "Action 策略实现（contracts.protocols.action.Action）",
    # Observability 命名：SpanContextInfo 是 OTel SDK 兼容的 dataclass（非 Info/Helper 类）
    "SpanContextInfo": "OTel span context 信息封装（兼容 OTel SDK 命名约定）",
    # ADR-0290 豁免：SpineHandler 为每 EP 单请求处理，Handler 系命名宪法 §4.1 合法后缀
    # （健身函数误杀；本 ADR 即 §13 Phase E 要求的豁免归档）
    "SpineHandler": "ADR-0290 豁免：每 EP 单请求处理的 reflector 句柄（命名宪法 §4.1）",
}

_SCAN_PACKAGES = [
    "lca.infrastructure",
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
]

# Forward glossary coverage test only checks LCA core (not gateway).
# Gateway is a separate concern; its terms are listed in glossary.md
# under "Gateway 概念" but not required to have bold entries.
_GLOSSARY_COVERAGE_SCAN_PACKAGES = [
    "lca.infrastructure",
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
]

# ── 文件行数上限 ─────────────────────────────────────────────────────────
_MAX_FILE_LINES = 250

# 已登记豁免（引用 ADR 或说明原因）。
# 2026-10-05 Phase A 死键清理（ADR-0291）：52 → 23。
# - 包化搬迁（<name>.py → <name>/<name>.py）跟随改键，理由原文保留；
# - 点分隔死键（从未生效）映射到现行路径；
# - 重复登记合并为一条（cli commands/tools、services/daemon、services/lobehub、
#   journal/engine/journal_io、journal/engine/engine）；
# - 删除：模块已删除（phase_graph_compiler、fact_stream、graph_validation、
#   outcome_projection、phase_governance、event_doc、runtime_exec、
#   plan_template、command_envelope、compiler、fact_stream_projector、
#   console_projector、openai_compat、simple_memory、journal_catalog）、
#   已降到限额下（api/spawn 131、reasoner 237、artifact 150、safe_executor 59、
#   capability_plan 158、declarative_phase_graph 90、cli/cli 158、
#   host_runtime user 拆分后各文件均 <250、openai_compat 包化后各文件均 <250）、
#   后继不明（contracts/protocols/plan.py，原模块消失、无明确后继）。
_LINE_COUNT_EXEMPT: dict[str, str] = {
    "lca/harness/profile/resolve/resolve.py": (
        "ADR-0061 resolve 阶段：深合并、from_env、DAG、校验集中于单一入口"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/harness/profile/resolve/source.py": (
        "Profile 输入适配器集中 YAML 来源、补丁来源与语义化配置解析，避免解析规则跨模块泄漏"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/infrastructure/cli/commands/runs/tools.py": (
        "CLI 工具子命令集中 registration、provider 装载、CLI 渲染、命令装配（Phase C #5 合并 ops 后）；"
        "coding-agent tools CLI 封装（ADR-0065 §六 / PR-9）：9 个只读子命令从旧 cli.py 拆出"
        "（2026-10-05 Phase A：两条重复登记合并，键随搬迁更新）"
    ),
    "lca/infrastructure/cli/services/daemon/daemon.py": (
        "Daemon lifecycle 服务集中 dispatch + run loop + shutdown coordination（Phase C #5 合并 ops 后）；"
        "Daemon 单模块承载 process 管理 + uptime + health"
        "（2026-10-05 Phase A：两条重复登记合并，键随包化搬迁更新）"
    ),
    "lca/infrastructure/cli/services/lobehub/lobehub.py": (
        "LobeHub streaming adapter 集中 SSE + ChunkBuilder + Encoder 装配（Phase C #5 合并 ops 后）；"
        "LobeHub deploy service 单模块承载 dev/prod/restart/logs/upgrade"
        "（2026-10-05 Phase A：两条重复登记合并，键随包化搬迁更新）"
    ),
    "lca/cognition/body/actions/action_handlers.py": (
        "Body 动作分发单模块（委派/工具/记忆/收口）；ADR-0049 证据平面与 harvest 同文件"
    ),
    "lca/contracts/models/observability/journal/journal.py": (
        "Journal 叙事词表单文件（ADR-0037）；ToolInvoked.plugin_state UI 一等字段（ADR-0053）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/infrastructure/skills/marketplace/marketplace.py": (
        "Skill marketplace 单模块承载发现/加载/注册全链路（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/application/authoring/casting.py": (
        "Team casting 单模块承载角色映射与团队组装"
        "（2026-10-05 Phase A：lca/application/casting.py → authoring/casting.py，键随路径更新）"
    ),
    "lca/infrastructure/sandbox/runtime/runtime.py": (
        "Sandbox Protocol 单模块承载 session/ready/exec 全链路（ADR-0043~0047）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/infrastructure/observability/journal/engine/engine.py": (
        "Journal RunStore 单模块承载注册表/订阅/写盘/状态机（ADR-0055 + ADR-0037）；"
        "Phase B 拆分保留单文件以维持 RunStore 内部一致性；"
        "RunStore 单模块承载事件索引 + get/get_event/get_blob/find_terminal（PR2 / PR6 / PR10 集中落地）"
        "（2026-10-05 Phase A：两条重复登记合并）"
    ),
    "lca/infrastructure/observability/journal/engine/journal_io.py": (
        "Journal IO 单模块承载序列化/反序列化/批量写盘/校验（ADR-0055）；"
        "序列化与持久化耦合紧密，未拆分；"
        "Journal v2 envelope IO（read / write / disk format；PR-3 + PR-6）"
        "（2026-10-05 Phase A：两条 journal_io 登记指向同一合并后文件，合并为一条）"
    ),
    "lca/infrastructure/observability/journal/console/projector.py": (
        "Journal ConsoleProjector 集中 console + sequence diagram + table 输出渲染"
    ),
    "lca/contracts/capabilities.py": (
        "L4 组合根 capability 注册中心 — STOP_RULES 由 C6 port 引入（C4 后向兼容 alias），"
        "无法拆到子模块"
    ),
    "lca/contracts/protocols/__init__.py": (
        "contracts/protocols re-export hub（所有 contracts 子模块类型统一导出）"
    ),
    "lca/infrastructure/observability/__init__.py": (
        "observability 模块统一 re-export（journal / evidence / otel）"
    ),
    "lca/infrastructure/observability/events/event/descriptors_data.py": (
        "Journal event descriptor 注册表（ADR-0065 PR-7 source inversion 单一源）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/infrastructure/observability/facade/facade/facade.py": (
        "observability 主 facade（record / record_runtime / observe_operation）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/runtime/loop/runtime_loop.py": (
        "CognitiveRuntime 单模块承载 v3 6 阶段闭环编排 + 协议边界 record()"
        "（perceive→think→act→reflect→remember→stop，ADR-0002 + PR10 落地）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/framework/graph/interpreter.py": (
        "ADR-0194 解释边界 shim，延迟导入 PlanInterpreterAdapter"
        "（2026-10-05 Phase A：lca/harness/graph/execute/interpreter.py → "
        "framework/graph/interpreter.py，键随路径更新）"
    ),
    "lca/loop/driver.py": ("ADR-0075 DeclarativeRuntimeDriver 统一 pause/resume/result 出口"),
    "lca/cognition/body/executor/pipeline_safe_executor.py": (
        "PipelineSafeExecutor 单模块承载五阶段管线 + finalize（v3 §9.1/9.2）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/application/api/api.py": (
        "L4 门面单文件承载 Agent / Team / cast 入口（ADR-0005）"
        "（2026-10-05 Phase A：随包化搬迁改键）"
    ),
    "lca/agent/cognitive_agent.py": (
        "CognitiveAgent 单 agent 运行单元（Runtime + RoleProfile 可调度单元：run/resume/cancel）（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/application/routine/tick.py": (
        "ADR-0263 T5/C5 RoutineTickDriver：tick 驱动 + 失败隔离/重试退避/dead-letter 状态机（7 类）；C5 "
        "状态机拆散割裂不变量（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/application/runtime/coordinator/event_translator.py": (
        "StampedEvent → AgentStreamEvent.data 纯 fold（EventTranslator 单类 + wire "
        "helper）；活动流投影单点（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/body/emit/tool_journal.py": (
        "ToolStarted/Invoked/Denied prepare+record+emit 三件套函数族；证据平面缝单文件（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/body/executor/safe_executor/executor.py": (
        "SimpleSafeExecutor "
        "单管线：permission→validate→ToolStarted→cache→retry→execute→ToolInvoked（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/body/executor/simple_body.py": (
        "SimpleBody 默认 Body 实现：显式 ActionRegistry 分发 + Observation 投影 helper；执行器边界内聚（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/body/tools/tool_batch_executor.py": (
        "ToolBatchExecutor 单类：model 批工具调用经 SafeExecutor 缝的单一执行入口；_canonicalise/_resolve_* "
        "围绕单批执行内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/brain/decision_gates/loop/multi_tool_breaker.py": (
        "ADR-0214 PR-B 多工具循环断路器（MultiToolLoopBreakerGate + verdict + 置信度/指纹 helper）；gate "
        "单职责内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/consolidation.py": (
        "ADR-0277 §2.3 remember 显式 consolidation 四决策：RuleDecider/LayaDecider 可互换决策器族（2026-10-05 "
        "Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/laya_backend.py": (
        "ADR-0277 Phase 4 Laya System-1 决策后端（LayaScoreEngine + LayaScore/LayaDecision）：评分与 "
        "consolidation 决策单文件（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/sensors.py": (
        "ADR-0277 Phase 2 perceive 记忆传感器注册表：9 传感器/percept 类 + 6 校验/评分 helper；注册表单文件（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/simple/memory.py": (
        "SimpleMemorySystem 四类记忆最小实现单类（Working/Semantic/Episodic/Procedural）；记忆系统边界内聚（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/temporal/memory.py": (
        "TemporalMemorySystem 单类（durable TemporalMemoryStore "
        "背后的查询感知时序记忆）；认知生命周期记忆系统单实现（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/atoms/plan/template.py": (
        "ADR-0069 §五 PlanTemplate 12 标准模板词表单文件（PlanTemplateId/PlanTemplate + "
        "构造器）；模板拆散会破坏契约单一事实源（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/harness/composition/plugin_contract.py": (
        "ADR-0069 §六 + ADR-0199 §3.1 PluginContract 10 段契约词表单文件（10 契约类 + fold/compose "
        "helper）；契约拆散会破坏声明单一事实源（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/harness/memory/events.py": (
        "session 事件契约词表（spec §2.2.3，30+ 事件类）；契约词汇单文件（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① "
        "仲裁；Phase D 点亮）"
    ),
    "lca/contracts/models/cognition/prompt_assembly.py": (
        "ADR-0175 prompt 装配契约词表单文件（Section/Template/Trace 16 类 + 3 归一化函数）；契约拆散会破坏装配 seam "
        "单一事实源（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/models/observability/activity.py": (
        "Activity 动态栏模型词表（ActivityStatus/Category/Item/StepEvidence）+ step 解析；模型定义集中（2026-10-05 "
        "Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/observability/event/meta_event_taxonomy.py": (
        "Meta-event taxonomy 词表 SSOT（MetaEventDomain/Plane Literal + 事件键元组 + MetaEventSlot）；全 run "
        "栈可观测性单一事实源，拆散破坏“先登记再发布”的调试契约（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/protocols/act/command/envelope.py": (
        "ADR-0068/ADR-0074 PR-7 数据契约词表（CommandEnvelope/RunFact/RunDelta/Verdict + "
        "factory/helper）；契约词汇单文件是仲裁设计，拆散破坏 effect 唯一入口的事实源（2026-10-05 Phase C batch-3 审计，ADR-0291 "
        "§5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/protocols/declarative/declarative_1/declarative_graph.py": (
        "声明式阶段图数据契约词表（14 类：PhaseNode/PhaseEdge/EffectPolicyPlan/ActionAuthorityPlan "
        "等）；契约词汇集中声明是仲裁设计（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/contracts/transport/agent_stream_event.py": (
        "AgentStreamEvent union wire 契约词表单文件（33 类，TS types.ts 1-54 镜像）；跨语言契约镜像必须单文件对位（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/framework/graph/host_wiring.py": (
        "PlanInterpreterAdapter host wiring 装配函数族（build_registry/make_*_runner/legacy "
        "shim）；解释器装配单模块，闭包共享 host 上下文（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/framework/graph/lift/parsers.py": (
        "plan lift 缝 YAML/DTO parser 函数族（binding/io_schema/when/loop/predicate coerce）：lift "
        "解析语义共享，拆分只增跳转成本（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/framework/graph/plan_sdk.py": (
        "Plan SDK 类型化谓词/路由构造函数族（21 个无状态纯函数）；SDK 表面集中，拆分只增跳转成本（2026-10-05 Phase C batch-2 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/harness/declarative/compile/instrument/events.py": (
        "wrap_instrument spine 发射 helper "
        "族（_safe_append/_emit_via_pipeline/_publish_i17_rejection）：contained failure 发射语义共享，拆散割裂 "
        "I17 语义（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/harness/declarative/compile/instrument/wrap.py": (
        "wrap_instrument phase 图装配装饰器函数族（sync/async wrapper + @overload 签名 + "
        "wrap_executor）；instrument 面集中（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/harness/declarative/compile/subgraph_resolver.py": (
        "BundleSubgraphResolver bundle 相对子图解析器：10 个编译/嗅探 helper 共享 bundle 路径解析上下文（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/harness/plan.py": (
        "编译计划散列/来源/可解释性投影函数族（*_sub_plan_hash + to_dict + provenance）：canonical JSON "
        "投影语义共享，拆散割裂投影一致性（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/harness/plugin/declaration.py": (
        "插件声明 Cordis 载体适配器：归一化函数族共享 declaration 语义（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① "
        "仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/attachment/default/provider.py": (
        "ADR-0121 PR-B Default FileRef provider：resolver/stager/renderer 三 seam 默认实现单文件；seam "
        "面集中（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/journal_extra/journal_trace/render.py": (
        "journal trace 纯终端渲染函数族（table/human 双视图）；无状态，拆分无收益（2026-10-05 Phase C batch-1 审计，ADR-0291 "
        "§5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/kernel/kernel.py": (
        "lca-ops kernel 子命令装配（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/kernel/supervisor.py": (
        "lca-ops kernel-supervisor 一次性进程管理命令族（start/stop/restart/_tail_log/_kill_orphans 共享 "
        "_render 输出面）（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/observation/debug_graph.py": (
        "lca-ops debug-graph 一次性诊断编排器：_load_events/_classify_node/build_debug_graph/render_human "
        "共享 spine 直读上下文（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/profile/declarative.py": (
        "declarative 计划编译/检查 Typer 命令族（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/profile/inspect.py": (
        "profile 诊断命令族（inspect-tree/dump-profile/why/why-plugin/graph/debug 共享 pipeline bundle "
        "视图）（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/runs/debug.py": (
        "lca-ops runs debug 一次性诊断编排器：_layer_* 投影函数族共享 spine 折叠上下文（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/runs/driver_debug.py": (
        "driver 级诊断命令族（cmd_debug_* 共享 kernel stderr 解析上下文）；继续膨胀时按命令拆子模块（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/commands/runs/runs.py": (
        "lca-ops runs CLI 命令装配（含 --facade in-process 分发）；命令入口集中（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/services/kernel/restart_report.py": (
        "kernel 重启后三阶段健康检查编排单模块（boot_check/fiber_report/health_probe）（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cli/services/kernel/supervisor/supervisor.py": (
        "KernelSupervisor 进程 supervisor 单类（start/stop/restart + waiter/readiness/decider "
        "三线程循环）（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/computer/companion/client.py": (
        "ADR-0246 M3 CompanionClient 单类（GatewayClient 协议执行面）（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/computer/companion/standalone.py": (
        "ADR-0246 M3 用户机 side-effect 平面单入口（main + CompanionClient）；部署单元内聚（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/computer/machine/machine.py": (
        "MachineComputer sidecar/SSH transport 单类（File/shell/search/code）；computer "
        "边界内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/computer/runtime/exec.py": (
        "ComputerRuntime execution plane "
        "mixin（execute_code/run_command/background/export）；执行面内聚，mixin 拆散无收益（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/cron/scheduler.py": (
        "ADR-0268 §7/§8 tick 调度器（CronScheduler + CronTickReport）：文件锁互斥与 tick 摘要内聚，调度器单模块拆散割裂 P3 "
        "调度语义（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/integrations/composio/service/service.py": (
        "Composio 集成服务单类（composio.* spine 事件 SSOT 边界）；集成服务边界内聚（2026-10-05 Phase C batch-3 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/memory/assistant_memory.py": (
        "ADR-0242 D5 per-assistant MemorySystem 单类实现（读写 {home}/memory/，键按助理隔离）（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/memory/contextfiles/domain/layout.py": (
        "context-file layout TOML 解析函数族（read/merge/packaged/layout_for_home + "
        "_table/_from_mapping 等）；layout 解析语义单模块内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① "
        "仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/memory/contextfiles/domain/standing.py": (
        "standing 文件装配/重注函数族（split/pack/render/assemble/rehydrate/refresh）：section "
        "装配语义共享，压缩后重注内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/memory/dream.py": (
        "ADR-0249 Dream 语义记忆巩固单模块（run_dream + _trail/_write_synthesis 编排）；consolidation "
        "一次执行语义内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/activity_feed.py": (
        "ActivityFeed 纯 fold 读投影：_fold_journal/_fold_spine 等 fold 函数族共享 run ledger 折叠上下文，拆散割裂 "
        "fold 不变量（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/adapters/adapters.py": (
        "TelemetryLLMAdapter 装饰单类：Session EP emit 唯一职责（无 legacy journal 写回）（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/meta_event_emit.py": (
        "meta-event 双通道发射函数族（20 个 emit_* 无状态函数共享 Session catalog + spine 发射面）；拆分无收益（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/running_operation_store.py": (
        "RunningOperationStore 双后端（SQLite dev + Postgres LobeHub）+ resolve 函数；store "
        "选择面集中（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/spine/sinks/file_sink.py": (
        "FileSink append-only JSONL sink 契约实现单类 + offload/序列化 helper；sink 边界内聚（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/observability/stream/trace_inspector.py": (
        "面向 Coding Agent 的运行账本检查器（TraceInspector + TraceReport）：诊断单职责单模块（2026-10-05 Phase C "
        "batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/openai/compat.py": (
        "上游 OpenAI Responses/chat 兼容适配函数族（normalize_*/create_*/resolve_*，8 函数）；兼容缝单模块，LobeHub "
        "对接的映射语义集中（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/persistence/user_store.py": (
        "ADR-0252 D2/D3 UserAssistantStore 双实现（SQLite/Postgres）同文件对照（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/preset/fs_repository.py": (
        "FileSystemPresetRepository PresetRepositoryProtocol 文件系统实现单类；repository 边界内聚（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/proactive/scheduler.py": (
        "ADR-0263 §9 主动消息 tick 调度器（ProactiveScheduler）：文件锁互斥单类，与 cron 调度器同构的调度语义内聚（2026-10-05 "
        "Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/sandbox/local/adapter.py": (
        "host-backed LocalSandboxAdapter 单类（阻塞式文件 I/O + 子进程 exec）；SANDBOX plane "
        "单执行实现，部署单元内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/sandbox/onlyboxes/adapter.py": (
        "OnlyboxesSandboxAdapter HTTP client 单类（terminalExec 统一通道）；adapter 边界内聚（2026-10-05 Phase "
        "C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/session/emit/lifecycle_emit.py": (
        "Session lifecycle 事件发射函数族（turn/step/model/session.created/checkpoint 等 v1 事件）；DSH ↔ LCA "
        "spec §5 对齐的发射词表，拆散割裂生命周期语义（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tool_defer/session.py": (
        "ToolDeferSession per-run defer 会话状态单类 + ambient publish/reset；run-scoped "
        "状态拆散无收益（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/assistant/create_tool.py": (
        "ADR-0187 §3 D12 create_assistant 工具类 + 10 个 SOUL/home 解析 helper；对话创建助理执行面内聚（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/assistant/memory_tools.py": (
        "ADR-0246 PR-6 受治理记忆工具族（8 工具类 + 基类）单文件注册（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① "
        "仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/assistant/self_manage_tools.py": (
        "ADR-0242 D6 助理自管理工具族（14 工具类 + 基类）单文件注册；拆成 14 文件只增跳转成本（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/box/tool.py": (
        "ADR-0248 §3.2 “我的电脑” box 工具族（4 工具类 + build_box_tools）单文件注册；拆成 4 文件只增跳转成本（2026-10-05 "
        "Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/composio/__init__.py": (
        "Composio LLM 工具族注册包入口（ComposioManagementExecutor/ComposioActionExecutor + "
        "build_tools）；工具族注册集中（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/infrastructure/tools/contract/sandbox/contracts.py": (
        "ADR-0102 per-tool RenderContract 注册表单文件（各工具 FieldSpec 元组集中声明）；per-tool "
        "契约词表拆散会重蹈“通用契约丢字段”覆辙（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/loop/commit/tool_journal.py": (
        "ADR-0194 tool journal catalog commit 缝：commit_* 函数族经 FactGateway 单一提交（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/loop/fact_gateway.py": (
        "ADR-0194 §3.1 G0 单一事实生产门面（DefaultFactGateway）：append/catalog/enrich 函数族经 Session "
        "收口，门面拆散割裂唯一生产语义（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/nodes/concept/tool_fork/dispatch.py": (
        "phase.concept.tool.fork.dispatch 节点：ToolForkDispatchExecutor + typed BindingsView 拉取/过滤 "
        "helper 内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/nodes/reflect/memory_extract/memory_extract.py": (
        "phase.reflect.memory.extract 原语节点：ReflectMemoryExtractExecutor + LLM 解析/格式化 helper "
        "内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/nodes/think/context/summarize.py": (
        "ADR-0283 think.context.summarize 图节点（Executor + summarize/build/render 纯逻辑 + setup "
        "注册）；节点实现单文件，纯逻辑与节点薄包装同在便于对位（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/nodes/think/history/assemble.py": (
        "think.history.assemble 图节点：HistoryDeriveExecutor + _forked_to_tools 等 13 个组装 helper 共享 "
        "prompt 组装上下文（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/events/_events.py": (
        "ADR-0187 §3 D8 助理域 EP payload 词表（9 payload 类 + 四件套字段守门）；事件发射契约集中，拆散破坏 D8 "
        "单一事实源（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/evolve/evolve.py": (
        "ADR-0187 §3 D9 assistant.evolve 插件实现单类 + 错误词表（fail-closed 语义集中）（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/home/_home_layout.py": (
        "ADR-0187 §3 D2 AssistantHome 目录布局 + manifest schema + digest 校验内聚（6 错误类 + 20 "
        "布局函数）；布局/digest/校验跨文件拆分得不偿失（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/jobs/jobs.py": (
        "ADR-0187 §3 D10 assistant.jobs plugin boot + 内部实现单文件；plugin setup 注入 "
        "catalog，拆分只增跳转成本（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/skill/overlay/overlay.py": (
        "assistant.skill_overlay 实现单类（plugin setup 注入 catalog/emitter）（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/assistant/tool/overlay.py": (
        "ADR-0243 D4 assistant.tool_overlay plugin boot + 内部实现单文件；plugin setup 注入 "
        "catalog/emitter（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/avatar/events.py": (
        "ADR-0269 §6 Avatar WS 推送通道（AvatarEventPublisher + 鉴权/握手/转发 helper 族）；WS "
        "协议单实现，_auth/*_failed 与 gateway WS 同型内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① "
        "仲裁；Phase D 点亮）"
    ),
    "lca/plugins/avatar/routes.py": (
        "Avatar REST 路由端点族（ADR-0269 §5/spec §9）：_auth_prelude/_ownership 鉴权前置共享，21 个 handler "
        "拆分无收益（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/avatar/service.py": (
        "ADR-0269 §4/spec §7 Avatar 领域服务与状态机（AvatarService + Store/Provider/Publisher "
        "协议）；领域服务边界内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/avatar/store.py": (
        "ADR-0269 §2 AvatarStore 文件存储单类（修订号/原子写 PNG/路径白名单）；存储语义内聚（2026-10-05 Phase C batch-3 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/avatar/tools.py": (
        "ADR-0269 §4 avatar 工具族（6 工具类：create/edit/set/get/clear/schedule）单文件注册（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/domain/assistant/catalog/handlers.py": (
        "Assistant Catalog 内部实现单类（Home CRUD + manifest digest 守门）；helper 经 plugin setup 共享 "
        "ctx，跨文件传参得不偿失（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/events/hooks/model_visible/adapter.py": (
        "LLM adapter decorator（ModelVisibleHookAdapter）接线单模块：_snapshot/_kwargs/_emit_* helper "
        "族围绕单次 LLM 调用边界内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/events/hooks/model_visible/hook.py": (
        "ADR-0185 §3.2 ModelVisibleHook LLM 边界 model-visible 拦截钩子；hook 实现单文件（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/loop/reducer/plugin.py": (
        "ADR-0066 boot-time 默认 Reducer 单实现（DefaultReducer，C4 单一写）（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/observability/spine/classifiers/exception_builtin.py": (
        "ExceptionBuiltinClassifier Layer-A 已知异常分类器单类 + plugin setup；classifier 实现单文件（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/observability/spine/derivers/anomaly.py": (
        "AnomalyDetector spine deriver（8 不变量违例检测器）；deriver 实现单文件（2026-10-05 Phase C batch-2 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/observability/spine/runtime_hooks.py": (
        "spine 事件发射 pipeline 钩子函数族（ctx_effect/ctx_intercept 双 wrap 种经 "
        "emit_pipeline）；发射缝单文件（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/session/derivers/step_tree/journal_fold.py": (
        "ADR-0186 PR-3g 纯 fold 单入口：事件流 fold 出 JournalDocument；_Frame 累积器内聚，拆散割裂 fold "
        "不变量（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/session/projection_cache/projection_cache.py": (
        "ProjectionCache DSH session-projection-cache LCA 形态：per-session 检查点缓存 + flush listener + "
        "observer 适配器内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/session/projection_registry/projection_registry.py": (
        "ProjectionRegistry DSH session-projection 一比一 LCA 实现：注册表 + _Cell 水位 + observer "
        "适配器内聚，fold 状态机拆散割裂不变量（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/session/telemetry_otel/telemetry_otel.py": (
        "OtelTelemetryBackend DSH session-telemetry-otel 一比一实现：有界队列 + daemon 批量导出 + "
        "_NoOpExporter；后端边界内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/session/title_service/title_service.py": (
        "ADR-0188 SessionTitleService：fold 读取 + Session.append 写回内聚（DSH 一比一对位）（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/tools/diagnostics/debug/run.py": (
        "ADR-0122 lca-ops debug run 8-section 诊断：DebugRunReport 单类 + 提取函数族（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/device_hub/routes/routes_http.py": (
        "设备通道 HTTP handler 注册表单文件（14 个 /api/device/* 端点）；协议面集中（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/carrier/runs/execute/execution_environment.py": (
        "RunExecutionEnvironment legacy run carrier scope 组装单模块；scope 顺序显式集中（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/carrier/runs/lifecycle/runnable_assembly.py": (
        "run 输入物化与 adapter resolver 装配单模块（CognitiveRunnableAssembler + LlmResolver + "
        "tools_from_scope）：assembler 装配语义内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D "
        "点亮）"
    ),
    "lca/plugins/transport/webserver/doctor/steps/hops.py": (
        "doctor.v3 hop 判定函数族（H1..H8/seg/phase/xref/ssot/mv-journal/fold）（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/doctor/steps/scan.py": (
        "doctor.v3 数据面 StepScan 事实收集函数族（_scan_* 共享 journal/spine/fold 上下文）；ADR-0185 "
        "PR-3.1（2026-10-05 Phase C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py": (
        "ADR-0163 run carrier 命令端点族：decode/validate/render 内聚，端点增删单文件可见（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py": (
        "run carrier 查询端点族（GET /runs/* 投影）；与 command_endpoints 对称，端点增删单文件可见（2026-10-05 Phase C "
        "batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py": (
        "RunSessionBuilder legacy RunSession 组装器：身份分配 + carrier 归一化 + fold deriver "
        "装配内聚（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/session/session/session.py": (
        "Legacy run-session aggregate（RunSession）+ RunRegistry "
        "兼容门面共生单模块；聚合与门面天然一体，拆散得不偿失（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py": (
        "RegistryRunCommands 单类：legacy run 的 create/cancel/approval-resume 变异内聚（2026-10-05 Phase "
        "C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py": (
        "LcaAgentGateway WebSocket 单协议实现：recv/心跳/控制帧/中断内聚（2026-10-05 Phase C batch-1 审计，ADR-0291 "
        "§5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/read/runs/terminal.py": (
        "terminal run manifest 物化函数族（watermark/ledger 高水位扫描共享 SSOT 直读上下文）；一次性诊断编排器（2026-10-05 "
        "Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_1/routes_assistants/codecs.py": (
        "assistants 路由共享 JSON 整形函数族（error envelope/COMPAT/鉴权探针 17 个）；跨路由共享面集中（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_1/routes_assistants/jobs.py": (
        "ADR-0268 P4 /v1/assistants jobs 端点族（cron.list/add 投影）（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_1/routes_assistants/profile.py": (
        "/v1/assistants profile 端点族（CRUD 映射）；ADR-0252 D6 归属隔离（2026-10-05 Phase C batch-1 "
        "审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py": (
        "standing-files 端点族（list/get/update + dispatcher 共享 _prelude "
        "鉴权前置）；协议面集中，端点增删单文件可见（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_1/routes_onboarding.py": (
        "onboarding 端点族（presets/welcome/naming_settle，ADR-0252 D7）；协议面集中（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/plugins/transport/webserver/routes_3/routes_rooms.py": (
        "/v1/rooms 群聊房间 REST 端点族（Room Runtime Go-Live M1）；RoomDispatcher "
        "接线共享，端点增删单文件可见（2026-10-05 Phase C batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/runtime/session/run_session_writer.py": (
        "ADR-0226 §1 RunSessionWriter：run-scoped Session 单一 surface append 路径拥有者（2026-10-05 Phase "
        "C batch-1 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/runtime/support/runtime_bindings.py": (
        "DeclarativeRuntimeBindings 声明式 Turn 依赖闭包契约（2 frozen 类）；绑定闭包拆散无收益（2026-10-05 Phase C "
        "batch-2 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/session/lifecycle/repair.py": (
        "崩溃恢复 repair 函数族（DSH interruptedTurnClosers）：repair_interrupted_turn + _coerce/_extract_* "
        "围绕开尾 turn 闭合语义内聚（2026-10-05 Phase C batch-3 审计，ADR-0291 §5① 仲裁；Phase D 点亮）"
    ),
    "lca/cognition/memory/scoring.py": (
        "ADR-0277 Phase 3 检索评分 SSOT：MemoryScorer/WeightedScorer/HybridScorer + Laya/Shadow "
        "评分器族共享评分公式上下文；评分器拆散割裂评分不变量（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/contracts/event.py": (
        "ADR-0180 事件层 v2 协议骨架：Category/Plane 闭集 + EventPayload 基类 + "
        "团队委派事件；协议词表单文件，拆散破坏协议单一事实源（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/infrastructure/observability/events/event/doc/doc.py": (
        "todo-57 数据表化后形态：_DOC_TABLE 53 事件词条数据表 + 注册装饰器/查询函数；词条增删改数据即可，属词表单文件（2026-10-05 "
        "iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/infrastructure/session/emit/cognitive_emit/reflection_events.py": (
        "ADR-0194 P1-15/ADR-0220 §6.2 brain-internal spine EP "
        "发射器族（critic/synthesize/skill_router/prompt_assembler/reasoner）；单生产缝，发射器拆散割裂发射面（2026-10-05 "
        "iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/nodes/concept/effect/execute.py": (
        "phase.concept.effect_execute 图唯一节点：EffectExecuteExecutor typed effect 分发 + _dispatch + "
        "tool result 归因 helper 族共享分发上下文（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/plugins/session/telemetry_capture/telemetry_capture.py": (
        "DSH SessionTelemetryCoordinator 一比一 LCA 实现：SessionTelemetryCapture 单类 + "
        "attach/observe/cursor helper；后端边界内聚（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 "
        "§5① 仲裁）"
    ),
    "lca/plugins/strategies/graph/graph.py": (
        "GraphStrategy DAG 工作流引擎（resolved-counter 模型）+ GraphExecutionState + "
        "factory/setup；策略引擎单文件内聚（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py": (
        "RunLifecycleCoordinator：单 run 执行/暂停/恢复/终态编排单类；run 生命周期状态机拆散割裂不变量（2026-10-05 iter-tests "
        "20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/plugins/transport/webserver/routes_channels_wechat.py": (
        "WeChat channel 管理鉴权端点族（bind/unbind/qrcode/status/config + "
        "网关分发）；通道协议面集中，端点增删单文件可见（2026-10-05 iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/session/append.py": (
        "ADR-0195 P1-03 Session append 公共 API：Session 类 + "
        "_to_jsonable/_validate_json_safe/_snapshot_data 快照 helper 族；append 面内聚（2026-10-05 "
        "iter-tests 20:09 Phase D 收尾审计，ADR-0291 §5① 仲裁）"
    ),
    "lca/nodes/intervene/approve_gate.py": (
        "ADR-0292 §10 grant-absence 拒绝门：node_execute 4 路 HITL 路由 + "
        "_grant_absence_refusal 特权判定 + evidence 路由三件套单类内聚；拒绝/路由拆分"
        "割裂拒绝不变量（2026-10-06 iter-tests 02:09 Phase D 补登记，ADR-0291 §5① 仲裁）"
    ),
    "lca/domain/cron/store.py": (
        "cron job/run 文件存储：job 增删查 + run 追加/查询 + CronWorkerResult "
        "outcome/receipts 落盘（ADR-0268 §6）；store API 面内聚（2026-10-06 iter-tests "
        "02:09 Phase D 补登记，ADR-0291 §5① 仲裁）"
    ),
    "lca/contracts/protocols/assistant/skill_overlay.py": (
        "AssistantSkillOverlay Protocol 与其 5 dataclass / 2 errors 同属单一内聚定义单元，硬拆反内聚"
        "（ADR-0295，2026-10-09 iter-quality 03:09 登记临时豁免）"
    ),
    "lca/infrastructure/cli/commands/ops/assistants.py": (
        "typer 命令聚合点（soul + skill/relink 系），与 runs/tools.py 豁免同构"
        "（ADR-0295，2026-10-09 iter-quality 03:09 登记临时豁免）"
    ),
}


def _collect_all_concrete_classes(
    scan_packages: list[str] | None = None,
) -> dict[str, type]:
    """扫描指定模块，收集其中定义的具体类（含 Protocol 和具体实现）。"""
    result: dict[str, type] = {}
    packages = scan_packages if scan_packages is not None else _SCAN_PACKAGES
    for pkg_name in packages:
        pkg = importlib.import_module(pkg_name)
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            pkg.__path__,
            prefix=pkg.__name__ + ".",
        ):
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
                if not cls.__module__.startswith(pkg_name):
                    continue
                result[cls_name] = cls
    return result


def _read_glossary_terms() -> set[str]:
    """从 docs/specs/glossary.md 提取所有术语词条（表格第一列的 **bold** 部分）。"""
    if not _GLOSSARY_PATH.exists():
        return set()
    terms: set[str] = set()
    for line in _GLOSSARY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("|") and "**" in line:
            match = re.search(r"\*\*([^*]+)\*\*", line)
            if match:
                terms.add(match.group(1).strip())
    return terms


# 反向校验的扫描范围：术语表覆盖 contracts 与 L0-L4 全部层的类名。
# ADR-0291 Phase A：去掉已不存在的 lca.plugins.loop.phase，
# 换为现行 lca.plugins.loop 下的 control/driver/graph/reducer 四包。
# ADR-0291 Phase D 前置动作①（2026-10-05 tests lane）：纳入 lca.plugins.strategies
# （7 策略类 DebateStrategy…SwarmStrategy）与 lca.plugins.tools.diagnostics
# （3 诊断工具类 FailureExplainer/MinimalReproduction/OptimizationFinder）——
# 三类均实证真实存在，先前因扫描范围外致 reverse 设计意图红，勿当 deleted 清理。
_REVERSE_SCAN_PACKAGES = (
    "lca.contracts",
    "lca.infrastructure",
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
    "lca.plugins.loop.control",
    "lca.plugins.loop.driver",
    "lca.plugins.loop.graph",
    "lca.plugins.loop.reducer",
    "lca.plugins.strategies",
    "lca.plugins.tools.diagnostics",
    # 机制层术语（EnvelopeBus / SessionEvent / EnvelopeRef …）定义在 lca_kernel，
    # 不在 lca 下；glossary 现役区收录它们，反向扫描必须覆盖其真实归属包。
    "lca_kernel",
)
_CAMEL_CASE_TERM = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_DEPRECATED_SECTION_MARKERS = ("已废弃主名", "禁止复活")


def _collect_class_names(scan_packages: tuple[str, ...]) -> set[str]:
    """收集指定包内定义的类名，以及模块级 union 类型别名（如 Coordination）。"""
    names: set[str] = set()
    for pkg_name in scan_packages:
        pkg = importlib.import_module(pkg_name)
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            pkg.__path__,
            prefix=pkg.__name__ + ".",
        ):
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
                if cls.__module__.startswith(pkg_name):
                    names.add(cls_name)
            for name, value in vars(mod).items():
                if type(value) is types.UnionType and _CAMEL_CASE_TERM.match(name):
                    names.add(name)
    return names


def _read_active_glossary_terms() -> set[str]:
    """提取现役区（「已废弃主名」章节之前）表格行中的全部 **bold** 术语。"""
    if not _GLOSSARY_PATH.exists():
        return set()
    terms: set[str] = set()
    for line in _GLOSSARY_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and any(
            marker in stripped for marker in _DEPRECATED_SECTION_MARKERS
        ):
            break
        if stripped.startswith("|") and "**" in stripped:
            terms.update(m.strip() for m in re.findall(r"\*\*([^*]+)\*\*", stripped))
    return terms


class TestNoBannedClassNames(unittest.TestCase):
    """类名不得命中禁用词正则（Manager/Util/Helper/Handler/Processor/Advanced/Data$/Info$）。"""

    def test_no_banned_class_name_patterns(self) -> None:
        classes = _collect_all_concrete_classes()
        # C1 基数门：扫描基数异常（包导入失败/指针漂移）时直接红，不许恒绿。
        self.assertGreaterEqual(
            len(classes),
            _MIN_CLASS_SCAN_COUNT,
            f"类扫描基数 {len(classes)} < {_MIN_CLASS_SCAN_COUNT}：扫描可能空心",
        )
        offenders: list[str] = []
        for cls_name in sorted(classes):
            if cls_name in _NAME_EXEMPT:
                continue
            core_name = cls_name.removeprefix("Simple")
            if core_name in _NAME_EXEMPT:
                continue
            if _BANNED_CLASS_PATTERN.search(cls_name):
                offenders.append(
                    f"  - {cls_name}（如需豁免，请在 docs/design/naming-constitution.md 登记并在 "
                    f"_NAME_EXEMPT 中注明理由）"
                )
        self.assertFalse(
            offenders,
            "以下类名命中禁用词正则:\n" + "\n".join(offenders),
        )


class TestFileLineCountLimit(unittest.TestCase):
    """单文件不超过 250 行（不含空行和注释），已登记豁免除外。"""

    def test_file_line_count_limit(self) -> None:
        py_files = sorted(_LCA_ROOT.rglob("*.py"))
        # C1 基数门：rglob 在不存在目录上返回空迭代器（曾致本测试恒绿），直接红。
        self.assertGreaterEqual(
            len(py_files),
            _MIN_FILE_SCAN_COUNT,
            f"文件扫描基数 {len(py_files)} < {_MIN_FILE_SCAN_COUNT}：扫描可能空心",
        )
        offenders: list[str] = []
        for py_file in py_files:
            rel_path = str(py_file.relative_to(_PROJECT_ROOT))
            lines = py_file.read_text(encoding="utf-8").splitlines()
            code_lines = [
                line for line in lines if line.strip() and not line.strip().startswith("#")
            ]
            if len(code_lines) > _MAX_FILE_LINES:
                if rel_path in _LINE_COUNT_EXEMPT:
                    continue
                offenders.append(
                    f"  - {rel_path}: {len(code_lines)} 行有效代码（阈值 {_MAX_FILE_LINES}）"
                )
        self.assertFalse(
            offenders,
            "以下文件超过有效代码行数上限:\n"
            + "\n".join(offenders)
            + "\n如需临时豁免，请在 _LINE_COUNT_EXEMPT 中登记并引用 ADR。",
        )


# ADR-0291 Phase A：层 docstring 测试语义重写。
# 原 `layer*/__init__.py` glob 在 lca/ 下恒空（无 layer* 命名目录），
# 改为显式五层清单 —— contracts → infrastructure → cognition → runtime → agent，
# 与 test_architecture_conformance.py 的分层维度对齐。
_LAYER_PACKAGES = ("contracts", "infrastructure", "cognition", "runtime", "agent")


class TestLayerInitDocstrings(unittest.TestCase):
    """每个层的 __init__.py 必须有非空 docstring，且各层描述不重复。"""

    def test_layer_init_docstrings_non_empty(self) -> None:
        empty: list[str] = []
        descriptions: list[str] = []
        for layer in _LAYER_PACKAGES:
            init_file = _LCA_ROOT / layer / "__init__.py"
            rel = str(init_file.relative_to(_PROJECT_ROOT))
            # 清单漂移即红：包改名/删除时测试必须显式失败，而非静默跳过。
            self.assertTrue(
                init_file.is_file(),
                f"层清单漂移：{rel} 不存在（_LAYER_PACKAGES 须与 lca/ 实际布局同步）",
            )
            mod = importlib.import_module(f"lca.{layer}")
            doc = (mod.__doc__ or "").strip()
            if not doc:
                empty.append(f"  - {rel}")
            else:
                descriptions.append(doc)

        self.assertFalse(
            empty,
            "以下层的 __init__.py 缺少 docstring:\n" + "\n".join(empty),
        )

        if len(descriptions) != len(set(descriptions)):
            self.fail("存在重复的层职责描述——每层 docstring 应唯一表达该层的核心职责")


class TestGlossaryTermCoverage(unittest.TestCase):
    """源码中的核心类名应至少有一个词根能在 glossary.md 中找到匹配。"""

    def test_glossary_term_coverage(self) -> None:
        glossary_terms = _read_glossary_terms()
        # C1/C4：glossary 缺失不再 skip（曾致本测试恒 skip），直接红。
        self.assertTrue(
            glossary_terms,
            f"glossary 为空：{_GLOSSARY_PATH} 不存在或无词条（指针/文件漂移即红）",
        )

        glossary_text = " ".join(glossary_terms).lower()

        classes = _collect_all_concrete_classes(_GLOSSARY_COVERAGE_SCAN_PACKAGES)
        # C1 基数门：扫描基数异常时直接红，不许恒绿。
        self.assertGreaterEqual(
            len(classes),
            _MIN_CLASS_SCAN_COUNT,
            f"类扫描基数 {len(classes)} < {_MIN_CLASS_SCAN_COUNT}：扫描可能空心",
        )
        uncovered: set[str] = set()

        for cls_name in sorted(classes):
            if cls_name.startswith("_"):
                continue
            parts = re.findall(r"[A-Z][a-z]+", cls_name)
            if not parts:
                continue
            matched = any(
                part.lower() in glossary_text
                or any(part.lower() in term.lower() for term in glossary_terms)
                for part in parts
            )
            if not matched:
                uncovered.add(f"  - {cls_name} (词根: {parts})")

        uncovered_list = sorted(uncovered)
        if len(uncovered_list) > 10:
            self.fail(
                f"以下 {len(uncovered_list)} 个类的词根在 glossary.md 中无匹配"
                f"（仅展示前 10 个）:\n"
                + "\n".join(uncovered_list[:10])
                + "\n请在 docs/specs/glossary.md 中补充对应词条。"
            )


class TestGlossaryReverseCoverage(unittest.TestCase):
    """glossary.md 现役区的 CamelCase 术语必须对应 lca / lca_kernel 包内真实类名。

    与 TestGlossaryTermCoverage 互为反向：后者保证「代码类 → 术语表」，
    本测试保证「术语表 → 代码类」。缺失反向校验时，ADR-0030 删除的
    MultiAgentTeam / TeamProcess / OrchestrationFamily 等废弃名曾长期
    滞留在现役区误导读者。术语被改名/删除后必须移入「已废弃主名」表。
    """

    def test_active_glossary_terms_exist_in_code(self) -> None:
        terms = _read_active_glossary_terms()
        # C1/C4：glossary 缺失不再 skip（曾致本测试恒 skip），直接红。
        self.assertTrue(
            terms,
            f"现役术语为空：{_GLOSSARY_PATH} 不存在、无词条或「已废弃主名」章节位置漂移",
        )

        # ADR-0291 Phase D 前置动作②（2026-10-05 tests lane）：8 条目全部清账——
        # ① 5 个已删除术语（CandidateEvaluationPipeline/DecisionParser/
        #    DegradationPolicy/GracefulDegradation/SimpleDecisionParser）已由
        #    Phase B（arch lane）移入 docs/specs/glossary.md「已废弃主名」表
        #    （实证：glossary.md 366–371 行；现役区 88 行的 DecisionParser 非
        #    bold 行内提及，reverse 只抓 bold 术语，不受影响）；
        # ② 3 个（FailureExplainer/MinimalReproduction/OptimizationFinder）为
        #    真实存在的诊断工具类（lca.plugins.tools.diagnostics/*），先前因
        #    扫描范围外被误登记，随动作①纳入扫描后可直接命中。
        # 保留空集合作为历史记录位（后续 deleted terms 未进废弃表时可再登记）。
        known_deleted_terms: set[str] = set()

        class_names = _collect_class_names(_REVERSE_SCAN_PACKAGES)
        # C1 基数门：扫描基数异常时直接红，不许恒绿。
        self.assertGreaterEqual(
            len(class_names),
            _MIN_REVERSE_CLASS_SCAN_COUNT,
            f"reverse 类扫描基数 {len(class_names)} < {_MIN_REVERSE_CLASS_SCAN_COUNT}：扫描可能空心",
        )
        missing = sorted(
            term
            for term in terms
            if _CAMEL_CASE_TERM.match(term)
            and term not in class_names
            and term not in known_deleted_terms
        )
        self.assertFalse(
            missing,
            "以下现役术语在 lca / lca_kernel 包中不存在对应类名"
            "（已改名/删除的术语请移入「已废弃主名」表，"
            "概念性词语请勿加粗为术语词条）:\n" + "\n".join(f"  - {term}" for term in missing),
        )


if __name__ == "__main__":
    unittest.main()
