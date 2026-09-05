"""SessionCheckpointPolicy plugin 测试(DSH session-checkpoint-policy LCA 形态)。

覆盖契约:

- flush 全 ok → 三个入口都放行不抛(空结果列表亦放行)
- FlushResult(ok=False) → 三个入口各抛 CheckpointFailure(fail-closed)
- session.flush 自身抛异常 → CheckpointFailure 包装(__cause__ 持原异常)
- enabled=False → no-op 放行,不触发 flush(LCA 扩展)
- plugin 装配:setup 提供 session.checkpoint.policy capability;manifest 元数据
- 端到端:真 SessionStore + 总是失败的 FlushListener → before_model_request
  抛 CheckpointFailure
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from lca.contracts.protocols.session.persistence_service import CheckpointFailure
from lca.plugins.session.checkpoint_policy.checkpoint_policy import (
    Config,
    FlushableSession,
    SessionCheckpointPolicy,
    setup,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.session import FlushResult

_ENTRY_POINTS = ("before_model_request", "before_tool_side_effect", "at_step_boundary")
"""三个 fail-closed 边界(DSH llm/stream、tools/execute、agent/pre-step)。"""


# ── helpers ─────────────────────────────────────────────────────────


class _StubListener:
    """FlushResult.listener 占位对象(策略只读 ok/error,不回调)。"""

    async def flush(self, session: Any) -> None:
        return None


class _FakeFlushSession:
    """duck-type session:``.flush()`` 返回预置结果列表或抛异常。"""

    def __init__(
        self,
        results: list[FlushResult] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._results = list(results) if results is not None else []
        self._exc = exc
        self.id = "fake-session"
        self.flush_calls = 0

    async def flush(self) -> list[FlushResult]:
        self.flush_calls += 1
        if self._exc is not None:
            raise self._exc
        return list(self._results)


def _ok_result() -> FlushResult:
    return FlushResult(listener=_StubListener(), ok=True, event_count=1)


def _failed_result(exc: Exception) -> FlushResult:
    return FlushResult(listener=_StubListener(), ok=False, event_count=1, error=exc)


def _fake_ctx() -> Any:
    """最小 stub PluginContext:provide + soft_get。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            return None

    return _Ctx()


# ── 三边界:放行 / fail-closed ───────────────────────────────────────


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_all_results_ok_passes(entry_point: str) -> None:
    session = _FakeFlushSession(results=[_ok_result(), _ok_result()])
    policy = SessionCheckpointPolicy()

    await getattr(policy, entry_point)(session)

    assert session.flush_calls == 1


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_empty_flush_results_pass(entry_point: str) -> None:
    """无 flush listener/observer → 空结果列表 → 放行(无可检查点)。"""
    session = _FakeFlushSession(results=[])
    policy = SessionCheckpointPolicy()

    await getattr(policy, entry_point)(session)

    assert session.flush_calls == 1


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_failed_result_raises_checkpoint_failure(entry_point: str) -> None:
    session = _FakeFlushSession(results=[_ok_result(), _failed_result(OSError("disk full"))])
    policy = SessionCheckpointPolicy()

    with pytest.raises(CheckpointFailure, match="disk full"):
        await getattr(policy, entry_point)(session)


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_flush_exception_wrapped_in_checkpoint_failure(entry_point: str) -> None:
    boom = ConnectionError("sink gone")
    session = _FakeFlushSession(exc=boom)
    policy = SessionCheckpointPolicy()

    with pytest.raises(CheckpointFailure) as excinfo:
        await getattr(policy, entry_point)(session)

    assert excinfo.value.__cause__ is boom


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_disabled_policy_skips_flush(entry_point: str) -> None:
    """enabled=False(LCA 扩展)→ no-op 放行,不触发 flush。"""
    session = _FakeFlushSession(exc=RuntimeError("must not flush"))
    policy = SessionCheckpointPolicy(enabled=False)

    await getattr(policy, entry_point)(session)

    assert session.flush_calls == 0


def test_fake_session_satisfies_flushable_duck_type() -> None:
    """duck-type 契约:只需 ``.flush()`` 返回 FlushResult 列表即可满足。"""
    assert isinstance(_FakeFlushSession(), FlushableSession)


# ── plugin 装配 ────────────────────────────────────────────────────


async def test_setup_provides_capability() -> None:
    ctx = _fake_ctx()

    # setup is wrapped by @plugin into a cordis.Plugin carrier; .setup is the
    # original async function (mirrors tests/plugins/session/test_persistence_jsonl.py).
    await setup.setup(ctx, Config())

    assert "session.checkpoint.policy" in ctx.provided
    policy = ctx.provided["session.checkpoint.policy"]
    assert isinstance(policy, SessionCheckpointPolicy)
    assert policy.enabled is True


async def test_setup_disabled_config_yields_noop_policy() -> None:
    ctx = _fake_ctx()

    await setup.setup(ctx, Config(enabled=False))

    policy = ctx.provided["session.checkpoint.policy"]
    assert policy.enabled is False


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Config(unknown_field=True)


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.session.checkpoint_policy import checkpoint_policy as plugin_module

    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.checkpoint_policy"
    assert definition.spec.layer == "L2"
    assert "session.checkpoint.policy" in definition.provided_capability_keys
    assert "session.store" in definition.required_capability_keys
    effects = definition.spec.effects
    effects_value = (
        tuple(e.value if hasattr(e, "value") else str(e) for e in effects)
        if isinstance(effects, (list, tuple))
        else (effects.value if hasattr(effects, "value") else str(effects),)
    )
    assert "filesystem" in effects_value


# ── 端到端:真 Session + FlushListener ──────────────────────────────


class _AlwaysFailListener:
    """总是失败的 FlushListener:模拟持久化后端排空失败。"""

    async def flush(self, session: Any) -> None:
        raise OSError("disk full")


class _RecordingListener:
    """健康 FlushListener:记录 flush 调用次数。"""

    def __init__(self) -> None:
        self.calls = 0

    async def flush(self, session: Any) -> None:
        self.calls += 1


async def test_end_to_end_failing_listener_blocks_model_request() -> None:
    """端到端:真 Session 的 flush 链报 ok=False → CheckpointFailure(fail-closed)。"""
    store = SessionStore()
    session = store.create("s-e2e-fail")
    session.append("spine.turn.started", {"turn": 1})
    session.register_flush_listener(_AlwaysFailListener())
    policy = SessionCheckpointPolicy()

    with pytest.raises(CheckpointFailure, match="disk full"):
        await policy.before_model_request(session)


async def test_end_to_end_healthy_listener_passes_all_boundaries() -> None:
    """端到端:健康 flush 链 → 三入口全部放行,每个边界恰好一次 flush。"""
    store = SessionStore()
    session = store.create("s-e2e-ok")
    listener = _RecordingListener()
    session.register_flush_listener(listener)
    policy = SessionCheckpointPolicy()

    await policy.before_model_request(session)
    await policy.before_tool_side_effect(session)
    await policy.at_step_boundary(session)

    assert listener.calls == 3
