"""ADR-0187 §5 / §7 PR-3 架构不变量(I-A1 / I-A9 / I-A10 / I-A11 / I-A13)。

每个测试对应 ADR-0187 §5 表里的一条不变量:

- I-A1:无 assistant_id 的 run 行为 = 启用前基线(web-standard 回归绿)
  → PR-3 不进 web-standard ⇒ 此处断言 ``web-standard`` resolve 后的 plugin
  列表不含 ``lca.plugins.assistant.*``(等价于 I-A10 同实现)
- I-A7:配置变更 ⇒ ``revision_seq++`` 且 ``revisions/`` 有快照 → 本 PR-3
  revise 未实现,此测试断言 Catalog 接口签名存在即可(后续 PR-5 锁回归)
- I-A9:不新增顶层 loop 类 → ``rg 'AssistantRuntime|AssistantLoop' lca`` = 0
- I-A10:assistant-runtime 未进 web-standard → 同 I-A1 的实现
- I-A11:create 必发对应 EP → 已由 ``tests/plugins/assistant/test_catalog.py``
  的 ``test_create_emits_assistant_created_event`` 守住;此处再加 1 条
  静态保证 —— plugin ``emits`` 声明含 ``assistant.created``
- I-A13:记忆面写入不经 manifest digest、不触发 ``revision_seq`` → 已由
  ``tests/plugins/assistant/test_catalog.py::TestMemoryLayerDigestPolicy``
  守住(双向)
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

# 助理域 12 EP 闭集(PR-2 落 contracts 层);本 PR-3 仅允许发射 ``assistant.created``
# (PR-4…PR-8 才补其它 11 EP)
_ASSISTANT_CREATED_EP = "assistant.created"


# ── I-A10 / I-A1:web-standard 不挂 assistant 插件 ─────────────────────


class TestWebStandardDoesNotIncludeAssistantRuntime:
    """web-standard profile resolve 后 plugin 列表不含 ``lca.plugins.assistant.*``。

    I-A1 + I-A10 同一实现:web-standard 不进 assistant-runtime(默认 profile
    零打扰);P6「存量零打扰」由本测试守住。
    """

    @pytest.fixture
    def resolved_web_standard(self) -> Any:
        from lca.harness.profile.resolve import resolve_profile

        return resolve_profile(WEB_STANDARD)

    def test_web_standard_plugin_ids_exclude_assistant(
        self,
        resolved_web_standard: Any,
    ) -> None:
        assistant_plugins = [
            plugin.id
            for plugin in resolved_web_standard.plugins
            if plugin.id.startswith("lca.plugins.assistant.")
        ]
        assert assistant_plugins == [], (
            f"web-standard 不应挂 assistant 插件,实际挂了 {assistant_plugins}"
        )

    def test_web_standard_capability_providers_exclude_assistant(
        self,
        resolved_web_standard: Any,
    ) -> None:
        """``assistant.*`` capability 必须不在 web-standard 提供者集合里。"""
        for plugin in resolved_web_standard.plugins:
            for cap in plugin.definition.provided_capability_keys:
                assert not cap.startswith("assistant."), (
                    f"web-standard plugin {plugin.id!r} 提供了 assistant 域 capability {cap!r}"
                )


# ── I-A7:Catalog 接口签名(revise 占位 + snapshot_dir)─────────────────


class TestAssistantCatalogInterfaceContract:
    """PR-3 范围 revise_profile / reimport / retire 是占位(抛 NotImplementedError);

    本测试断言 Protocol 签名存在 → PR-5 落实现时本测试不变(回归锁)。
    """

    def test_protocol_defines_revise_reimport_retire(self) -> None:
        from lca.contracts.protocols.assistant.catalog import AssistantCatalog

        for method in ("revise_profile", "reimport", "retire"):
            assert hasattr(AssistantCatalog, method), f"AssistantCatalog 缺 {method!r}"

    def test_create_get_list_signatures(self) -> None:
        from lca.contracts.protocols.assistant.catalog import AssistantCatalog

        for method in ("create", "get", "list"):
            assert hasattr(AssistantCatalog, method), f"AssistantCatalog 缺 {method!r}"


# ── I-A9:不新增顶层 loop 类 ────────────────────────────────────────


class TestNoParallelAssistantLoopClasses:
    """禁止 ``AssistantRuntime`` / ``AssistantLoop`` / ``AssistantCognitiveLoop``。

    ADR-0187 §6 删除条件 + §8 实现拒收信号 1 + I-A9。
    """

    @pytest.mark.parametrize(
        "banned",
        ["AssistantRuntime", "AssistantLoop", "AssistantCognitiveLoop"],
    )
    def test_banned_class_name_absent_from_lca(self, banned: str) -> None:
        # 全文正则搜索,允许注释 + docstring + 测试文件名出现;
        # 但禁止在 ``class`` 定义行出现
        text = _read_lca_source()
        class_pattern = re.compile(rf"^\s*class\s+{banned}\b", re.MULTILINE)
        matches = class_pattern.findall(text)
        assert matches == [], f"{banned} 出现 {len(matches)} 处 class 定义:{matches[:3]}"

    def test_banned_module_attribute_absent(self) -> None:
        """模块级变量绑定(``AssistantRuntime = ...`` / ``class AssistantLoop: ...``)

        也守。``grep -rn 'AssistantRuntime' lca`` 必须为 0(命中 class 定义 / 引用)。
        """
        text = _read_lca_source()
        for banned in ("AssistantRuntime", "AssistantLoop"):
            assert (
                f"{banned}(" not in text
                and f"class {banned}" not in text
                and f" {banned}." not in text
            ), f"{banned} 出现在 lca/ 源代码"


def _read_lca_source() -> str:
    """把 lca/ 下所有 ``.py`` 文件拼成一个字符串(忽略 .pyc 与 __pycache__)。"""
    chunks: list[str] = []
    for path in sorted(LCA.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


# ── I-A11:plugin ``emits`` 声明含 ``assistant.created`` ──────────────


class TestAssistantCatalogEmitsCreatedEP:
    """plugin Manifest ``OwnershipDeclaration.emits`` 必含 ``assistant.created``。

    PR-2 已落 contracts 层 EP 描述符的 emitter 命名空间;本测试守住
    plugin manifest 的静态声明与 descriptor 对齐。
    """

    def test_plugin_emits_assistant_created(self) -> None:
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.catalog import setup

        definition = definition_from_plugin(setup)
        assert definition.ownership is not None, "plugin 缺 OwnershipDeclaration"
        assert _ASSISTANT_CREATED_EP in definition.ownership.emits, (
            f"plugin emits={definition.ownership.emits!r} 缺 {_ASSISTANT_CREATED_EP!r}"
        )


# ── 不直读 os.environ(I-A 类范畴;ADR-0187 §6 删除条件)───────────────


class TestAssistantPluginsDoNotReadOsEnviron:
    """禁止 ``assistant.*`` 插件模块读 ``os.environ[...]``。

    根路径只来自 Profile ``{from_env: LCA_ASSISTANTS_ROOT}`` 注入(详见
    ADR-0187 §3 D2 + §6 删除条件);本测试守住 grep = 0。
    """

    def test_no_os_environ_in_assistant_modules(self) -> None:
        assistant_modules = list((LCA / "plugins" / "assistant").rglob("*.py"))
        # templates/*/ 模板是 data,允许文案注释提到 env;只查 plugin code 文件
        plugin_modules = [path for path in assistant_modules if "templates" not in path.parts]
        offenders: list[tuple[Path, str, int]] = []
        for path in plugin_modules:
            text = path.read_text(encoding="utf-8")
            # strip triple-quoted docstrings (allow mention of env in docs/ADR refs)
            code_only = re.sub(r'"""[\s\S]*?"""', "", text)
            code_only = re.sub(r"'''[\s\S]*?'''", "", code_only)
            # strip line comments too (single-line only — keeps real code intact)
            code_lines = [
                line for line in code_only.splitlines() if not line.lstrip().startswith("#")
            ]
            code_only = "\n".join(code_lines)
            for line_no, line in enumerate(code_only.splitlines(), 1):
                if "os.environ" in line or "os.getenv" in line:
                    offenders.append((path, line.strip(), line_no))
        assert offenders == [], f"assistant 插件代码禁读 env,违规:{offenders}"


# ── assistant 插件只一个目录一个 .py(AGENTS.md §5 Plugin 范式)───────


class TestAssistantPluginOneDirOnePy:
    """lca/plugins/assistant/ 下每个 kind 目录只一个 .py plugin 文件。

    templates/ 是 data 目录,单独规则(本测试放过)。
    """

    def test_no_subdir_manifest_under_assistant(self) -> None:
        """禁止 ``lca/plugins/assistant/<sub>/manifest.py + plugin.py`` 双文件形态。"""
        for sub in (LCA / "plugins" / "assistant").iterdir():
            if sub.name in {
                "__init__.py",
                "__pycache__",
                "templates",
                "_events.py",
                "_home_layout.py",
            }:
                # _events.py / _home_layout.py 是内部辅助(下划线前缀),
                # 模板 + __init__ + 私有 helpers 都非 plugin
                continue
            if not sub.is_dir():
                continue
            py_files = [p for p in sub.glob("*.py") if p.name != "__init__.py"]
            assert len(py_files) == 1, f"目录 {sub} 应只有一个 plugin 文件,实际 {py_files}"


# ── 静态:web-standard profile resolve 不含 assistant plugin id ──────


class TestWebStandardYamlGrepInvariant:
    """ADR-0187 §6:web-standard.yaml 不引入 assistant-runtime 引用。

    静态 grep 守护:未来若有人改 profile 引入 assistant plugin id,本测试
    立即报警。
    """

    def test_web_standard_yaml_does_not_mention_assistant(self) -> None:
        text = WEB_STANDARD.read_text(encoding="utf-8")
        assert "lca.plugins.assistant" not in text, (
            "web-standard.yaml 不应直接引用 assistant plugin id"
        )

    def test_web_standard_bundles_do_not_include_assistant_bundle(self) -> None:
        text = WEB_STANDARD.read_text(encoding="utf-8")
        assert "assistant-runtime" not in text, (
            "web-standard.yaml 不应 include assistant-runtime bundle(PR-4 才做)"
        )


# ── COMPAT 占位 grep 守门 ───────────────────────────────────────────


class TestCompatMarkersHaveDeleteWhen:
    """``COMPAT(delete-when: ...)`` 注释必须带删除条件;无期限占位 = 红灯。"""

    def test_compat_markers_in_assistant_modules_have_delete_when(self) -> None:
        for path in (LCA / "plugins" / "assistant").rglob("*.py"):
            if "templates" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "COMPAT" not in text:
                continue
            # 找到所有 COMPAT 行,验证每个都跟 delete-when
            compat_lines = [line for line in text.splitlines() if "COMPAT" in line]
            for line in compat_lines:
                assert "delete-when" in line, f"{path} 含 COMPAT 但缺 delete-when:{line!r}"
