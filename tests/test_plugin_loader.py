"""Loader 测试 —— 拓扑、失败语义、dispose 传播。"""

from __future__ import annotations

import pytest

from lca.contracts.mechanisms.plugin import PluginConfig
from lca.layer0_infra.plugin.loader import (
    Loader,
    LoaderError,
    PluginEntry,
)

# ── helpers ────────────────────────────────────────────────


def _make_module(
    name: str,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    *,
    on_apply=None,
    config_cls: type[PluginConfig] = PluginConfig,
):
    """模拟插件模块。"""

    class Module:
        pass

    mod = Module()
    mod.name = name
    mod.inject = inject
    mod.provides = provides
    mod.Config = config_cls

    def apply(ctx, config):
        if on_apply is not None:
            on_apply(ctx, config)

    mod.apply = apply
    return mod


# ── 基本拓扑 ──────────────────────────────────────────────


class TestBasicLoad:
    @pytest.mark.asyncio
    async def test_empty_profile_loads_to_empty_tree(self) -> None:
        tree = await Loader().load([])
        assert tree.entries == []

    @pytest.mark.asyncio
    async def test_single_plugin_no_deps(self) -> None:
        mod = _make_module("llm", provides="llm")
        entry = PluginEntry(id="llm", module=mod, config={})
        tree = await Loader().load([entry])
        assert tree.host.get_service("llm") is not None

    @pytest.mark.asyncio
    async def test_two_plugins_respect_inject(self) -> None:
        order: list[str] = []

        llm_mod = _make_module("llm", provides="llm", on_apply=lambda ctx, cfg: order.append("llm"))
        reasoner_mod = _make_module(
            "reasoner", inject=("llm",), on_apply=lambda ctx, cfg: order.append("reasoner")
        )
        await Loader().load(
            [
                PluginEntry(id="reasoner", module=reasoner_mod, config={}),
                PluginEntry(id="llm", module=llm_mod, config={}),
            ]
        )
        assert order == ["llm", "reasoner"]

    @pytest.mark.asyncio
    async def test_plugin_can_mount_via_ctx(self) -> None:
        mod = _make_module(
            "llm",
            provides="llm",
            on_apply=lambda ctx, cfg: ctx.mount("llm", {"kind": "mock"}),
        )
        tree = await Loader().load([PluginEntry(id="llm", module=mod, config={})])
        assert tree.host.get_service("llm") == {"kind": "mock"}

    @pytest.mark.asyncio
    async def test_plugin_receives_parsed_config(self) -> None:

        class MyCfg(PluginConfig):
            threshold: int = 0

        seen = {}

        def on_apply(ctx, cfg):
            seen["threshold"] = cfg.threshold

        mod = _make_module("compaction", provides="compaction", on_apply=on_apply, config_cls=MyCfg)
        await Loader().load([PluginEntry(id="compaction", module=mod, config={"threshold": 42})])
        assert seen["threshold"] == 42

    @pytest.mark.asyncio
    async def test_disabled_entries_are_skipped(self) -> None:
        mod = _make_module("llm", provides="llm")
        tree = await Loader().load([PluginEntry(id="llm", module=mod, config={}, disabled=True)])
        assert tree.host.get_service("llm") is None
        assert tree.entries == []

    @pytest.mark.asyncio
    async def test_entry_ids_must_be_unique(self) -> None:
        mod = _make_module("llm")
        with pytest.raises(LoaderError):
            await Loader().load(
                [
                    PluginEntry(id="llm", module=mod, config={}),
                    PluginEntry(id="llm", module=mod, config={}),
                ]
            )


# ── 失败语义 ──────────────────────────────────────────────


class TestFailureSemantics:
    @pytest.mark.asyncio
    async def test_missing_inject_reports_which(self) -> None:
        mod = _make_module("reasoner", inject=("llm",))
        with pytest.raises(LoaderError) as exc:
            await Loader().load([PluginEntry(id="reasoner", module=mod, config={})])
        assert "llm" in str(exc.value)

    @pytest.mark.asyncio
    async def test_double_provides_fails(self) -> None:
        a = _make_module("a", provides="llm")
        b = _make_module("b", provides="llm")
        with pytest.raises(LoaderError):
            await Loader().load(
                [
                    PluginEntry(id="a", module=a, config={}),
                    PluginEntry(id="b", module=b, config={}),
                ]
            )

    @pytest.mark.asyncio
    async def test_apply_failure_marks_failed(self) -> None:
        a = _make_module(
            "a",
            provides="x",
            on_apply=lambda ctx, cfg: ctx.effect(lambda: lambda: None),
        )
        b = _make_module(
            "b",
            inject=("x",),
            on_apply=lambda ctx, cfg: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        tree = await Loader().load(
            [
                PluginEntry(id="a", module=a, config={}),
                PluginEntry(id="b", module=b, config={}),
            ]
        )
        # a activated, b failed
        from lca.layer0_infra.plugin.kernel import PluginState

        assert tree.host.handles["a"].state is PluginState.ACTIVE
        assert tree.host.handles["b"].state is PluginState.FAILED

    @pytest.mark.asyncio
    async def test_config_validation_fails_load(self) -> None:

        class MyCfg(PluginConfig):
            required: str

        mod = _make_module("p", provides="p", config_cls=MyCfg)
        with pytest.raises(LoaderError, match="config validation"):
            await Loader().load([PluginEntry(id="p", module=mod, config={})])

    @pytest.mark.asyncio
    async def test_cycle_detected(self) -> None:
        a = _make_module("a", inject=("b",), provides="a")
        b = _make_module("b", inject=("a",), provides="b")
        with pytest.raises(LoaderError):
            await Loader().load(
                [
                    PluginEntry(id="a", module=a, config={}),
                    PluginEntry(id="b", module=b, config={}),
                ]
            )


# ── 生命周期 ──────────────────────────────────────────────


class TestTreeDispose:
    @pytest.mark.asyncio
    async def test_tree_entries_list_enabled_ids(self) -> None:
        a = _make_module("a", provides="a")
        b = _make_module("b", inject=("a",), provides="b")
        tree = await Loader().load(
            [
                PluginEntry(id="a", module=a, config={}),
                PluginEntry(id="b", module=b, config={}),
            ]
        )
        assert [e.id for e in tree.entries] == ["a", "b"]
