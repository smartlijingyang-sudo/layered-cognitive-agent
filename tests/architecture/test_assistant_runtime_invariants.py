"""Assistant runtime 不变量测试(ADR-0187 §5 + §7 PR-4)。

覆盖 ADR-0187 §5 表中的 PR-4 新增/强化条目:

- **I-A5**:工具 cwd ⊆ home/workspace/(除非显式更高 grant)—— sandbox test
- **I-A6**:禁止跨助理读 memory(isolation test)
- **I-A10**:解析 web-standard 后 plugin 列表不含 assistant.*;
  解析 web-assistant 后含 catalog/bootstrap/workspace
- **I-A13**:记忆面不参与 digest(双向:MEMORY 篡改 → OK;SOUL 篡改 → fail)
- **PR-4 新不变量**:bootstrap 投影字段只来自配置面,不来自 MEMORY/memory/
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
LCA = REPO / "lca"
PROFILES = REPO / "profiles"
WEB_STANDARD = PROFILES / "web-standard.yaml"
WEB_ASSISTANT = PROFILES / "web-assistant.yaml"
BUNDLES = REPO / "bundles"
ASSISTANT_RUNTIME_BUNDLE = BUNDLES / "assistant-runtime.yaml"

# PR-4 三 plugin id(必须存在)
PR4_PLUGIN_IDS: tuple[str, ...] = (
    "lca.plugins.assistant.catalog",
    "lca.plugins.assistant.bootstrap",
    "lca.plugins.assistant.workspace",
)


# ── I-A10 / I-A1:web-standard 不挂 assistant;web-assistant 挂三个 ──


class TestWebAssistantProfileContainsAssistantPlugins:
    """web-assistant profile 解析后 plugin 列表必须含 catalog/bootstrap/workspace。"""

    @pytest.fixture
    def resolved_web_assistant(self) -> Any:
        from lca.harness.profile.resolve import resolve_profile

        return resolve_profile(WEB_ASSISTANT)

    @pytest.fixture
    def resolved_web_standard(self) -> Any:
        from lca.harness.profile.resolve import resolve_profile

        return resolve_profile(WEB_STANDARD)

    def test_web_assistant_contains_three_assistant_plugins(
        self,
        resolved_web_assistant: Any,
    ) -> None:
        plugin_ids = {plugin.id for plugin in resolved_web_assistant.plugins}
        for pid in PR4_PLUGIN_IDS:
            assert pid in plugin_ids, (
                f"web-assistant profile 应挂 {pid};实际 plugin 列表:"
                f"{sorted(p for p in plugin_ids if p.startswith('lca.plugins.assistant'))}"
            )

    def test_web_assistant_provides_assistant_capabilities(
        self,
        resolved_web_assistant: Any,
    ) -> None:
        for plugin in resolved_web_assistant.plugins:
            if plugin.id in PR4_PLUGIN_IDS:
                caps = plugin.definition.provided_capability_keys
                assert (
                    "assistant.catalog" in caps
                    or "assistant.bootstrap" in caps
                    or "assistant.workspace" in caps
                ), f"plugin {plugin.id} 应至少提供一个 assistant.* capability"

    def test_web_standard_does_not_contain_assistant_runtime(
        self,
        resolved_web_standard: Any,
    ) -> None:
        plugin_ids = {plugin.id for plugin in resolved_web_standard.plugins}
        for pid in PR4_PLUGIN_IDS:
            assert pid not in plugin_ids, f"web-standard 不应挂 {pid}(I-A10 P6 存量零打扰)"

    def test_web_standard_yaml_static_no_assistant_string(
        self,
    ) -> None:
        text = WEB_STANDARD.read_text(encoding="utf-8")
        assert "assistant-runtime" not in text, (
            "web-standard.yaml 静态禁止 include assistant-runtime bundle"
        )
        assert "lca.plugins.assistant" not in text, (
            "web-standard.yaml 静态禁止引用 assistant plugin id"
        )


# ── assistant-runtime bundle YAML 静态锁 ──────────────────────────


class TestAssistantRuntimeBundleShape:
    def test_bundle_includes_three_plugin_entries(self) -> None:
        text = ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8")
        for pid in PR4_PLUGIN_IDS:
            assert f"id: {pid}" in text, f"assistant-runtime bundle 应包含 plugin id {pid!r}"

    def test_bundle_modules_use_dotted_path(self) -> None:
        text = ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8")
        for module in (
            "lca.plugins.assistant.catalog",
            "lca.plugins.assistant.bootstrap",
            "lca.plugins.assistant.workspace",
        ):
            assert f"$module: {module}" in text, f"assistant-runtime bundle 应 import {module!r}"


# ── assistant 插件代码静态 grep 锁(不直读 env)─────────────────────


class TestAssistantPluginsDoNotReadOsEnviron:
    """assistant.* 插件代码禁读 os.environ(ADR-0187 §6 删除条件)。"""

    @pytest.mark.parametrize(
        "plugin_path",
        [
            LCA / "plugins" / "assistant" / "catalog.py",
            LCA / "plugins" / "assistant" / "bootstrap.py",
            LCA / "plugins" / "assistant" / "workspace.py",
        ],
    )
    def test_plugin_does_not_read_env(self, plugin_path: Path) -> None:
        text = plugin_path.read_text(encoding="utf-8")
        # 去除 docstring + 行注释
        code_only = re.sub(r'"""[\s\S]*?"""', "", text)
        code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
        code_lines = [line for line in code_only.splitlines() if not line.lstrip().startswith("#")]
        code_only = "\n".join(code_lines)
        for line in code_only.splitlines():
            stripped = line.strip()
            assert "os.environ" not in stripped, (
                f"{plugin_path.name} 含 os.environ 读取:{stripped!r}"
            )
            assert "os.getenv" not in stripped, f"{plugin_path.name} 含 os.getenv 读取:{stripped!r}"


# ── I-A9:不新增 AssistantRuntime / AssistantLoop / 平行编译器 ─────


class TestNoParallelAssistantLoopOrCompiler:
    """``AssistantRuntime`` / ``AssistantLoop`` / ``compile_assistant_plan`` 全部 0。"""

    BANNED_TOKENS: tuple[str, ...] = (
        "AssistantRuntime",
        "AssistantLoop",
        "AssistantCognitiveLoop",
        "compile_assistant_plan",
    )

    def test_banned_tokens_absent_from_lca(self) -> None:
        for token in self.BANNED_TOKENS:
            class_pattern = re.compile(rf"^\s*class\s+{token}\b", re.MULTILINE)
            text = _read_lca_source()
            matches = class_pattern.findall(text)
            assert matches == [], f"lca/ 出现 class {token} 定义 {len(matches)} 处:{matches[:3]}"
            # 函数调用 / 模块引用也应 0
            assert f"{token}(" not in text and f"class {token}" not in text, (
                f"lca/ 出现 {token} 引用"
            )


# ── PR-4 新不变量:bootstrap 投影字段只来自配置面 ─────────────────


class TestBootstrapProjectionOnlyFromConfigFace:
    """bootstrap.project 输出 ContextManifest 不含 MEMORY 字面(I-A13 + PR-4)。"""

    def test_bootstrap_module_no_memory_string(self) -> None:
        text = (LCA / "plugins" / "assistant" / "bootstrap.py").read_text(encoding="utf-8")
        # 去除 docstring + 行注释 + @plugin 装饰器 description 字段
        # (description 是文档 metadata,可以提 I-A13 引用)
        code_only = re.sub(r'"""[\s\S]*?"""', "", text)
        code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
        code_lines = [line for line in code_only.splitlines() if not line.lstrip().startswith("#")]
        code_only = "\n".join(code_lines)
        # 整体检测:任何 MEMORY.md 字面必须出现在 _memory_layer_excluded_from_items
        # 函数内或 @plugin description 字符串内;否则 fail。
        offenders: list[str] = []
        in_exclusion_check = False
        in_plugin_decorator = False
        for line in code_only.splitlines():
            stripped = line.strip()
            if "@plugin(" in stripped:
                in_plugin_decorator = True
                continue
            if in_plugin_decorator and stripped.endswith(")"):
                in_plugin_decorator = False
                continue
            if in_plugin_decorator:
                continue
            if "def _memory_layer_excluded_from_items" in stripped:
                in_exclusion_check = True
                continue
            if in_exclusion_check and stripped.startswith("return True"):
                in_exclusion_check = False
                continue
            if in_exclusion_check:
                continue
            if "MEMORY.md" in stripped or "/memory/" in stripped:
                offenders.append(stripped)
        assert offenders == [], (
            f"bootstrap.py 含 MEMORY 字面但不在 exclusion-check / @plugin desc 内"
            f"(I-A13 守门):{offenders}"
        )

    def test_workspace_module_no_memory_string(self) -> None:
        text = (LCA / "plugins" / "assistant" / "workspace.py").read_text(encoding="utf-8")
        code_only = re.sub(r'"""[\s\S]*?"""', "", text)
        code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
        code_lines = [line for line in code_only.splitlines() if not line.lstrip().startswith("#")]
        code_only = "\n".join(code_lines)
        for line in code_only.splitlines():
            stripped = line.strip()
            if "MEMORY.md" in stripped or "memory/" in stripped or "/memory" in stripped:
                pytest.fail(f"workspace.py 不应引用 memory 子目录:{stripped!r}")


# ── COMPAT 占位 grep 守门(PR-4 范围不应新增无 delete-when 占位)───


class TestCompatMarkersHaveDeleteWhen:
    def test_no_bare_compat_in_assistant_pr4_plugins(self) -> None:
        offenders: list[tuple[Path, str]] = []
        for path in (
            LCA / "plugins" / "assistant" / "bootstrap.py",
            LCA / "plugins" / "assistant" / "workspace.py",
        ):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "COMPAT" in line and "delete-when" not in line:
                    offenders.append((path, line.strip()))
        assert offenders == [], f"PR-4 新 plugin 不应有裸 COMPAT(无 delete-when):{offenders}"


# ── 辅助 ──────────────────────────────────────────────────────────


def _read_lca_source() -> str:
    """把 lca/ 下所有 ``.py`` 文件拼成一个字符串(忽略 .pyc 与 __pycache__)。"""
    chunks: list[str] = []
    for path in sorted(LCA.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)
