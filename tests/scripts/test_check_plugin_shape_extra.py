"""Tests for the 5 new dimensions added by PR-1 (single-plugin-universe).

Each test builds a tiny temp project that reproduces one violation kind, runs
the corresponding scanner function, and asserts the finding is reported.

Covers dimensions added on top of the original 3:
1. ``plugin_location`` — ``@plugin`` outside ``lca/plugins/`` /
   ``lca_kernel/events/manifest.py``.
2. ``orphan_plugin`` — ``@plugin`` file under plugins/ with no bundle ``$module``.
3. ``dead_bundle_ref`` — ``$module`` not importable or ``@plugin(id=)`` ≠ entry ``id:``.
4. ``plugin_in_init`` — ``@plugin(...)`` in ``__init__.py``.
5. ``duplicate_id`` (re-listed as dimension 8 in the PR-1 row).

Baseline-mode + scan() integration is also exercised for regression detection.
"""

from __future__ import annotations

import json
import sys
import textwrap
import types
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_plugin_shape import (  # noqa: E402
    ALL_KINDS,
    KIND_DEAD_BUNDLE_REF,
    KIND_DUPLICATE_ID,
    KIND_ORPHAN_PLUGIN,
    KIND_PLUGIN_IN_INIT,
    KIND_PLUGIN_LOCATION,
    _relative_to_root,
    _scan_dead_bundle_refs,
    _scan_duplicate_ids,
    _scan_orphan_plugins,
    _scan_plugin_in_init,
    _scan_plugin_location,
    scan,
)

# ── Temp project helper ─────────────────────────────────────────────────


def _build_plugin_file(parent: Path, *, rel_under: Path, body: str) -> Path:
    """在 ``parent/rel_under`` 写入 ``@plugin(...)`` 源码。"""
    target = parent / rel_under
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body), encoding="utf-8")
    return target


def _install_fake_plugin_api() -> None:
    """注入占位 ``lca.harness.plugin_api``,让 fixture 模块
    ``from lca.harness.plugin_api import plugin`` 不触发真实框架签名校验。

    仅在 ``lca.harness.plugin_api`` 尚未被真实模块占用时注入,避免污染主测试环境。
    """
    if "lca.harness.plugin_api" in sys.modules:
        return
    api = types.ModuleType("lca.harness.plugin_api")

    def _plugin(*_args, **_kwargs):
        """占位 plugin 装饰器;实际语义不验证。"""

        def _decorator(fn):
            return fn

        return _decorator

    api.plugin = _plugin
    sys.modules["lca.harness.plugin_api"] = api


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_plugin_api():
    """每个 test 自动装占位 plugin_api,避免真实 lca 框架初始化污染。"""
    _install_fake_plugin_api()


# ── Dimension 1: plugin_location ────────────────────────────────────────


def test_plugin_location_flags_outside_legal(tmp_path: Path) -> None:
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    (plugins_root / "good.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(
                id="plugins.good",
                effects="none",
            )
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    _build_plugin_file(
        proj,
        rel_under=Path("cognition/team/modes/solo_mode.py"),
        body="""\
            from lca.harness.plugin_api import plugin

            @plugin(
                id="modes.solo",
                effects="none",
            )
            async def setup(ctx, config):
                pass
            """,
    )
    findings = _scan_plugin_location(
        production_roots=[proj],
        allowed=("plugins/",),
    )
    files = {v.file for v in findings}
    assert "cognition/team/modes/solo_mode.py" in files
    assert all(v.kind == KIND_PLUGIN_LOCATION for v in findings)


def test_plugin_location_passes_when_inside_allowed(tmp_path: Path) -> None:
    proj = tmp_path
    (proj / "plugins").mkdir()
    (proj / "plugins/good.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.good", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    findings = _scan_plugin_location(
        production_roots=[proj],
        allowed=("plugins/",),
    )
    assert findings == []


def test_plugin_location_excludes_tests_and_vendored(tmp_path: Path) -> None:
    proj = tmp_path
    # tests/ + vendor/ should be skipped.
    (proj / "tests").mkdir()
    (proj / "tests/test_x.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="fixture.test", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    (proj / "vendor").mkdir()
    (proj / "vendor/foo.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="fixture.vendor", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    findings = _scan_plugin_location(
        production_roots=[proj],
        allowed=("plugins/",),
    )
    assert findings == []


# ── Dimension 4: plugin_in_init ─────────────────────────────────────────


def test_plugin_in_init_flags(tmp_path: Path) -> None:
    proj = tmp_path
    (proj / "plugins").mkdir()
    (proj / "plugins/foo").mkdir()
    (proj / "plugins/foo/__init__.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.foo", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    findings = _scan_plugin_in_init(production_roots=[proj])
    assert len(findings) == 1
    assert findings[0].kind == KIND_PLUGIN_IN_INIT
    assert findings[0].plugin_id == "plugins.foo"
    assert findings[0].file.endswith("plugins/foo/__init__.py")


def test_plugin_in_init_clean_when_only_init_dirs(tmp_path: Path) -> None:
    proj = tmp_path
    (proj / "plugins").mkdir()
    (proj / "plugins/empty_pkg").mkdir()
    (proj / "plugins/empty_pkg/__init__.py").write_text("# empty\n", encoding="utf-8")
    findings = _scan_plugin_in_init(production_roots=[proj])
    assert findings == []


# ── Dimension 2: orphan_plugin ─────────────────────────────────────────


def test_orphan_plugin_flags_unreferenced(tmp_path: Path) -> None:
    """Plugin 文件存在,但 bundles/*.yaml 没引用它的 module。"""
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    (plugins_root / "orphan.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.orphan", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    # Empty bundles dir → no refs at all → orphan.
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    bundles_glob = bundles_dir / "*.yaml"

    # module_root = proj 让 "plugins/orphan.py" → 模块名 "plugins.orphan"。
    findings = _scan_orphan_plugins(plugins_root, bundles_glob, module_root=proj)
    assert len(findings) == 1
    assert findings[0].kind == KIND_ORPHAN_PLUGIN
    assert findings[0].plugin_id == "plugins.orphan"


def test_orphan_plugin_clean_when_referenced(tmp_path: Path) -> None:
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    (plugins_root / "kept.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.kept", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "x.yaml").write_text(
        textwrap.dedent(
            """\
            entries:
              - id: plugins.kept
                name: kept
                $module: plugins.kept
                config: {}
            """
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(proj))
    try:
        findings = _scan_orphan_plugins(plugins_root, bundles_dir / "*.yaml", module_root=proj)
    finally:
        sys.path.pop(0)
        sys.modules.pop("plugins", None)
        sys.modules.pop("plugins.kept", None)

    assert findings == []


# ── Dimension 3: dead_bundle_ref ───────────────────────────────────────


def test_dead_bundle_ref_unimportable(tmp_path: Path) -> None:
    proj = tmp_path
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "bad.yaml").write_text(
        textwrap.dedent(
            """\
            entries:
              - id: ghost.plugin
                name: ghost
                $module: lca.plugins.does_not_exist_anywhere
                config: {}
            """
        ),
        encoding="utf-8",
    )
    findings = _scan_dead_bundle_refs(bundles_dir / "*.yaml")
    assert len(findings) == 1
    assert findings[0].kind == KIND_DEAD_BUNDLE_REF
    assert findings[0].plugin_id == "ghost.plugin"
    assert "does_not_exist_anywhere" in findings[0].detail


def test_dead_bundle_ref_id_mismatch(tmp_path: Path) -> None:
    """Bundle entry id ≠ module's ``@plugin(id=)`` → dead_bundle_ref."""
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    (plugins_root / "real.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.real_native", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "x.yaml").write_text(
        textwrap.dedent(
            """\
            entries:
              - id: plugins.real_but_wrong_alias
                name: real
                $module: plugins.real
                config: {}
            """
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(proj))
    try:
        findings = _scan_dead_bundle_refs(bundles_dir / "*.yaml")
    finally:
        sys.path.pop(0)
        for name in ("plugins", "plugins.real"):
            sys.modules.pop(name, None)

    assert len(findings) == 1
    assert findings[0].kind == KIND_DEAD_BUNDLE_REF
    assert findings[0].plugin_id == "plugins.real_but_wrong_alias"
    assert "plugins.real_native" in findings[0].detail
    assert "plugins.real_but_wrong_alias" in findings[0].detail


def test_dead_bundle_ref_clean(tmp_path: Path) -> None:
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    (plugins_root / "ok.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.ok", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "x.yaml").write_text(
        textwrap.dedent(
            """\
            entries:
              - id: plugins.ok
                name: ok
                $module: plugins.ok
                config: {}
            """
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(proj))
    try:
        findings = _scan_dead_bundle_refs(bundles_dir / "*.yaml")
    finally:
        sys.path.pop(0)
        for name in ("plugins", "plugins.ok"):
            sys.modules.pop(name, None)
    assert findings == []


# ── Dimension 5 (re-listed): duplicate_id ──────────────────────────────


def test_duplicate_id_flags(tmp_path: Path) -> None:
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    for name in ("a.py", "b.py"):
        (plugins_root / name).write_text(
            textwrap.dedent(
                f"""\
                from lca.harness.plugin_api import plugin

                @plugin(id="plugins.dup", effects="none")
                async def setup_{name[0]}(ctx, config):
                    pass
                """
            ),
            encoding="utf-8",
        )
    findings = _scan_duplicate_ids(plugins_root)
    assert len(findings) == 2
    assert {v.file.split("/")[-1] for v in findings} == {"a.py", "b.py"}
    assert all(v.kind == KIND_DUPLICATE_ID for v in findings)


def test_duplicate_id_clean(tmp_path: Path) -> None:
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()
    for name, pid in (("a.py", "plugins.a"), ("b.py", "plugins.b")):
        (plugins_root / name).write_text(
            textwrap.dedent(
                f"""\
                from lca.harness.plugin_api import plugin

                @plugin(id="{pid}", effects="none")
                async def setup(ctx, config):
                    pass
                """
            ),
            encoding="utf-8",
        )
    findings = _scan_duplicate_ids(plugins_root)
    assert findings == []


# ── scan() integration: all 7 kinds can fire in one fixture ─────────────


def test_scan_reports_all_five_new_kinds(tmp_path: Path) -> None:
    """一个 fixture 同时触发 5 个新维度,验证 scan() 汇总输出。"""
    proj = tmp_path
    plugins_root = proj / "plugins"
    plugins_root.mkdir()

    # 合法的孤儿(plugins/ 内 + 没 bundle 引用)
    (plugins_root / "orphan.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.orphan", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )

    # __init__.py 内的 @plugin
    (plugins_root / "init_violation").mkdir()
    (plugins_root / "init_violation" / "__init__.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.init_violation", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )

    # 位置违规:__init__.py 之外、合法的 plugins/ 之外
    (proj / "lca" / "runtime").mkdir(parents=True)
    (proj / "lca" / "runtime" / "reducer.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="lca.escaped", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )

    # 合法的、合法的、合法的 → 被 bundle 引用、id 一致、importable
    (plugins_root / "wired.py").write_text(
        textwrap.dedent(
            """\
            from lca.harness.plugin_api import plugin

            @plugin(id="plugins.wired", effects="none")
            async def setup(ctx, config):
                pass
            """
        ),
        encoding="utf-8",
    )

    # bundle 含 wired(好) + ghost(坏:不可 import) + alias(坏:id mismatch)
    bundles_dir = proj / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "test.yaml").write_text(
        textwrap.dedent(
            """\
            entries:
              - id: plugins.wired
                name: wired
                $module: plugins.wired
                config: {}

              - id: plugins.ghost
                name: ghost
                $module: plugins.does_not_exist
                config: {}

              - id: plugins.alias_mismatch
                name: alias
                $module: plugins.wired
                config: {}
            """
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(proj))
    try:
        report = scan(
            root=plugins_root,
            bundles_glob=bundles_dir / "*.yaml",
            production_roots=[proj],
            allowed_locations=("plugins/",),
            module_root=proj,
        )
    finally:
        sys.path.pop(0)
        for mod in list(sys.modules):
            if mod == "plugins" or mod.startswith("plugins."):
                sys.modules.pop(mod, None)

    by_kind = report.by_kind

    # 仅断言我们 fixture 触发的种类,不去断言全仓清零。
    assert by_kind[KIND_PLUGIN_LOCATION] >= 1
    assert by_kind[KIND_PLUGIN_IN_INIT] == 1
    # orphan:orphan + init_violation(都不在 bundles/*.yaml)
    assert by_kind[KIND_ORPHAN_PLUGIN] == 2
    # dead_bundle_ref:ghost(不可 import)+ alias_mismatch(id 不一致)
    assert by_kind[KIND_DEAD_BUNDLE_REF] == 2


# ── scan() integration: gate via baseline JSON ──────────────────────────


def test_scan_baseline_gate_detects_regression(tmp_path: Path) -> None:
    """scanner 把当前数量写到 baseline,后续扫描超基线则被识别为 regression。"""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    for name in ("a.py", "b.py"):
        (plugins_root / name).write_text(
            textwrap.dedent(
                f"""\
                from lca.harness.plugin_api import plugin

                @plugin(id="plugins.dup_{name[0]}", effects="none")
                async def setup(ctx, config):
                    pass
                """
            ),
            encoding="utf-8",
        )

    # 一次性 baseline = 0 (啥也没有)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"by_kind": dict.fromkeys(ALL_KINDS, 0)}), encoding="utf-8")

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    (bundles / "x.yaml").write_text("entries: []\n", encoding="utf-8")

    report = scan(
        plugins_root, bundles / "*.yaml", [plugins_root], ("plugins/",), module_root=tmp_path
    )
    by_kind = report.by_kind
    baseline_by_kind = dict.fromkeys(ALL_KINDS, 0)
    diff = {k: by_kind.get(k, 0) - baseline_by_kind.get(k, 0) for k in ALL_KINDS}
    # duplicate_id = 0(两个不同 id),但 orphan_plugin 应有 2(无 bundle 引用)
    assert by_kind[KIND_ORPHAN_PLUGIN] == 2
    assert diff[KIND_ORPHAN_PLUGIN] == 2


# ── Helpers ─────────────────────────────────────────────────────────────


def test_relative_to_root_uses_matching_root(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    f = a / "x.py"
    f.write_text("", encoding="utf-8")
    assert _relative_to_root(f, [tmp_path]) == "a/x.py"


def test_relative_to_root_falls_back_to_posix(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere" / "x.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("", encoding="utf-8")
    assert _relative_to_root(other, [tmp_path / "nope"]) == other.as_posix()
