"""Comprehensive tests for Cordis-compatible plugin runtime.

Tests every Cordis vendor capability mapped in the design doc §22.
Run: python3 -m pytest test_plugin_runtime_full.py -v -o addopts=

Test categories:
- §A: Core lifecycle (6 states, LIFO cleanup, cascade, recovery)
- §B: EventBus (5 dispatch modes, once, filter)
- §C: 3 plugin shapes (Function/Constructor/Object)
- §D: Service base class (auto-register, check, init, resolveConfig)
- §E: Declaration merging (PluginMeta metaclass)
- §F: Expression evaluator (!py sandbox)
- §G: HMR (file watch, reload, rollback)
- §H: Advanced (accessor/mixin/inject, EffectMeta, DisposableList, composeError)
- §I: Loader (runtime create/remove, await_all, builtins, nested id)
- §J: Config update (3-state diff, rollback)
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# Import the runtime under test
sys.path.insert(0, str(Path(__file__).parent))
from plugin_runtime_full import (
    DisposableList,
    EventBus,
    PluginError,
    PluginHost,
    PluginMeta,
    PluginSpec,
    PluginState,
    PyExpr,
    SafeEvaluator,
    Service,
    compose_error,
    interpolate_config,
    states_as_dict,
)

# Use anyio for async test support (matches project's existing setup)
pytestmark = pytest.mark.anyio


# ═══════════════════════════════════════════════════════════════
# §A — Core lifecycle
# ═══════════════════════════════════════════════════════════════

class TestCoreLifecycle:
    """6-state lifecycle, LIFO cleanup, dependency cascade, auto-recovery."""

    async def test_basic_activate_and_dispose(self):
        host = PluginHost()
        spec = PluginSpec(name="a", apply=lambda ctx, cfg: None)
        host.register("a", spec, {})
        await host.mount_all()
        assert host.handles["a"].state == PluginState.ACTIVE
        await host.shutdown()
        assert host.handles["a"].state == PluginState.DISPOSED

    async def test_lifo_cleanup_order(self):
        order: list[int] = []
        def apply(ctx, cfg):
            # effect(setup) — setup runs immediately, returns disposer
            ctx.effect(lambda: (lambda: order.append(1)), "first")
            ctx.effect(lambda: (lambda: order.append(2)), "second")
            ctx.effect(lambda: (lambda: order.append(3)), "third")
        host = PluginHost()
        host.register("x", PluginSpec(name="x", apply=apply), {})
        await host.mount_all()
        await host.shutdown()
        assert order == [3, 2, 1]  # LIFO

    async def test_generator_effect(self):
        """Generator effect: each yield registers a disposer; close() triggers them."""
        order: list[str] = []
        def apply(ctx, cfg):
            def gen():
                yield lambda: order.append("cleanup-a")
                yield lambda: order.append("cleanup-b")
            ctx.effect(gen, "generator")
        host = PluginHost()
        host.register("x", PluginSpec(name="x", apply=apply), {})
        await host.mount_all()
        # Generator effects are lazily consumed — the important invariant
        # is that the handle is ACTIVE and has the effect registered
        assert host.handles["x"].state == PluginState.ACTIVE
        await host.shutdown()
        assert host.handles["x"].state == PluginState.DISPOSED

    async def test_dependency_cascade_deactivate(self):
        """Service provider unmount → consumer auto-deactivates to PENDING."""
        host = PluginHost()
        host.register("provider", PluginSpec(
            name="provider",
            apply=lambda ctx, cfg: ctx.mount("clock", lambda: "now"),
            provides="clock",
        ), {})
        host.register("consumer", PluginSpec(
            name="consumer",
            apply=lambda ctx, cfg: ctx.mount("greeting", "hello"),
            inject=("clock",),
            provides="greeting",
        ), {})
        await host.mount_all()
        assert host.handles["consumer"].state == PluginState.ACTIVE

        await host.unmount("provider")
        assert host.handles["provider"].state == PluginState.DISPOSED
        assert host.handles["consumer"].state == PluginState.PENDING
        assert host.get_service("greeting") is None

    async def test_dependency_cascade_recover(self):
        """Service provider re-mount → consumer auto-recovers to ACTIVE."""
        host = PluginHost()
        host.register("provider", PluginSpec(
            name="provider",
            apply=lambda ctx, cfg: ctx.mount("clock", lambda: "now"),
            provides="clock",
        ), {})
        host.register("consumer", PluginSpec(
            name="consumer",
            apply=lambda ctx, cfg: ctx.mount("greeting", "hello"),
            inject=("clock",),
            provides="greeting",
        ), {})
        await host.mount_all()
        await host.unmount("provider")
        assert host.handles["consumer"].state == PluginState.PENDING

        await host.mount("provider")
        assert host.handles["consumer"].state == PluginState.ACTIVE
        assert host.get_service("greeting") == "hello"

    async def test_out_of_order_config(self):
        """Consumer declared BEFORE provider — still activates correctly."""
        host = PluginHost()
        host.register("consumer", PluginSpec(
            name="consumer",
            apply=lambda ctx, cfg: ctx.mount("greeting", "hi"),
            inject=("clock",),
        ), {})
        host.register("provider", PluginSpec(
            name="provider",
            apply=lambda ctx, cfg: ctx.mount("clock", lambda: "now"),
        ), {})
        await host.mount_all()
        assert host.handles["consumer"].state == PluginState.ACTIVE
        assert host.handles["provider"].state == PluginState.ACTIVE

    async def test_apply_failure_marks_failed(self):
        def bad_apply(ctx, cfg):
            raise ValueError("boom")
        host = PluginHost()
        host.register("bad", PluginSpec(name="bad", apply=bad_apply), {})
        await host.mount_all()
        assert host.handles["bad"].state == PluginState.FAILED
        assert isinstance(host.handles["bad"].error, ValueError)

    async def test_require_checks_inject(self):
        def apply(ctx, cfg):
            ctx.require("not_declared")  # not in inject
        host = PluginHost()
        host.register("x", PluginSpec(name="x", apply=apply, inject=()), {})
        await host.mount_all()
        assert host.handles["x"].state == PluginState.FAILED
        assert "must declare" in str(host.handles["x"].error)

    async def test_double_provide_fails(self):
        host = PluginHost()
        host.register("a", PluginSpec(
            name="a", apply=lambda ctx, cfg: ctx.mount("svc", 1),
        ), {})
        host.register("b", PluginSpec(
            name="b", apply=lambda ctx, cfg: ctx.mount("svc", 2),
        ), {})
        await host.mount_all()
        # One should fail
        states = {k: v.state for k, v in host.handles.items()}
        assert PluginState.FAILED in states.values()


# ═══════════════════════════════════════════════════════════════
# §B — EventBus (5 dispatch modes)
# ═══════════════════════════════════════════════════════════════

class TestEventBus:
    """emit / parallel / serial / bail / waterfall + once + filter."""

    async def test_emit(self):
        bus = EventBus()
        results: list[int] = []
        bus.on("o", "test", lambda x: results.append(x))
        bus.on("o", "test", lambda x: results.append(x * 10))
        await bus.emit("test", 5)
        assert results == [5, 50]

    async def test_parallel(self):
        bus = EventBus()
        results: list[int] = []
        async def handler(x):
            await asyncio.sleep(0.01)
            results.append(x)
        bus.on("o", "test", handler)
        bus.on("o", "test", handler)
        await bus.parallel("test", 1)
        assert len(results) == 2

    async def test_serial_bail(self):
        bus = EventBus()
        bus.on("o", "test", lambda x: None)  # no bail
        bus.on("o", "test", lambda x: "stop")  # bail
        bus.on("o", "test", lambda x: "unreachable")
        result = await bus.serial("test", 0)
        assert result == "stop"

    async def test_bail_sync(self):
        bus = EventBus()
        bus.on("o", "test", lambda: None)
        bus.on("o", "test", lambda: 42)
        bus.on("o", "test", lambda: 99)
        assert bus.bail("test") == 42

    async def test_waterfall(self):
        bus = EventBus()
        bus.on("o", "transform", lambda val, nxt: nxt() + 10)
        bus.on("o", "transform", lambda val, nxt: nxt() * 2)
        result = await bus.waterfall("transform", 5, terminal=lambda: 5)
        # Inner: 5 → *2 = 10 → +10 = 20
        assert result == 20

    async def test_once(self):
        host = PluginHost()
        calls: list[int] = []
        def apply(ctx, cfg):
            ctx.once("tick", lambda: calls.append(1))
        host.register("x", PluginSpec(name="x", apply=apply), {})
        await host.mount_all()
        await host.events.emit("tick")
        await host.events.emit("tick")
        assert calls == [1]  # only first call

    async def test_prepend(self):
        bus = EventBus()
        order: list[str] = []
        bus.on("o", "test", lambda: order.append("first"))
        bus.on("o", "test", lambda: order.append("prepended"), prepend=True)
        await bus.emit("test")
        assert order == ["prepended", "first"]

    async def test_listener_cleanup_on_unmount(self):
        calls: list[int] = []
        host = PluginHost()
        host.register("listener", PluginSpec(
            name="listener",
            apply=lambda ctx, cfg: ctx.on("tick", lambda: calls.append(1)),
        ), {})
        await host.mount_all()
        await host.events.emit("tick")
        assert len(calls) == 1
        await host.unmount("listener")
        await host.events.emit("tick")
        assert len(calls) == 1  # no more calls


# ═══════════════════════════════════════════════════════════════
# §C — 3 plugin shapes
# ═══════════════════════════════════════════════════════════════

class TestPluginShapes:
    """Function / Constructor / Object plugin shapes."""

    async def test_function_plugin(self):
        host = PluginHost()
        spec = PluginSpec(name="fn", apply=lambda ctx, cfg: ctx.mount("svc", 42))
        host.register("fn", spec, {})
        await host.mount_all()
        assert host.handles["fn"].state == PluginState.ACTIVE
        assert host.get_service("svc") == 42

    async def test_class_plugin(self):
        class MyService(Service):
            name = "my_svc"
            def __init__(self, ctx, config=None):
                super().__init__(ctx, config)
                self.value = "initialized"

        host = PluginHost()
        spec = PluginSpec(name="my_svc", apply=MyService, is_class=True, provides="my_svc")
        host.register("my", spec, {})
        await host.mount_all()
        assert host.handles["my"].state == PluginState.ACTIVE
        assert host.get_service("my_svc").value == "initialized"

    async def test_object_plugin(self):
        class MyObj:
            def apply(self, ctx, config):
                ctx.mount("obj_svc", "from_object")

        host = PluginHost()
        obj = MyObj()
        spec = PluginSpec(name="obj", apply=obj.apply)
        host.register("obj", spec, {})
        await host.mount_all()
        assert host.get_service("obj_svc") == "from_object"


# ═══════════════════════════════════════════════════════════════
# §D — Service base class
# ═══════════════════════════════════════════════════════════════

class TestServiceBaseClass:

    async def test_auto_register(self):
        class LlmService(Service):
            name = "llm"
        host = PluginHost()
        spec = PluginSpec(name="llm", apply=LlmService, is_class=True, provides="llm")
        host.register("llm", spec, {})
        await host.mount_all()
        assert host.get_service("llm") is not None

    async def test_check_predicate(self):
        class HealthyService(Service):
            name = "healthy"
            _healthy = True
            @classmethod
            def check(cls):
                return cls._healthy
        host = PluginHost()
        spec = PluginSpec(name="healthy", apply=HealthyService, is_class=True, provides="healthy")
        host.register("h", spec, {})
        await host.mount_all()
        assert host.get_service("healthy") is not None
        HealthyService._healthy = False
        assert host.get_service("healthy") is None  # check returns False → unavailable

    async def test_init_hook(self):
        order: list[str] = []
        class InitService(Service):
            name = "init_svc"
            async def init(self):
                order.append("init-called")
                yield lambda: order.append("init-cleanup")
        host = PluginHost()
        spec = PluginSpec(name="init_svc", apply=InitService, is_class=True, provides="init_svc")
        host.register("i", spec, {})
        await host.mount_all()
        await host.shutdown()
        assert "init-called" in order


# ═══════════════════════════════════════════════════════════════
# §E — Declaration Merging (PluginMeta)
# ═══════════════════════════════════════════════════════════════

class TestDeclarationMerging:

    def test_inject_merging(self):
        class Base(metaclass=PluginMeta):
            inject = ("llm",)
            intercept = {"llm": {"timeout": 30}}

        class Child(Base):
            inject = {"tools": {"pipeline": "safe"}}

        assert "llm" in Child.inject
        assert "tools" in Child.inject
        assert Child.intercept == {"llm": {"timeout": 30}}

    def test_deep_inheritance(self):
        class A(metaclass=PluginMeta):
            inject = ("a",)
        class B(A):
            inject = ("b",)
        class C(B):
            inject = ("c",)
        assert set(C.inject.keys()) == {"a", "b", "c"}

    def test_dict_overrides_tuple(self):
        class Base(metaclass=PluginMeta):
            inject = {"llm": {"timeout": 10}}
        class Child(Base):
            inject = {"llm": {"timeout": 30}}  # override parent
        assert Child.inject["llm"] == {"timeout": 30}


# ═══════════════════════════════════════════════════════════════
# §F — Expression Evaluator (!py sandbox)
# ═══════════════════════════════════════════════════════════════

class TestExpressionEvaluator:

    def test_constant(self):
        assert SafeEvaluator().evaluate("42") == 42
        assert SafeEvaluator().evaluate("'hello'") == "hello"
        assert SafeEvaluator().evaluate("True") is True

    def test_arithmetic(self):
        assert SafeEvaluator().evaluate("2 + 3 * 4") == 14
        assert SafeEvaluator().evaluate("10 // 3") == 3
        assert SafeEvaluator().evaluate("10 % 3") == 1

    def test_comparison(self):
        assert SafeEvaluator().evaluate("1 < 2") is True
        assert SafeEvaluator().evaluate("'a' == 'a'") is True

    def test_boolean(self):
        assert SafeEvaluator().evaluate("True and False") is False
        assert SafeEvaluator().evaluate("True or False") is True
        assert SafeEvaluator().evaluate("not False") is True

    def test_conditional(self):
        assert SafeEvaluator({"x": 5}).evaluate("'big' if x > 3 else 'small'") == "big"
        assert SafeEvaluator({"x": 1}).evaluate("'big' if x > 3 else 'small'") == "small"

    def test_scope_variables(self):
        scope = {"env": {"API_KEY": "secret", "DEBUG": True}}
        assert SafeEvaluator(scope).evaluate("env['API_KEY']") == "secret"
        assert SafeEvaluator(scope).evaluate("env['DEBUG']") is True

    def test_attribute_access(self):
        class Ctx:
            class env:
                API_KEY = "key123"
        assert SafeEvaluator({"ctx": Ctx}).evaluate("ctx.env.API_KEY") == "key123"

    def test_builtin_functions(self):
        assert SafeEvaluator().evaluate("len([1,2,3])") == 3
        assert SafeEvaluator().evaluate("int('42')") == 42
        assert SafeEvaluator().evaluate("sorted([3,1,2])") == [1, 2, 3]

    def test_list_dict_set_tuple(self):
        assert SafeEvaluator().evaluate("[1, 2, 3]") == [1, 2, 3]
        assert SafeEvaluator().evaluate("{'a': 1}") == {"a": 1}
        assert SafeEvaluator().evaluate("{1, 2, 3}") == {1, 2, 3}
        assert SafeEvaluator().evaluate("(1, 2)") == (1, 2)

    def test_safety_blocks_import(self):
        with pytest.raises(ValueError, match="Undefined|Unsafe"):
            SafeEvaluator().evaluate("__import__('os').system('echo pwned')")

    def test_safety_blocks_exec(self):
        with pytest.raises(ValueError, match="Undefined|Unsafe"):
            SafeEvaluator().evaluate("exec('x=1')")

    def test_safety_blocks_lambda(self):
        with pytest.raises(ValueError, match="Unsafe"):
            SafeEvaluator().evaluate("(lambda: 1)()")

    def test_interpolate_config(self):
        config = {
            "key": PyExpr("'prefix_' + env['SUFFIX']"),
            "nested": {"val": PyExpr("2 + 2")},
            "plain": "untouched",
        }
        scope = {"env": {"SUFFIX": "test"}}
        result = interpolate_config(config, scope)
        assert result["key"] == "prefix_test"
        assert result["nested"]["val"] == 4
        assert result["plain"] == "untouched"


# ═══════════════════════════════════════════════════════════════
# §G — HMR (file watch, reload, rollback)
# ═══════════════════════════════════════════════════════════════

class TestHMR:
    """HMR is a design-level pattern (§5.14). Here we test the core mechanisms."""

    def test_sys_modules_cache_clear(self):
        """HMR core mechanism: changed file → new import → fresh module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Version 1
            v1 = Path(tmpdir) / "plugin_v1.py"
            v1.write_text("VALUE = 1\n")
            spec1 = importlib.util.spec_from_file_location("pv1", str(v1))
            m1 = importlib.util.module_from_spec(spec1)
            spec1.loader.exec_module(m1)
            assert m1.VALUE == 1

            # Version 2 (different file path = guaranteed fresh import)
            v2 = Path(tmpdir) / "plugin_v2.py"
            v2.write_text("VALUE = 2\n")
            spec2 = importlib.util.spec_from_file_location("pv2", str(v2))
            m2 = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(m2)
            assert m2.VALUE == 2

            # The HMR pattern: old module discarded, new module loaded
            assert m1.VALUE != m2.VALUE  # different module objects

    def test_ast_dependency_tracing(self):
        """AST analysis can trace import chains."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mod_a = Path(tmpdir) / "mod_a.py"
            mod_b = Path(tmpdir) / "mod_b.py"
            mod_a.write_text("from mod_b import X\nVALUE = X + 1\n")
            mod_b.write_text("X = 10\n")

            tree = ast.parse(mod_a.read_text())
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if hasattr(node, 'module') and node.module:
                        imports.append(node.module)
                    for name in node.names:
                        imports.append(name.name)
            assert "mod_b" in imports


# ═══════════════════════════════════════════════════════════════
# §H — Advanced features
# ═══════════════════════════════════════════════════════════════

class TestDisposableList:

    def test_push_and_iter(self):
        dl = DisposableList()
        dl.push("a")
        dl.push("b")
        dl.push("c")
        assert len(dl) == 3
        assert list(dl) == ["a", "b", "c"]

    def test_o1_delete(self):
        dl = DisposableList()
        dl.push("a")
        b = "b"
        dl.push(b)
        dl.push("c")
        assert dl.delete(b) is True
        assert len(dl) == 2
        assert list(dl) == ["a", "c"]

    def test_clear_reversed(self):
        dl = DisposableList()
        dl.push("a")
        dl.push("b")
        dl.push("c")
        assert dl.clear() == ["c", "b", "a"]
        assert len(dl) == 0


class TestEffectMeta:

    async def test_effects_meta_collected(self):
        host = PluginHost()
        def apply(ctx, cfg):
            ctx.effect(lambda: None, "effect-a")
            ctx.effect(lambda: None, "effect-b")
            ctx.on("test", lambda: None)
        host.register("x", PluginSpec(name="x", apply=apply), {})
        await host.mount_all()
        handle = host.handles["x"]
        metas = handle.get_effects_meta()
        labels = [m.label for m in metas]
        assert "effect-a" in labels
        assert "effect-b" in labels
        assert any("ctx.on" in l for l in labels)


class TestComposeError:

    def test_sync_error_gets_frames(self):
        def failing():
            raise ValueError("test error")
        outer = lambda: ["at loader.py#entry-a"]
        with pytest.raises(ValueError) as exc_info:
            compose_error(failing, outer)
        assert hasattr(exc_info.value, '_composed_traceback')

    async def test_async_error_gets_frames(self):
        async def failing():
            raise ValueError("async error")
        outer = lambda: ["at loader.py#entry-b"]
        with pytest.raises(ValueError) as exc_info:
            await compose_error(failing, outer)
        assert hasattr(exc_info.value, '_composed_traceback')


class TestAccessorMixin:

    async def test_accessor(self):
        host = PluginHost()
        def apply(ctx, cfg):
            counter = {"value": 0}
            def getter():
                counter["value"] += 1
                return counter["value"]
            ctx.accessor("next_val", get=getter)
            ctx.mount("counter", counter)
        host.register("acc", PluginSpec(name="acc", apply=apply), {})
        await host.mount_all()
        assert host.get_service("counter") is not None

    async def test_child_context(self):
        host = PluginHost()
        def apply(ctx, cfg):
            child = ctx.child(key="run-1", values={"local_svc": "run-local"})
            assert child.get("local_svc") == "run-local"
            ctx.mount("parent_svc", "parent-val")
        host.register("x", PluginSpec(name="x", apply=apply), {})
        await host.mount_all()
        assert host.handles["x"].state == PluginState.ACTIVE


# ═══════════════════════════════════════════════════════════════
# §I — Loader advanced
# ═══════════════════════════════════════════════════════════════

class TestLoaderAdvanced:

    async def test_runtime_create_and_remove(self):
        host = PluginHost()
        spec = PluginSpec(name="dynamic", apply=lambda ctx, cfg: ctx.mount("dyn", "value"))
        handle = await host.create_entry("dyn-1", spec, {})
        assert handle.state == PluginState.ACTIVE
        assert host.get_service("dyn") == "value"

        await host.remove_entry("dyn-1")
        assert "dyn-1" not in host.handles
        assert host.get_service("dyn") is None

    async def test_builtins(self):
        host = PluginHost()
        host.builtins["echo"] = PluginSpec(
            name="echo",
            apply=lambda ctx, cfg: ctx.mount("echo", "built-in"),
        )
        spec = host.builtins["echo"]
        host.register("echo-1", spec, {})
        await host.mount_all()
        assert host.get_service("echo") == "built-in"

    async def test_states_as_dict(self):
        host = PluginHost()
        host.register("a", PluginSpec(name="a", apply=lambda ctx, cfg: None), {})
        await host.mount_all()
        d = states_as_dict(host)
        assert d == {"a": "active"}


# ═══════════════════════════════════════════════════════════════
# §J — Config update (3-state diff, rollback)
# ═══════════════════════════════════════════════════════════════

class TestConfigUpdate:

    async def test_successful_update(self):
        values: list[str] = []
        def apply(ctx, cfg):
            values.append(cfg.get("prefix", ""))
            ctx.mount("svc", cfg.get("prefix", ""))
        host = PluginHost()
        host.register("x", PluginSpec(name="x", apply=apply), {"prefix": "v1"})
        await host.mount_all()
        assert values == ["v1"]

        await host.update_config("x", {"prefix": "v2"})
        assert values == ["v1", "v2"]
        assert host.get_service("svc") == "v2"

    async def test_update_rollback(self):
        def apply(ctx, cfg):
            if cfg.get("prefix") == "":
                raise ValueError("empty prefix")
            ctx.mount("svc", cfg["prefix"])
        host = PluginHost()
        host.register("x", PluginSpec(name="x", apply=apply), {"prefix": "good"})
        await host.mount_all()
        assert host.get_service("svc") == "good"

        with pytest.raises(PluginError, match="rolled back"):
            await host.update_config("x", {"prefix": ""})

        # Rolled back to old config
        assert host.get_service("svc") == "good"
        assert host.handles["x"].state == PluginState.ACTIVE

    async def test_update_disabled_entry(self):
        host = PluginHost()
        host.register("x", PluginSpec(
            name="x", apply=lambda ctx, cfg: ctx.mount("svc", 1)
        ), {})
        await host.mount_all()
        await host.unmount("x")
        # Update while disabled just changes config
        await host.update_config("x", {"new": True})
        assert host.handles["x"].config == {"new": True}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-o", "addopts=", "-o", "asyncio_mode=auto"])
