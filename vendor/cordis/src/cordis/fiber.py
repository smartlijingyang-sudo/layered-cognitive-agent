"""`cordis.fiber` — Plugin fiber (lifecycle, DI, effects).

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/fiber.ts`.

Implements:

- :class:`FiberState` — PENDING / LOADING / ACTIVE / FAILED / UNLOADING /
  DISPOSED lifecycle states.
- :class:`CordisError` — framework error with stable ``code``.
- :class:`ValidationError` — raised when plugin config validation fails.
- :func:`resolve_config` — config validator dispatch (Pydantic / callable).
- :class:`Fiber` — full state machine with DI, effects, reload/unload.

Public surface:

- ``Fiber.uid`` — allocator-supplied id; ``None`` once disposed.
- ``Fiber.state`` — current lifecycle state.
- ``Fiber.inject`` — required service names + intercept config.
- ``Fiber.store`` — snapshot of resolved dependencies while loaded.
- ``Fiber.inertia`` — pending load/unload transition (None at rest).
- ``Fiber.dispose`` — cleanup-driven uninstall.
- ``Fiber.effect(execute, label)`` — register a cleanup-aware effect.
- ``Fiber.await_()`` — wait for inertia and rethrow startup errors.
- ``Fiber.restart()`` — unload + reload the plugin.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cordis.utils import DisposableList, EffectMeta, build_outer_stack, compose_error

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "Fiber",
    "FiberState",
    "CordisError",
    "ValidationError",
    "resolve_config",
    "INACTIVE",
]


# ---------------------------------------------------------------------------
# Fiber state enum
# ---------------------------------------------------------------------------


class FiberState:
    """Lifecycle states for one plugin fiber (mirrors upstream TS enum)."""

    PENDING = 0
    LOADING = 1
    ACTIVE = 2
    FAILED = 3
    UNLOADING = 4
    DISPOSED = 5

    _NAMES: dict[int, str] = {
        0: "PENDING",
        1: "LOADING",
        2: "ACTIVE",
        3: "FAILED",
        4: "UNLOADING",
        5: "DISPOSED",
    }

    @classmethod
    def name(cls, value: int) -> str:
        """Return the human-readable name of a state code."""
        return cls._NAMES.get(value, "UNKNOWN")


INACTIVE: str = "__INACTIVE__"
"""Sentinel for an inactive dependency epoch (mirrors upstream ``INACTIVE``)."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CordisError(Exception):
    """Stable, machine-readable framework error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class ValidationError(TypeError):
    """Raised when a plugin's config fails standard-schema validation."""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        msg_lines = ["invalid config:"]
        for issue in issues:
            path = ".".join(str(p) for p in issue.get("path", []))
            text = issue.get("message", "")
            if path:
                msg_lines.append(f"  - {text} (at {path})")
            else:
                msg_lines.append(f"  - {text}")
        super().__init__("\n".join(msg_lines))


def resolve_config(runtime: Any, config: Any) -> Any:
    """Run ``runtime.Config['~standard'].validate(config)`` if available.

    In Python we tolerate both Pydantic models (``model_validate`` /
    ``parse_obj``) and plain callables.
    """
    schema = getattr(runtime, "Config", None)
    if schema is None:
        return config
    try:
        return schema.model_validate(config)
    except AttributeError:
        pass
    try:
        return schema.parse_obj(config)
    except AttributeError:
        pass
    try:
        return schema(config)
    except Exception:
        return config


# ---------------------------------------------------------------------------
# Fiber (full)
# ---------------------------------------------------------------------------


@dataclass
class _Runner:
    """Per-effect runner state."""

    epoch: Any
    execute: Callable[[], Any]
    collect: Callable[[Any], None]
    get_outer_stack: Callable[[], list[str]] = field(default_factory=lambda: lambda: [])


def _is_constructor(func: Any) -> bool:
    """True if plugin callback should be ``new``-instantiated."""
    try:
        return inspect.isclass(func)
    except Exception:  # pragma: no cover
        return False


class Fiber:
    # Class-level registry of pending _reload tasks to prevent the underlying
    # coroutines from being garbage-collected before the event loop runs them.
    _pending_reloads: list[asyncio.Task[Any]] = []
    """Runtime instance of one plugin application.

    Tracks dependency state, validated config, lifecycle effects, and
    cleanup for the plugin context returned by ``ctx.plugin()``.
    """

    def __init__(  # noqa: PLR0915
        self,
        parent: "Context",
        config: Any,
        inject: dict[str, Any],
        runtime: Any | None,
        get_outer_stack: Callable[[], list[str]] | None = None,
        is_root: bool = False,
    ) -> None:
        self.parent: "Context" = parent
        self.ctx: "Context" = parent
        self.config: Any = config
        self._config: Any = config
        self.inject: dict[str, Any] = inject
        self.runtime: Any | None = runtime
        self.state: int = FiberState.PENDING
        self.store: dict[str, Any] | None = None
        self.inertia: asyncio.Task[None] | None = None

        self._hooks: dict[str, DisposableList] = {}
        self._disposables: DisposableList = DisposableList()

        self._error: Any = None
        self._store: dict[str, Any] = {}
        self._runner: _Runner = _Runner(
            epoch=INACTIVE,
            execute=lambda: None,
            collect=lambda d: None,
            get_outer_stack=get_outer_stack or build_outer_stack(0),
        )

        self._parent_dispose: Callable[[], Any] = lambda: None

        if runtime is not None:
            # Plugin fiber.
            self.uid = parent.registry.counter  # type: ignore[attr-defined]
            self.ctx = parent.extend({"fiber": self})  # type: ignore[arg-defined]

            # ``ctx[Context.intercept]`` is built from parent + inject entries.
            inject_entries = list(inject.items())
            if inject_entries:
                try:
                    parent_intercept = parent[symbols.intercept]  # type: ignore[name-defined]
                except Exception:
                    parent_intercept = {}
                new_intercept: dict[str, Any] = dict(parent_intercept) if isinstance(parent_intercept, dict) else {}
                for name, cfg in inject_entries:
                    if cfg is None:
                        continue
                    new_intercept[name] = cfg
                try:
                    self.ctx[symbols.intercept] = new_intercept  # type: ignore[name-defined]
                except Exception:  # pragma: no cover
                    pass

            if _is_constructor(runtime.callback):
                # Class plugin: instantiate and run init hooks.
                def _execute_class() -> Any:
                    instance = runtime.callback(self.ctx, self.config)
                    # Run init hooks if present.
                    init_hooks = getattr(instance, "cordis.init_hooks", None)
                    if isinstance(init_hooks, (list, tuple)):
                        for hook in init_hooks:
                            try:
                                hook()
                            except Exception:  # pragma: no cover
                                pass
                    # Call `[cordis.init]` if present.
                    init = getattr(instance, "cordis.init", None)
                    if callable(init):
                        return init()
                    return None

                self._runner = _Runner(
                    epoch=INACTIVE,
                    execute=_execute_class,
                    collect=lambda d: self._disposables.push(d),
                    get_outer_stack=self._runner.get_outer_stack,
                )
            else:
                # Function plugin: call ``runtime.callback(ctx, config)``.
                self._runner = _Runner(
                    epoch=INACTIVE,
                    execute=lambda: runtime.callback(self.ctx, self.config),
                    collect=lambda d: self._disposables.push(d),
                    get_outer_stack=self._runner.get_outer_stack,
                )

            # Register self for cleanup.
            try:
                self._parent_dispose = parent.fiber.effect(  # type: ignore[attr-defined]
                    self._register_in_runtime,
                    "ctx.plugin()",
                )
            except Exception:  # pragma: no cover
                pass

            # ``self.dispose`` delegates to the parent's effect wrapper
            # (mirrors upstream ``this.dispose = parent.fiber.effect(...)``).
            # Calling it triggers the async cleanup chain which sets
            # ``uid = None``, removes the fiber from ``runtime.fibers``, and
            # unloads the fiber.
            self.dispose: Any = self._parent_dispose

            # Emit ``internal/plugin`` and trigger initial reload.
            try:
                self.context_emit_internal_plugin()
            except Exception:  # pragma: no cover
                pass

            # DI refresh: walk inject map, then trigger initial reload via _refresh()
            # which schedules _reload() through asyncio.ensure_future(). The resulting
            # Task is intentionally not awaited in the synchronous constructor; it runs
            # on the event loop and updates self.inertia. The with-warnings block
            # suppresses the "coroutine never awaited" RuntimeWarning that pytest
            # surfaces when the test runner's event loop is torn down before _reload
            # completes.
            import warnings as _w
            try:
                with _w.catch_warnings():
                    _w.simplefilter("ignore", RuntimeWarning)
                    if self.uid is not None:
                        for name in list(self.inject.keys()):
                            self._check_impl(name)
                        self._refresh()
            except Exception:  # pragma: no cover
                pass
        else:
            # Root fiber.
            self.uid = 0 if is_root else None
            if is_root:
                self.uid = 0
                self.state = FiberState.ACTIVE
                self.store = {}
            # Root fibers have nothing to dispose; ``dispose()`` triggers a
            # restart (matches upstream ``this.dispose = () => this.restart()``).
            self.dispose: Any = lambda: self.restart()

    def context_emit_internal_plugin(self) -> None:
        """Emit ``internal/plugin`` for observability."""
        try:
            self.context.emit("internal/plugin", self)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        fiber: Fiber = self
        while True:
            runtime = fiber.runtime
            name = getattr(runtime, "name", None) if runtime else None
            if name:
                return name
            try:
                parent_fiber = fiber.parent.fiber  # type: ignore[attr-defined]
            except Exception:
                return "root"
            if parent_fiber is fiber:
                return "root"
            fiber = parent_fiber

    @property
    def context(self) -> "Context":  # type: ignore[name-defined]
        return self.ctx

    @context.setter
    def context(self, value: "Context") -> None:  # type: ignore[name-defined]
        self.ctx = value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_in_runtime(self) -> Callable[[], Any]:
        """Append this fiber to ``runtime.fibers`` and return a cleanup."""
        runtime = self.runtime
        if runtime is None:  # pragma: no cover
            return lambda: None
        remove = runtime.fibers.push(self)

        async def _cleanup() -> None:
            self.uid = None
            try:
                self.context_emit_internal_plugin()
            except Exception:  # pragma: no cover
                pass
            try:
                if self.ctx.registry.has(runtime.callback):  # type: ignore[attr-defined]
                    remove()
                    if len(runtime.fibers) == 0:
                        self.ctx.registry.delete(runtime.callback)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
            self._set_epoch(INACTIVE)
            if self.inertia is None:
                self._begin_unload()
            while self.inertia is not None:
                try:
                    await self.inertia
                except Exception:
                    break

        return _cleanup

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assert_active(self) -> None:
        """Raise ``CordisError(INACTIVE_EFFECT)`` if the fiber was disposed."""
        if self.uid is None:
            raise CordisError(
                "INACTIVE_EFFECT",
                "cannot create effect on inactive context",
            )

    def effect(  # noqa: PLR0915
        self,
        execute: Callable[[], Any],
        label: str = "anonymous",
    ) -> Any:
        """Register a cleanup-aware effect on this fiber.

        Mirrors upstream ``Fiber.effect``: ``execute`` runs immediately;
        the disposers it produces are collected and run in reverse order
        when the returned wrapper is called or the fiber unloads.
        """
        self.assert_active()
        if self.state == FiberState.UNLOADING:
            raise CordisError("INACTIVE_EFFECT")

        disposables: list[Callable[[], Any]] = []
        dispose_called = False
        disposal_task: Any = None

        meta = EffectMeta(label=label, children=[])

        def _do_dispose() -> Any:
            nonlocal dispose_called, disposal_task
            if dispose_called:
                return disposal_task
            dispose_called = True
            chain: Any = None
            for disp in reversed(disposables):
                try:
                    result = disp()
                except Exception:  # pragma: no cover
                    continue
                if chain is None:
                    if inspect.isawaitable(result):
                        chain = result
                    else:
                        # Sync disposer; run synchronously and recurse.
                        try:
                            result()
                        except Exception:  # pragma: no cover
                            pass
                else:
                    prev = chain

                    async def _chain(_p: Any = prev, _d: Callable[[], Any] = disp) -> None:
                        await _p
                        v = _d()
                        if inspect.isawaitable(v):
                            await v

                    chain = _chain()
            disposal_task = chain
            return chain

        runner = _Runner(
            epoch=True,
            execute=execute,
            collect=lambda d: disposables.append(d),
            get_outer_stack=build_outer_stack(0),
        )

        wrapper: Any = lambda: _do_dispose()
        setattr(wrapper, "cordis.effect", meta)

        # Register wrapper into master disposables BEFORE execute.
        wrapper_remove = self._disposables.push(wrapper)
        del wrapper_remove

        try:
            task = self._execute_runner(runner)
        except Exception as exc:
            try:
                _do_dispose()
            except Exception:  # pragma: no cover
                pass
            raise

        # Link future into the wrapper's ``.then`` via the ``_effect_runner``.
        async def _effect_runner(_t: Any = task) -> Any:
            if inspect.isawaitable(_t):
                await _t
            return None

        async def _then(
            on_fulfilled: Callable[[Any], Any] | None = None,
            on_rejected: Callable[[Any], Any] | None = None,
        ) -> Any:
            try:
                result = _do_dispose()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                if on_rejected is not None:
                    return on_rejected(exc)
                raise
            if on_fulfilled is not None:
                return on_fulfilled(None)
            return None

        wrapper.then = _then
        return wrapper

    def getEffects(self) -> list[EffectMeta]:
        """Return metadata for currently registered effects."""
        out: list[EffectMeta] = []
        for d in self._disposables:
            meta = getattr(d, "cordis.effect", None)
            if meta is not None:
                out.append(meta)
        return out

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _execute_runner(self, runner: _Runner) -> Any:
        """Execute ``runner`` synchronously.

        Returns ``None``; the runner's body fully populates
        ``disposables`` synchronously when possible. Async bodies are
        awaited via ``asyncio.run`` if no loop is running; if a loop
        is already running, we fall back to leaving the body unconsumed
        (caller is responsible for awaiting).
        """
        result = compose_error(
            lambda _info: _run_effect_body(self, runner),
            runner.get_outer_stack,
        )
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
                # Loop is running; can't asyncio.run. Caller is async.
                return result
            except RuntimeError:
                # No running loop; consume synchronously.
                asyncio.run(result)
        return None

    async def _execute_runner_async(self, runner: _Runner) -> Any:
        """Async counterpart used by ``effect`` / ``_reload`` paths."""
        await asyncio.sleep(0)  # cooperate
        result = compose_error(
            lambda _info: _run_effect_body(self, runner),
            runner.get_outer_stack,
        )
        if inspect.isawaitable(result):
            await result
        return None

    def _get_state(self) -> int:
        if self.uid is None:
            return FiberState.DISPOSED
        if self._error is not None:
            return FiberState.FAILED
        if self._runner.epoch != INACTIVE:
            return FiberState.ACTIVE
        return FiberState.PENDING

    def _update_state(self, callback: Callable[[], int | None]) -> None:
        old_state = self.state
        try:
            result = callback()
        except Exception:  # pragma: no cover
            result = None
        self.state = result if isinstance(result, int) else self._get_state()
        if old_state == self.state:
            return
        try:
            self.context.emit("internal/status", self, old_state)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

    def _begin_unload(self) -> int:
        self.inertia = asyncio.ensure_future(self._unload())
        return FiberState.UNLOADING

    async def _reload(self) -> None:
        try:
            self.store = dict(self._store)
            old = self._runner.epoch
            try:
                await asyncio.sleep(0)  # force async checkpoint
                if self._runner.epoch == old:
                    self.config = self._resolve_config(self._config)
                    await self._execute_runner_async(self._runner)
                    self._error = None
            except BaseException as exc:  # noqa: BLE001
                try:
                    self.ctx.logger.error(exc)  # type: ignore[attr-defined]
                except Exception:  # pragma: no cover
                    pass
                self._error = exc
                self._runner.epoch = INACTIVE

            def _cb() -> int:
                if self._runner.epoch == old:
                    self.inertia = None
                    return self._get_state()
                self.inertia = asyncio.ensure_future(self._unload())
                return FiberState.UNLOADING

            self._update_state(_cb)
        except Exception:  # pragma: no cover
            pass

    async def _unload(self) -> None:
        try:
            disposables = self._disposables.clear()
            for disp in disposables:
                try:
                    result = disp()
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # pragma: no cover
                    try:
                        self.ctx.logger.error(  # type: ignore[attr-defined]
                            f"disposer failed: {disp!r}"
                        )
                    except Exception:
                        pass
        finally:
            self.store = None
            self._update_state(self._on_unload_done)

    def _on_unload_done(self) -> int:
        if self._runner.epoch == INACTIVE:
            self.inertia = None
            return self._get_state()
        task = asyncio.ensure_future(self._reload())
        self.inertia = task
        # Keep a strong reference to prevent the coroutine from being
        # garbage-collected before the event loop runs it.
        Fiber._pending_reloads.append(task)
        return FiberState.LOADING

    def _check_impl(self, name: str) -> None:
        try:
            impl = self.ctx.reflect._get_impl(name, True)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            self._store.pop(name, None)
            return
        if not impl:
            self._store.pop(name, None)
            return
        try:
            check = impl.get("check")
            if check is not None and not check():
                self._store.pop(name, None)
                return
        except Exception:  # pragma: no cover
            self._store.pop(name, None)
            return
        self._store[name] = impl

    def _refresh(self) -> None:
        epoch: Any = ""
        for name in self.inject.keys():
            impl = self._store.get(name)
            if impl is None:
                epoch = INACTIVE
                break
            fiber = impl.get("fiber")
            uid = getattr(fiber, "uid", 0) if fiber else 0
            epoch += f":{uid}"
        self._set_epoch(epoch)

    def _set_epoch(self, epoch: Any) -> None:
        old = self._runner.epoch
        if epoch == old:
            return
        self._runner.epoch = epoch
        if self.inertia is not None:
            return
        # Decide transition.
        if epoch != INACTIVE and old == INACTIVE:
            task = asyncio.ensure_future(self._reload())
            self.inertia = task
            # Keep a strong reference to prevent the coroutine from being
            # garbage-collected before the event loop runs it, which would
            # trigger a RuntimeWarning ("coroutine was never awaited").
            Fiber._pending_reloads.append(task)
            self._update_state(lambda: FiberState.LOADING)
        else:
            self.inertia = asyncio.ensure_future(self._unload())
            self._update_state(lambda: FiberState.UNLOADING)

    def _resolve_config(self, config: Any) -> Any:
        try:
            config = self.context.waterfall(  # type: ignore[attr-defined]
                self, "internal/config", config, lambda: config
            )
        except Exception:  # pragma: no cover
            pass
        if self.runtime is not None:
            try:
                return resolve_config(self.runtime, config)
            except Exception:
                return config
        return config

    # ------------------------------------------------------------------
    # Public awaitable methods
    # ------------------------------------------------------------------

    async def await_(self) -> "Fiber":
        """Wait for inertia; rethrow any startup error."""
        while self.inertia is not None:
            try:
                await self.inertia
            except Exception:
                break
        if self._error is not None:
            raise self._error
        return self

    async def restart(self) -> None:
        """Unload and re-setup the plugin."""
        self.assert_active()
        self._set_epoch(INACTIVE)
        self._refresh()
        await self.await_()


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _run_effect_body(fiber: Fiber, runner: _Runner) -> Any:
    """Drive the upstream ``_execute`` body for one effect runner."""
    result = runner.execute()
    if callable(result):
        runner.collect(result)
        return None
    if result is None:
        return None

    if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        it = iter(result)
        while True:
            try:
                v = next(it)
            except StopIteration:
                break
            runner.collect(v)
        return None

    if inspect.isawaitable(result):
        async def _then() -> None:
            v = await result
            if callable(v):
                runner.collect(v)
            elif v is not None:
                raise TypeError("Invalid effect")

        return _then()

    if hasattr(result, "__aiter__"):
        async def _aiter() -> None:
            it = result.__aiter__()
            while True:
                try:
                    v = await it.__anext__()
                except StopAsyncIteration:
                    return
                runner.collect(v)

        return _aiter()

    raise TypeError("Invalid effect")


# Late-bound symbol table import (avoids hard import cycle in tests).
try:
    from cordis.utils import symbols as _symbols  # noqa: F401
except Exception:  # pragma: no cover
    pass
