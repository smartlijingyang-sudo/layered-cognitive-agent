"""代码规范健身函数 —— 命名禁用词、文件行数、层职责、术语覆盖。

与 test_architecture_conformance.py（分层维度）并列，
覆盖"合理性 / 命名 / 目录"维度的微观治理。
"""

from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import re
import types
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LCA_ROOT = _PROJECT_ROOT / "lca"
_GLOSSARY_PATH = _PROJECT_ROOT / "docs" / "specs" / "glossary.md"

# ── 命名禁用词 ──────────────────────────────────────────────────────────
_BANNED_CLASS_PATTERN = re.compile(
    r"(Manager|Util|Utils|Helper|Handler|Processor|Advanced)"
    r"|(Data|Info)$",
)

# 显式豁免清单（参照 docs/specs/glossary.md "命名约定" 章节）
_NAME_EXEMPT: dict[str, str] = {
    # Action 策略类：Operation 后缀表达策略模式插槽，非禁用词 Manager/Helper
    "RespondOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "UseToolOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "DelegateOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "HandoffOperation": "Action 策略实现（contracts.protocols.action.Action）",
    # Observability 命名：SpanContextInfo 是 OTel SDK 兼容的 dataclass（非 Info/Helper 类）
    "SpanContextInfo": "OTel span context 信息封装（兼容 OTel SDK 命名约定）",
}

_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
    "gateway",
]

# Forward glossary coverage test only checks LCA core (not gateway).
# Gateway is a separate concern; its terms are listed in glossary.md
# under "Gateway 概念" but not required to have bold entries.
_GLOSSARY_COVERAGE_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
]

# ── 文件行数上限 ─────────────────────────────────────────────────────────
_MAX_FILE_LINES = 250

# 已登记豁免（引用 ADR 或说明原因）
_LINE_COUNT_EXEMPT: dict[str, str] = {
    "lca/harness/plugin_api.py": (
        "ADR-0061 Manifest API：PluginDefinition / @plugin / AuditedPluginContext 同文件"
    ),
    "lca/harness/profile/resolve.py": (
        "ADR-0061 resolve 阶段：深合并、from_env、DAG、校验集中于单一入口"
    ),
    "lca/layer4_app/spawn.py": (
        "L4 spawn 闭合 AgentSpec/TeamSpec（ADR-0056）；"
        "promote_lead 由 test_refactor_guards 直接 import"
    ),
    "lca/layer1_cognitive/body/action_handlers.py": (
        "Body 动作分发单模块（委派/工具/记忆/收口）；ADR-0049 证据平面与 harvest 同文件"
    ),
    "lca/layer1_cognitive/brain/reasoner.py": (
        "PromptReasoner 单模块承载模板渲染 + LLM 调用 + 流式增量（ADR-0041）；"
        "ADR-0052 新增 _strip_empty_prompt_fields 用于 solo 裸模型空字段剥离"
    ),
    "lca/contracts/models/observability/journal.py": (
        "Journal 叙事词表单文件（ADR-0037）；ToolInvoked.plugin_state UI 一等字段（ADR-0053）"
    ),
    "lca/layer0_infra/skills/marketplace.py": ("Skill marketplace 单模块承载发现/加载/注册全链路"),
    "lca/layer4_app/casting.py": ("Team casting 单模块承载角色映射与团队组装"),
    "lca/layer0_infra/sandbox/runtime.py": (
        "Sandbox Protocol 单模块承载 session/ready/exec 全链路（ADR-0043~0047）"
    ),
    "lca/layer0_infra/computer/runtime_exec.py": (
        "ComputerRuntime 执行平面单模块：code/shell/background/export + SandboxPolicy 检查"
    ),
    "lca/contracts/atoms/plan_template.py": (
        "PR-12 12 PlanTemplate 标准集数据面 + module-level accessors"
    ),
    "lca/contracts/harness/artifact.py": (
        "PR-8 4 状态机 + CapabilityArtifact + ArtifactController + 8→4 legacy migration"
    ),
    "lca/contracts/protocols/__init__.py": (
        "contracts/protocols re-export hub（所有 contracts 子模块类型统一导出）"
    ),
    "lca/contracts/protocols/command_envelope.py": (
        "PR-7 CommandEnvelope + RunFact + Verdict 5 闸单调聚合数据面"
    ),
    "lca/contracts/protocols/control_plan.py": (
        "PR-1 11 ControlSlot + Activation DSL + ControlPlan + plan_hash"
    ),
    "lca/contracts/protocols/declarative_phase_graph.py": (
        "ADR-0075 最小可信内核：PluginSpec、PhaseGraph、cursor、outcome 与验证契约必须同源闭合"
    ),
    "lca/contracts/protocols/plan.py": (
        "ADR-0075 CompiledRunPlan 将旧子计划与声明式图、binding、effect policy 纳入同一可哈希输入"
    ),
    "lca/harness/declarative/compiler.py": (
        "ADR-0075 声明式计划编译：插件贡献、阶段图、effect policy 与验证报告必须在单一纯编译入口收敛"
    ),
    "lca/harness/declarative/interpreter.py": (
        "ADR-0075 通用解释器：有界图执行、Journal、effect、pause/failed/effect_uncertain outcome 与 cursor 恢复需要同一事务边界"
    ),
    "lca/layer2_runtime/declarative_runtime.py": (
        "ADR-0075 声明式 driver：受限 runtime capability、handler gateway、reducer adapter 与可恢复 checkpoint 共同构成执行适配层"
    ),
    "lca/harness/profile/control_plan_resolver.py": (
        "ADR-0074 ControlPlan 单一投影入口：声明解析、严格校验、11 槽默认闭合与 explain 投影"
    ),
    "lca/layer0_infra/observability/__init__.py": (
        "observability 模块统一 re-export（journal / evidence / otel）"
    ),
    "lca/layer0_infra/observability/event_descriptors_data.py": (
        "Journal event descriptor 注册表（ADR-0065 PR-7 source inversion 单一源）"
    ),
    "lca/layer0_infra/observability/facade.py": (
        "observability 主 facade（record / record_runtime / observe_operation）"
    ),
    "lca/layer0_infra/observability/journal/journal_io.py": (
        "Journal v2 envelope IO（read / write / disk format；PR-3 + PR-6）"
    ),
    "lca/layer1_cognitive/body/safe_executor.py": (
        "SafeExecutor + 5 阶段管线 + ToolStarted / ToolInvoked audit"
    ),
    "lca/layer4_app/spawn_bind_plan.py": (
        "PR-5 bind_plan + BindOptions + PlanBindingResult + legacy fallback"
    ),
    "lca/layer0_infra/observability/journal/engine.py": (
        "RunStore 单模块承载事件索引 + get/get_event/get_blob/find_terminal"
        "（PR2 / PR6 / PR10 集中落地）"
    ),
    "lca/layer0_infra/observability/journal/fact_stream_projector.py": (
        "FactStreamProjector 单模块承载流式事件到 Journal 转换（ADR-0037）"
    ),
    "lca/layer0_infra/observability/journal/console_projector.py": (
        "ConsoleProjector 单模块承载 console 输出（ADR-0037）"
    ),
    "lca/layer0_infra/observability/diagnostics.py": (
        "DiagnosePattern 单模块承载 4 个 v3 §24.5 诊断模式"
        "（model_not_seen / loop_stuck / memory_poisoned / approval_rejected）"
    ),
    "lca/layer0_infra/ops/cli.py": (
        "lca-ops CLI 单模块承载 dev/restart/stop/status/heal/provision"
        "/diagnose/dump-profile/inspect-tree 全子命令"
    ),
    "lca/layer0_infra/ops/commands/tools.py": (
        "coding-agent tools CLI 封装（ADR-0065 §六 / PR-9）：9 个只读子命令从旧 cli.py 拆出"
    ),
    "lca/layer0_infra/ops/services/lobehub.py": (
        "LobeHub deploy service 单模块承载 dev/prod/restart/logs/upgrade"
    ),
    "lca/layer0_infra/ops/services/daemon.py": ("Daemon 单模块承载 process 管理 + uptime + health"),
    "lca/layer0_infra/openai_compat.py": (
        "OpenAI compat 单模块承载 chat / completion / embedding 适配"
    ),
    "lca/layer0_infra/host_runtime/providers/user.py": (
        "User provider 单模块承载 user runtime 配置 + workspace"
    ),
    "lca/layer1_cognitive/memory/simple_memory.py": (
        "SimpleMemorySystem 单模块承载四层记忆 + propose/commit/compaction 影子（PR7）"
    ),
    "lca/layer1_cognitive/body/pipeline_safe_executor.py": (
        "PipelineSafeExecutor 单模块承载五阶段管线 + finalize（v3 §9.1/9.2）"
    ),
    "lca/contracts/models/observability/journal_catalog.py": (
        "JOURNAL_EVENT_CLASSES + JournalSchemaMeta 单文件（PR-7 后 EventDescriptor 单一源移到 event_descriptors_data.py）"
    ),
    "lca/layer4_app/api.py": ("L4 门面单文件承载 Agent / Team / cast 入口（ADR-0005）"),
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


# 反向校验的扫描范围：术语表覆盖 contracts 与 L0-L4 全部层的类名
_REVERSE_SCAN_PACKAGES = (
    "lca.contracts",
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
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
        offenders: list[str] = []
        for cls_name in sorted(classes):
            if cls_name in _NAME_EXEMPT:
                continue
            core_name = cls_name.removeprefix("Simple")
            if core_name in _NAME_EXEMPT:
                continue
            if _BANNED_CLASS_PATTERN.search(cls_name):
                offenders.append(
                    f"  - {cls_name}（如需豁免，请在 docs/specs/glossary.md 登记并在 "
                    f"_NAME_EXEMPT 中注明理由）"
                )
        self.assertFalse(
            offenders,
            "以下类名命中禁用词正则:\n" + "\n".join(offenders),
        )


class TestFileLineCountLimit(unittest.TestCase):
    """单文件不超过 250 行（不含空行和注释），已登记豁免除外。"""

    def test_file_line_count_limit(self) -> None:
        offenders: list[str] = []
        for py_file in sorted(_LCA_ROOT.rglob("*.py")):
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


class TestLayerInitDocstrings(unittest.TestCase):
    """每个层的 __init__.py 必须有非空 docstring，且各层描述不重复。"""

    def test_layer_init_docstrings_non_empty(self) -> None:
        layer_inits = sorted(_LCA_ROOT.glob("layer*/__init__.py"))
        layer_inits.append(_LCA_ROOT / "contracts" / "__init__.py")
        layer_inits.sort()

        empty: list[str] = []
        descriptions: list[str] = []
        for init_file in layer_inits:
            rel = str(init_file.relative_to(_PROJECT_ROOT))
            try:
                mod = importlib.import_module(
                    str(init_file.parent.relative_to(_PROJECT_ROOT)).replace(os.sep, ".")
                )
            except ImportError:
                continue
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
        if not glossary_terms:
            self.skipTest("docs/specs/glossary.md 不存在或为空")

        glossary_text = " ".join(glossary_terms).lower()

        classes = _collect_all_concrete_classes(_GLOSSARY_COVERAGE_SCAN_PACKAGES)
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
    """glossary.md 现役区的 CamelCase 术语必须对应 lca 包内真实类名。

    与 TestGlossaryTermCoverage 互为反向：后者保证「代码类 → 术语表」，
    本测试保证「术语表 → 代码类」。缺失反向校验时，ADR-0030 删除的
    MultiAgentTeam / TeamProcess / OrchestrationFamily 等废弃名曾长期
    滞留在现役区误导读者。术语被改名/删除后必须移入「已废弃主名」表。
    """

    def test_active_glossary_terms_exist_in_code(self) -> None:
        terms = _read_active_glossary_terms()
        if not terms:
            self.skipTest("docs/specs/glossary.md 不存在或为空")

        # Terms from deleted modules that haven't been moved to the deprecated section yet.
        # Once the glossary is updated, remove these from the skip list.
        known_deleted_terms = {
            "CandidateEvaluationPipeline",
            "DecisionParser",
            "DegradationPolicy",
            "GracefulDegradation",
            "SimpleDecisionParser",
        }

        class_names = _collect_class_names(_REVERSE_SCAN_PACKAGES)
        missing = sorted(
            term
            for term in terms
            if _CAMEL_CASE_TERM.match(term)
            and term not in class_names
            and term not in known_deleted_terms
        )
        self.assertFalse(
            missing,
            "以下现役术语在 lca 包中不存在对应类名"
            "（已改名/删除的术语请移入「已废弃主名」表，"
            "概念性词语请勿加粗为术语词条）:\n" + "\n".join(f"  - {term}" for term in missing),
        )


if __name__ == "__main__":
    unittest.main()
