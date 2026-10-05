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
    """glossary.md 现役区的 CamelCase 术语必须对应 lca 包内真实类名。

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

        # Terms from deleted modules that haven't been moved to the deprecated section yet.
        # Phase B（arch lane）负责将其移入「已废弃主名」表后从此处删除。
        known_deleted_terms = {
            "CandidateEvaluationPipeline",
            "DecisionParser",
            "DegradationPolicy",
            "GracefulDegradation",
            "SimpleDecisionParser",
            "FailureExplainer",
            "MinimalReproduction",
            "OptimizationFinder",
        }

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
            "以下现役术语在 lca 包中不存在对应类名"
            "（已改名/删除的术语请移入「已废弃主名」表，"
            "概念性词语请勿加粗为术语词条）:\n" + "\n".join(f"  - {term}" for term in missing),
        )


if __name__ == "__main__":
    unittest.main()
