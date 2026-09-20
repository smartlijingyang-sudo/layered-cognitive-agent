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
import yaml

REPO = Path(__file__).resolve().parents[2]
LCA = REPO / "lca"
PROFILES = REPO / "profiles"
WEB_STANDARD = PROFILES / "web-standard.yaml"
WEB_ASSISTANT = PROFILES / "web-assistant.yaml"
BUNDLES = REPO / "bundles"
ASSISTANT_RUNTIME_BUNDLE = BUNDLES / "assistant-runtime.yaml"

# PR-4 三 plugin id(必须存在)
PR4_PLUGIN_IDS: tuple[str, ...] = (
    "lca.plugins.assistant.catalog.catalog",
    "lca.plugins.assistant.bootstrap.bootstrap",
    "lca.plugins.assistant.workspace.workspace",
)

# 三 plugin 的 import 路径(assistant-runtime bundle 的 ``$module`` 必须逐字相同)
CATALOG_MODULE = "lca.plugins.domain.assistant.catalog.plugin"
BOOTSTRAP_MODULE = "lca.plugins.assistant.bootstrap.bootstrap"
WORKSPACE_MODULE = "lca.plugins.assistant.workspace.workspace"
PR4_PLUGIN_MODULES: tuple[str, ...] = (CATALOG_MODULE, BOOTSTRAP_MODULE, WORKSPACE_MODULE)


def _module_file(dotted: str) -> Path:
    """``lca.plugins.x.y`` → ``<repo>/lca/plugins/x/y.py``。"""
    parts = dotted.split(".")
    return REPO.joinpath(*parts[:-1]) / f"{parts[-1]}.py"


CATALOG_FILE = _module_file(CATALOG_MODULE)
BOOTSTRAP_FILE = _module_file(BOOTSTRAP_MODULE)
WORKSPACE_FILE = _module_file(WORKSPACE_MODULE)

# ADR-0242 D3：run 装配路径（persona_from_home 调用点）
RUNNABLE_ASSEMBLY_FILE = (
    REPO / "lca/plugins/transport/webserver/carrier/runs/lifecycle/runnable_assembly.py"
)


def _bundle_plugin_ids(bundle: Path) -> frozenset[str]:
    data = yaml.safe_load(bundle.read_text(encoding="utf-8"))
    return frozenset(entry["id"] for entry in data["entries"])


# 助理域部署相对 web-standard 的全部增量 = 两条 bundle 的 entry(不另立 id 清单)
ASSISTANT_DOMAIN_PLUGIN_IDS = _bundle_plugin_ids(ASSISTANT_RUNTIME_BUNDLE) | _bundle_plugin_ids(
    BUNDLES / "composio-tools.yaml"
)


# ── I-A10 / I-A1:web-standard 不挂 assistant;web-assistant 挂三个 ──


class TestWebAssistantProfileContainsAssistantPlugins:
    """web-assistant profile 解析后 plugin 列表必须含 catalog/bootstrap/workspace。"""

    @pytest.fixture
    def resolved_web_assistant(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        from lca.harness.profile.resolve.resolve import resolve_profile

        # composio-tools 的 provider 把 api_key 声明为 required env;本类锁的是
        # profile 形状,不是凭证,所以注入占位值让 resolve 不依赖开发者 .env。
        monkeypatch.setenv("COMPOSIO_API_KEY", "placeholder-not-a-credential")
        return resolve_profile(WEB_ASSISTANT)

    @pytest.fixture
    def resolved_web_standard(self) -> Any:
        from lca.harness.profile.resolve.resolve import resolve_profile

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

    def test_web_assistant_resolves_every_web_standard_plugin(
        self,
        resolved_web_assistant: Any,
        resolved_web_standard: Any,
    ) -> None:
        """切到 web-assistant 的部署 = web-standard + 助理域,逐项相等。

        只比 plugin id 集不够:``disabled`` 漂移看不出来 —— base.yaml 的
        deny-by-default permission manifest 没关时,id 集完全正常,而每个工具
        调用都在 ``effect.pre_dispatch.envelope_check`` 被拒。bundle 缺失同样
        只在 plan 拓扑上显形(参见 test_p7_profile_regions_declare.py 的
        bundle 锁)。
        """

        def effective(resolved: Any) -> set[str]:
            return {plugin.id for plugin in resolved.plugins if not plugin.disabled}

        standard_ids = effective(resolved_web_standard)
        assistant_ids = effective(resolved_web_assistant)
        assert not standard_ids - assistant_ids, (
            f"web-assistant 相对 web-standard 缺 plugin:{sorted(standard_ids - assistant_ids)}"
        )
        assert assistant_ids - standard_ids == ASSISTANT_DOMAIN_PLUGIN_IDS, (
            "web-assistant 的增量 plugin 应恰好是助理域 + composio:"
            f"{sorted(assistant_ids - standard_ids)}"
        )

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
        """bundle 的 ``$module`` 必须指向真实存在的模块文件。

        路径写错时 resolve 才报错,本锁让漂移在静态层就红。
        """
        text = ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8")
        for module in PR4_PLUGIN_MODULES:
            assert f"$module: {module}" in text, f"assistant-runtime bundle 应 import {module!r}"
        for path in (CATALOG_FILE, BOOTSTRAP_FILE, WORKSPACE_FILE):
            assert path.is_file(), f"assistant plugin 模块文件不存在:{path}"


# ── assistant 插件代码静态 grep 锁(不直读 env)─────────────────────


class TestAssistantPluginsDoNotReadOsEnviron:
    """assistant.* 插件代码禁读 os.environ(ADR-0187 §6 删除条件)。"""

    @pytest.mark.parametrize(
        "plugin_path",
        [CATALOG_FILE, BOOTSTRAP_FILE, WORKSPACE_FILE],
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
        text = BOOTSTRAP_FILE.read_text(encoding="utf-8")
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
        text = WORKSPACE_FILE.read_text(encoding="utf-8")
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
        for path in (BOOTSTRAP_FILE, WORKSPACE_FILE):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "COMPAT" in line and "delete-when" not in line:
                    offenders.append((path, line.strip()))
        assert offenders == [], f"PR-4 新 plugin 不应有裸 COMPAT(无 delete-when):{offenders}"


# ── ADR-0242 D3 防复发：运行路径必须调用 persona_from_home ─────────


class TestRuntimePersonaInjection:
    """「设计写了实现缺失」回归护栏：run 装配必须消费 Home 人设。"""

    def test_runnable_assembly_calls_persona_from_home(self) -> None:
        text = RUNNABLE_ASSEMBLY_FILE.read_text(encoding="utf-8")
        assert "persona_from_home" in text, (
            "runnable_assembly.py 必须调用 persona_from_home（ADR-0242 D3）"
        )
        assert "role_profile" in text, "RunnableBuildRequest 必须携带 role_profile（ADR-0242 D3）"


# ── ADR-0242 PR-7：plan.yaml 配置面 + 17-section 闭集不变 ─────────────


class TestPlanYamlConfigFace:
    """plan.yaml 进配置面 digest；模板目录必须带默认文件（I-B10/I-B11）。"""

    def test_plan_yaml_in_config_face_files(self) -> None:
        from lca.plugins.assistant.home._home_layout import CONFIG_FACE_FILES

        assert "plan.yaml" in CONFIG_FACE_FILES

    def test_all_template_dirs_have_plan_yaml(self) -> None:
        from lca.plugins.assistant.home._home_layout import TEMPLATE_REGISTRY

        templates_root = REPO / "lca/plugins/assistant/templates"
        for dir_name in TEMPLATE_REGISTRY.values():
            assert (templates_root / dir_name / "plan.yaml").is_file(), f"{dir_name}/plan.yaml 缺失"


class TestPromptSectionRegistryUnchanged:
    """plan.yaml 只能引用既有 section 注册表闭集（ADR-0242 I-B11 / C1）。

    新增 section 类型必须走 ADR 闭集扩展流程并同步本闭集常量。
    """

    def test_registered_prompt_section_names_unchanged(self) -> None:
        from lca.contracts.models.cognition.prompt_assembly import (
            REGISTERED_PROMPT_SECTION_NAMES,
        )

        assert (
            frozenset(
                {
                    "role",
                    "goal",
                    "backstory",
                    "available_skills",
                    "react_workflow",
                    "react_tool_usage_guidelines",
                    "routing_instructions",
                    "hierarchical_instructions",
                    "tools",
                    "cloud_sandbox",
                    "current_date",
                    "task",
                    "activated_skills",
                    "context",
                    "user_profile",
                    "teammates",
                    "assigned_roles_text",
                    "member_reports_text",
                    "member_status_text",
                    "evidence_pack_text",
                }
            )
            == REGISTERED_PROMPT_SECTION_NAMES
        )

    def test_builtin_template_ids_unchanged(self) -> None:
        from lca.contracts.models.cognition.prompt_assembly import (
            BUILTIN_PROMPT_TEMPLATE_IDS,
        )

        assert (
            frozenset({"react_prompt", "routing_prompt", "hierarchical_prompt"})
            == BUILTIN_PROMPT_TEMPLATE_IDS
        )


# ── 辅助 ──────────────────────────────────────────────────────────


def _read_lca_source() -> str:
    """把 lca/ 下所有 ``.py`` 文件拼成一个字符串(忽略 .pyc 与 __pycache__)。"""
    chunks: list[str] = []
    for path in sorted(LCA.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)
