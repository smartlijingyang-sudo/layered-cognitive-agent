"""SessionCheckpointPolicy —— DSH session-checkpoint-policy 的 LCA capability 形态。

对齐 deepseek-harness ``packages/session/session-checkpoint-policy`` 的三个
fail-closed durability checkpoint 边界(``docs/specs/session-event-pipeline-spec.md``
§5 的 ★ 检查点):

- **模型请求边界**(DSH ``llm/stream``):adapter 流构造前先让已提交请求前缀
  durable → :meth:`SessionCheckpointPolicy.before_model_request`;
- **顶层工具副作用边界**(DSH ``tools/execute``):工具体执行前先让记录的
  调用 durable → :meth:`SessionCheckpointPolicy.before_tool_side_effect`;
- **步边界**(DSH ``agent/pre-step``):下一步请求派生前,上一步已提交的
  响应/工具结果批次先排空 → :meth:`SessionCheckpointPolicy.at_step_boundary`。

三个入口共享语义:先 ``await session.flush()``(Session 的唯一 durability
barrier 入口),检查返回的 :class:`FlushResult` 列表 —— 任一 ``ok=False``
抛 :class:`CheckpointFailure`(fail-closed:下游不得执行);全部 ok → 放行。

设计要点:

- **被动调用面**:DSH 用 cordis 事件钩子(``ctx.on``)拦截 waterfall 链;
  LCA 以 plugin capability(``session.checkpoint.policy``)提供,由调用方
  主动 await 三入口。策略不主动订阅事件、不注册 FlushListener、无可变状态。
- **duck-type 入参**::class:`FlushableSession` 只要求
  ``async flush() -> Sequence[FlushResult]``;不 import runtime 实现类,
  fake 可测、真 Session 可调。
- **顶层性/取消语义归调用方**:DSH ``tools/execute`` 钩子按 ``exec.parent``
  区分顶层/嵌套(嵌套复用外层已 durable 的调用),并在 flush 后按
  ``exec.signal`` 落 ``ABORTED_BEFORE_DISPATCH``;LCA 由融合阶段执行侧判定
  顶层性与取消,本策略只提供 barrier 本身。

接线点 —— 模型请求边界 ``lca/cognition/brain/llm_turn/executor.py``、工具
副作用边界 ``lca/cognition/body/safe_executor.py`` —— 属后续融合阶段;
本插件只提供 capability 面,本次变更不修改这两个文件。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.session.persistence_service import CheckpointFailure
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.events.session import FlushResult

__all__ = ["Config", "FlushableSession", "SessionCheckpointPolicy", "setup"]


@runtime_checkable
class FlushableSession(Protocol):
    """checkpoint 调用目标的最小 duck-type 面。

    只要求 ``flush()`` 返回 per-listener :class:`FlushResult` 列表;刻意不
    绑定完整 ``SessionProtocol``,策略与 Session 实现侧解耦(真
    :class:`Session` 与测试 fake 均可满足)。
    """

    async def flush(self) -> Sequence[FlushResult]: ...


class Config(BaseModel):
    """plugin 配置:checkpoint 策略开关;拒绝未知键。

    DSH 原版零配置;``enabled`` 是 LCA 扩展 —— ``False`` 用于"有意替换
    checkpoint 调度"的部署,三入口降级为 no-op 放行。
    """

    model_config = {"extra": "forbid"}

    enabled: bool = True
    """是否执行 durability barrier;``False`` → 三入口直接放行(不触发 flush)。"""


class SessionCheckpointPolicy:
    """三边界 durability checkpoint 策略(无状态,fail-closed)。

    三入口共享同一 barrier 形态:await flush → 检查结果 → 放行/抛。策略
    自身不写 Session、不发事件、不订阅;唯一副作用是经 ``session.flush()``
    触发的落盘(对应 manifest ``effects="filesystem"``)。
    """

    def __init__(self, *, enabled: bool = True) -> None:
        """构造策略。``enabled=False`` → 三入口全部 no-op 放行(不触发 flush)。"""
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        """是否执行 checkpoint barrier(只读诊断面)。"""
        return self._enabled

    async def before_model_request(self, session: FlushableSession) -> None:
        """模型请求边界(DSH ``llm/stream``):adapter 流构造前做检查点。

        放行后已提交请求前缀已 durable —— 响应前崩溃不会丢请求;
        :class:`CheckpointFailure` 表示调用方不得发出本次模型请求。
        """
        await self._checkpoint(session, boundary="llm/stream")

    async def before_tool_side_effect(self, session: FlushableSession) -> None:
        """顶层工具副作用边界(DSH ``tools/execute``):工具体执行前做检查点。

        放行后记录的调用已 durable —— 副作用前崩溃留下可匹配的调用记录;
        :class:`CheckpointFailure` 表示调用方不得进入工具体。嵌套工具派发
        不应调本入口(复用外层检查点,由融合阶段执行侧判定)。
        """
        await self._checkpoint(session, boundary="tools/execute")

    async def at_step_boundary(self, session: FlushableSession) -> None:
        """步边界(DSH ``agent/pre-step``):下一步请求前排空上一步已提交批次。

        放行后上一步的响应与有序工具结果已 durable;
        :class:`CheckpointFailure` 表示回合应在发起下一请求前失败。
        """
        await self._checkpoint(session, boundary="agent/pre-step")

    async def _checkpoint(self, session: FlushableSession, *, boundary: str) -> None:
        """共享的 fail-closed barrier:flush → 检查 FlushResult → 放行或抛。

        失败语义:

        - ``enabled=False`` → 直接放行(不触发 flush);
        - ``session.flush()`` 自身抛错 → 包装为 :class:`CheckpointFailure`
          (``__cause__`` 持原异常);
        - 返回列表任一 ``ok=False`` → :class:`CheckpointFailure`(message 带
          boundary、session id 与首个失败 listener 及其错误);
        - 空列表(未注册任何 flush listener/observer)→ 放行,无可检查点。
        """
        if not self._enabled:
            return
        session_id = getattr(session, "id", None)
        try:
            results = await session.flush()
        except Exception as exc:
            msg = f"checkpoint {boundary}: session={session_id!r} flush raised: {exc!r}"
            raise CheckpointFailure(msg) from exc
        failure = next((result for result in results if not result.ok), None)
        if failure is not None:
            listener = type(failure.listener).__name__
            msg = (
                f"checkpoint {boundary}: session={session_id!r} flush not durable "
                f"(listener={listener}, error={failure.error!r})"
            )
            raise CheckpointFailure(msg)


# ── plugin manifest ────────────────────────────────────────────────────


@plugin(
    id="lca.plugins.session.checkpoint_policy",
    provides=["session.checkpoint.policy"],
    requires=["session.store"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="filesystem",
    description=(
        "SessionCheckpointPolicy(DSH session-checkpoint-policy 的 LCA 形态):模型请求前 /"
        " 顶层工具副作用前 / 步边界三个 fail-closed durability 检查点;先 await"
        " session.flush(),任一 FlushResult(ok=False) 抛 CheckpointFailure(下游不得执行),"
        "全部 ok 放行。被动调用面,不订阅事件。提供 session.checkpoint.policy capability。"
    ),
    test_suite="tests/plugins/session/test_checkpoint_policy.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.store",),
        emits=(),
        state_mutation="reducer-only",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """checkpoint 策略 plugin boot:构造策略并提供 capability。

    行为契约:构造一个 :class:`SessionCheckpointPolicy`(按 ``config.enabled``),
    以 ``session.checkpoint.policy`` capability 提供。策略是被动调用面 ——
    不订阅事件、不向 ``session.store`` 的活 Session 注册 FlushListener;
    ``requires=["session.store"]`` 只约束激活序(检查点调用发生在 Session
    存在之后)。

    失败语义:构造无 I/O;session.store 未装载时本插件仍提供 capability
    (调用方自行等待装载)。
    """
    policy = SessionCheckpointPolicy(enabled=config.enabled)
    ctx.provide("session.checkpoint.policy", policy)
