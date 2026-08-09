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
_GLOSSARY_PATH = _PROJECT_ROOT / "docs" / "glossary.md"

# ── 命名禁用词 ──────────────────────────────────────────────────────────
_BANNED_CLASS_PATTERN = re.compile(
    r"(Manager|Util|Utils|Helper|Handler|Processor|Advanced)"
    r"|(Data|Info)$",
)

# 显式豁免清单（参照 docs/glossary.md "命名约定" 章节）
_NAME_EXEMPT: dict[str, str] = {
    # Action 策略类：Operation 后缀表达策略模式插槽，非禁用词 Manager/Helper
    "RespondOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "UseToolOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "DelegateOperation": "Action 策略实现（contracts.protocols.action.Action）",
    "HandoffOperation": "Action 策略实现（contracts.protocols.action.Action）",
}

_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
    "gateway",
]

# ── 文件行数上限 ─────────────────────────────────────────────────────────
_MAX_FILE_LINES = 250

# 已登记豁免（引用 ADR 或说明原因）
_LINE_COUNT_EXEMPT: dict[str, str] = {
    "lca/layer4_app/composer.py": (
        "组合根单文件承载 AgentComposer/TeamComposer 全量组装（ADR-0005/0033）；"
        "_promote_lead 由 test_refactor_guards 直接 import，"
        "progressive-disclosure 检查 def compose / def compose_team 子串"
    ),
    "lca/layer1_cognitive/body/action_handlers.py": (
        "Body 动作分发单模块（委派/工具/记忆/收口）；ADR-0049 证据平面与 harvest 同文件"
    ),
    "lca/layer1_cognitive/brain/decision_parser.py": (
        "Decision 防腐层归一化管线单入口（ADR-0045）；拆分会破坏 parse 内聚性"
    ),
    "lca/layer1_cognitive/brain/reasoner.py": (
        "PromptReasoner 单模块承载模板渲染 + LLM 调用 + 流式增量（ADR-0041）；"
        "ADR-0052 新增 _strip_empty_prompt_fields 用于 solo 裸模型空字段剥离"
    ),
}


def _collect_all_concrete_classes() -> dict[str, type]:
    """扫描 L0-L3 所有模块，收集其中定义的具体类（含 Protocol 和具体实现）。"""
    result: dict[str, type] = {}
    for pkg_name in _SCAN_PACKAGES:
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
    """从 docs/glossary.md 提取所有术语词条（表格第一列的 **bold** 部分）。"""
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
                    f"  - {cls_name}（如需豁免，请在 docs/glossary.md 登记并在 "
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
            self.skipTest("docs/glossary.md 不存在或为空")

        glossary_text = " ".join(glossary_terms).lower()

        classes = _collect_all_concrete_classes()
        uncovered: list[str] = []

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
                uncovered.append(f"  - {cls_name} (词根: {parts})")

        if len(uncovered) > 5:
            self.fail(
                f"以下 {len(uncovered)} 个类的词根在 glossary.md 中无匹配"
                f"（仅展示前 5 个）:\n"
                + "\n".join(uncovered[:5])
                + "\n请在 docs/glossary.md 中补充对应词条。"
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
            self.skipTest("docs/glossary.md 不存在或为空")

        class_names = _collect_class_names(_REVERSE_SCAN_PACKAGES)
        missing = sorted(
            term for term in terms if _CAMEL_CASE_TERM.match(term) and term not in class_names
        )
        self.assertFalse(
            missing,
            "以下现役术语在 lca 包中不存在对应类名"
            "（已改名/删除的术语请移入「已废弃主名」表，"
            "概念性词语请勿加粗为术语词条）:\n" + "\n".join(f"  - {term}" for term in missing),
        )


if __name__ == "__main__":
    unittest.main()
