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
    "PromptManager": "glossary 显式豁免: Prompt 模板注册与渲染缺少更精确的领域词",
    # 过渡期 alias（ADR-0016）——下一主版本删除后同步清理
    "RespondOperation": "过渡期 alias → RespondOperation",
    "UseToolOperation": "过渡期 alias → UseToolOperation",
    "DelegateOperation": "过渡期 alias → DelegateOperation",
    "HandoffOperation": "过渡期 alias → HandoffOperation",
    "FallbackActionPolicy": "过渡期 alias → FallbackActionPolicy",
}

_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
]

# ── 文件行数上限 ─────────────────────────────────────────────────────────
_MAX_FILE_LINES = 250

# 已登记豁免（引用 ADR 或说明原因）
_LINE_COUNT_EXEMPT: dict[str, str] = {
    "lca/layer4_app/assembly.py": "ADR-0024: Assembly 类 + 模块级自由函数同文件（_promote_supervisor(agent, policy) 由 test_refactor_guards 直接 import，progressive-disclosure 检查 def assemble_agent 子串）",
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


if __name__ == "__main__":
    unittest.main()
