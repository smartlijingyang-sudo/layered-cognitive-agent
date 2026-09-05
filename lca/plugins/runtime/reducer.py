"""DefaultReducer —— ADR-0066 的 boot-time 默认 Reducer 实现。

迁移期保留 mutable AgentState 的写法（与既有测试夹具兼容），但所有
mutation 集中在此模块；``CognitiveRuntime._loop`` 不再直接写 state。
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, ParamSpec, TypeVar, overload

from pydantic import BaseModel

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.models.core.terminal_outcome import (
    ErrorRef,
    ResumeCursor,
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import DeclarativeValidationError
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.contracts.observability.outcome import Outcome

_log = logging.getLogger(__name__)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _publish_apply_marker(
    *,
    method: str,
    phase: str,
    outcome: Outcome | None = None,
) -> None:
    """Publish one ``runtime.reducer.apply`` marker through the Session chain.

    Contract (ADR-0183 PR-8 / ADR-0186 PR-3d): reducer fold 是 AgentState C4
    单写边界,每次 fold 经 spine_reflector_runtime 的 emit helpers(内部
    ``publish_via_session`` → ``Session.append``)发一条
    ``runtime.reducer.apply`` marker,category 为
    ``spine.runtime.reducer.apply``(与 execution_point 一一绑定,由 plugin
    的 ``_SPINE_EP_TO_CATEGORY`` 派生)。

    producer 用 ``spine_reflector_runtime.plugin.ReflectorClass``:yaml SSOT
    (``lca_kernel/events/config/observability/spine.yaml``) 对该 category 只
    授权这一个 publish 身份;换独立身份需同步改 yaml 白名单。

    payload 字段 method/phase/outcome/run_id 与 ``journal_trace`` reader 的
    字段集对齐。``run_id`` 由 helper 按 thread active run
    (``set_active_run_id`` 注入)补齐,未注入时为空串。

    Failure:鉴权或 payload 校验失败抛 ``UnauthorizedPublishError`` /
    ``PayloadSchemaError``,不静默吞错。``MissingPublishSessionError``
    (run context 之外——boot / 测试未 bind Session)按装饰性 marker no-op:
    与 :class:`~lca.runtime.envelope_emitter.SpineEnvelopeEmitter` 及
    transport ``_safe_emit`` 的装饰性 emit 语义一致;fold 本体异常不受影响。
    """
    from lca.plugins.events.publishers.spine_reflector_runtime.plugin import (
        emit_runtime_reducer_apply_end,
        emit_runtime_reducer_apply_start,
    )
    from lca_kernel.events.errors import MissingPublishSessionError

    try:
        if phase == "start":
            emit_runtime_reducer_apply_start(method=method)
        else:
            if outcome is None:
                raise ValueError(f"phase='end' marker requires outcome: method={method}")
            emit_runtime_reducer_apply_end(method=method, outcome=outcome)
    except MissingPublishSessionError:
        _log.debug(
            "runtime.reducer.apply marker skipped (no bound publish session): method=%s phase=%s",
            method,
            phase,
        )


def _wrap_apply(fn: Callable[_P, _R], method_name: str) -> Callable[_P, _R]:
    """Single wrap implementation shared by both decorator call patterns."""

    @functools.wraps(fn)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        _publish_apply_marker(method=method_name, phase="start")
        outcome: Outcome = "success"
        try:
            return fn(*args, **kwargs)
        except BaseException:
            outcome = "failure"
            raise
        finally:
            _publish_apply_marker(method=method_name, phase="end", outcome=outcome)

    return wrapped


@overload
def _instrument_apply(method_name_or_fn: Callable[_P, _R]) -> Callable[_P, _R]: ...


@overload
def _instrument_apply(
    method_name_or_fn: str,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...


def _instrument_apply(
    method_name_or_fn: str | Callable[_P, _R],
) -> Callable[_P, _R] | Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Wrap an ``apply_*`` body with ``runtime.reducer.apply`` start/end markers.

    Every reducer fold emits one start marker and one end marker
    (``outcome="success"`` or ``"failure"``) via :func:`_publish_apply_marker`;
    the Reducer contract and the wrapped function's signature are unchanged.

    Two call patterns supported:

    - ``@_instrument_apply`` — uses ``fn.__name__`` as the method tag.
    - ``@_instrument_apply("custom_name")`` — explicit method tag.
    """
    if callable(method_name_or_fn):
        return _wrap_apply(method_name_or_fn, method_name_or_fn.__name__)

    method_name = method_name_or_fn

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        return _wrap_apply(fn, method_name)

    return decorator


class DefaultReducer(Reducer):
    """Reducer Protocol 默认实现（C4 单一写）。

    方法语义：
    - 全部以新 state 形式返回（虽然 AgentState 当前为 mutable dataclass，
      但本类把 mutation 集中在同一文件，未来 AgentState 转 frozen 后只
      改这一处）。
    - 每个方法是纯函数（除 await 内 yield）；无 side effect。
    - 公共 ``apply_*`` 方法通过 ``_instrument_apply`` 包装,每次调用经
      EventBus 发 ``runtime.reducer.apply`` start/end marker。
    """

    @_instrument_apply
    def apply_step_advanced(self, state: AgentState, step: int) -> AgentState:
        state.step = step
        state.budget.used_steps = step
        return state

    @_instrument_apply
    def apply_perception(self, state: AgentState, manifest: ContextManifest) -> AgentState:
        """fold ContextManifest 到 state。

        当前 Hub 已经通过 perceive_state 模块写入 current_manifest 和 gate_decided。
        Reducer 追加 manifest_digest 到 state.extra 作为 idempotency token
        ——用于 replay / cache 校验。
        """
        state.extra["manifest_digest"] = manifest.digest
        return state

    @_instrument_apply
    def apply_turn(self, state: AgentState, turn: Turn) -> AgentState:
        state.history.append(turn)
        return state

    @_instrument_apply
    def apply_skill_route(self, state: AgentState, active_template: str | None) -> AgentState:
        """fold SkillRouter.route(state) 返回的 active_template 到 state。

        PR-4 think.guard 原子化迁移:ModularBrain 不再直接写
        ``state.active_template``;通过 reducer 收口(C4 兑现)。
        active_template 是 prompt template 名字;空 = use default。
        """
        state.active_template = active_template
        return state

    @_instrument_apply
    def apply_activation(
        self, state: AgentState, activated: tuple[ActivatedSkill, ...]
    ) -> AgentState:
        if not activated:
            return state
        state.activated_skills.extend(activated)
        return state

    @_instrument_apply
    def apply_memory(self, state: AgentState, writes: object) -> AgentState:
        """fold MemoryWriteSet 到 state(无副作用版本)。

        Memory 写入由 Memory 协议自身负责(``memory.propose`` /
        ``memory.commit``);reducer 不直接动 memory 层。本方法为 seam
        完整性保留——plugin 可注入 reducer 在 commit 后做衍生 fold
        (例如 budget.used_tokens 累计)。
        """
        return state

    @_instrument_apply
    def apply_stop(self, state: AgentState, stop: StopDecision) -> AgentState:
        if stop.status is not None:
            state.status = stop.status
        # ADR-0158 决策 四:AgentState.final_output 字段已删除;stop 输出经
        # TerminalOutcome.final_output_ref 流通(本函数仅折叠 status / last_error)。
        # ADR-0122: typed failure detail propagates through stop.failure →
        # state.last_error, so the doctor_report / TerminalOutcome surfaces
        # carry the real exception rather than a fixed Chinese fallback.
        if stop.failure is not None and not state.last_error:
            state.last_error = stop.failure.message
        return state

    @_instrument_apply
    def apply_terminal_outcome(
        self,
        state: AgentState,
        stop: StopDecision,
        *,
        plan_ref: str,
        journal_seq_end: int,
        resume_cursor: ResumeCursor | None = None,
    ) -> TerminalOutcome:
        """Fold StopDecision into the sole TerminalOutcome (ADR-0077 §决策一).

        Slim orchestrator — delegates state→kind classification to
        :meth:`_classify_kind` and ErrorRef construction to
        :meth:`_build_error_ref`. The zero-output Chinese fallback lives in
        :meth:`_zero_output_fallback_message` so both call sites read the
        same string.

        ADR-0158 决策 四 + 决策 十:AgentState.final_output 字段已删除;
        final_output 来源改为:(a) StopDecision.final_output 显式传入;
        (b) state.history[-1].decision.response_text(decision 的载体文本);
        (c) handoff completion 走 "handoff completed" 占位(仅在 output_text
        为空时 materialization)。

        SSOT 收口(SSOT-Teardown):本方法**不**再内部调 ``apply_stop``;
        teardown 顺序由 caller 决定——caller 应先 ``apply_stop(state, stop)``
        再 ``apply_terminal_outcome(state, stop, ...)``。这避免历史 bug
        (spine 同 run 出现 apply_stop × 2,第二次嵌套在 apply_terminal_outcome
        内部,造成 reducer 状态被 apply 两次)。
        """
        # 注释保留:不再调 self.apply_stop(state, stop)。
        # 调用方必须在调本方法前显式 apply_stop 一次。

        # ADR-0158 决策 四:final_output 来源整合(不再读 state.final_output)。
        # 优先级:StopDecision.final_output > last_turn.decision.response_text
        response_text = self._extract_response_text(state, stop)

        kind, response_text = self._classify_kind(state, stop, response_text)

        # Build final_output_ref if we have output(ADR-0158 决策 四:
        # 输出文本从 response_text local 变量来,不再读 state.final_output 字段)
        final_output_ref = None
        if kind == TerminalOutcomeKind.COMPLETED and response_text:
            final_output_ref = TextRef(text=response_text, seq=journal_seq_end, cursor="")

        error_ref = self._build_error_ref(state, kind, stop)

        # A pause cursor belongs to the declared interpreter outcome. Do not
        # fabricate a legacy cursor: resume must be backed by durable facts.
        if kind == TerminalOutcomeKind.WAITING_INPUT and resume_cursor is None:
            raise DeclarativeValidationError(
                "RT-004",
                "waiting-input terminal outcome requires a durable resume cursor",
            )

        stop_reason_value = getattr(stop.reason, "value", str(stop.reason))
        return TerminalOutcome(
            kind=kind,
            stop_reason=stop_reason_value
            or ("completed" if kind == TerminalOutcomeKind.COMPLETED else "unknown"),
            final_output_ref=final_output_ref,
            artifact_refs=(),
            error_ref=error_ref,
            resume_cursor=resume_cursor,
            plan_ref=plan_ref,
            journal_seq_end=journal_seq_end,
        )

    @staticmethod
    def _zero_output_fallback_message() -> str:
        """SSOT for the Chinese 'no output produced' message.

        Both the WORKING-at-terminal branch and the COMPLETED-zero-output
        branch of :meth:`_classify_kind` use this string so the user-facing
        envelope is consistent across ladder entries.
        """
        return (
            "Agent 运行结束但未产生任何输出。可能原因: 工具循环失败、代码执行错误、模型未正确响应。"
        )

    def _classify_kind(
        self,
        state: AgentState,
        stop: StopDecision,
        response_text: str | None,
    ) -> tuple[TerminalOutcomeKind, str | None]:
        """Map ``state.status`` to a :class:`TerminalOutcomeKind` (the kind ladder).

        Mutates ``state.status`` per the existing rules (e.g. WORKING + output →
        COMPLETED; zero-output COMPLETED → FAILED). The second tuple element
        is the materialized response text — non-empty when a stable carrier
        is present, ``"handoff completed"`` when a HANDOFF decision was the
        terminal action, ``None`` otherwise.
        """
        # A terminal stop carrying output is authoritative even when older
        # StopDecision producers omit the optional status field; otherwise
        # the output would be discarded by the zero-output guard.
        if state.status == TaskStatus.WORKING and stop.should_stop and bool(response_text):
            state.status = TaskStatus.COMPLETED

        if state.status == TaskStatus.WORKING:
            # WORKING at terminal means budget exhausted without output = FAILED
            state.status = TaskStatus.FAILED
            if not state.last_error:
                state.last_error = self._zero_output_fallback_message()
            return TerminalOutcomeKind.FAILED, response_text

        if state.status == TaskStatus.COMPLETED:
            # A handoff is a valid completion even when its carrier has no
            # response text. Materialize a stable terminal marker so the
            # ADR-0077 TerminalOutcome still has the required output ref.
            output_text = response_text or ""
            if not output_text.strip() and self._is_handoff_completion(state):
                output_text = "handoff completed"
            if not output_text.strip():
                state.status = TaskStatus.FAILED
                if not state.last_error:
                    state.last_error = self._zero_output_fallback_message()
                return TerminalOutcomeKind.FAILED, response_text
            # ADR-0158 决策 四:final_output_ref 来源是 output_text 本地变量
            # (含 handoff 占位 materialization),不读 state.final_output 字段
            return TerminalOutcomeKind.COMPLETED, output_text

        if state.status == TaskStatus.FAILED:
            if not state.last_error:
                # phase.result fact under the run journal already carries
                # the typed ``PhaseExecutionFailure`` payload; users dig
                # into the journal for the cause. The reducer just gives
                # a single-sentence summary so the run envelope's
                # ``error`` field is informative rather than opaque.
                state.last_error = (
                    "Agent 阶段执行失败。可能原因: phase 异常、模型未响应或工具循环失败。"
                )
            return TerminalOutcomeKind.FAILED, response_text

        if state.status == TaskStatus.INPUT_REQUIRED:
            return TerminalOutcomeKind.WAITING_INPUT, response_text

        if state.status == TaskStatus.CANCELED:
            return TerminalOutcomeKind.CANCELED, response_text

        # DEGRADED or unknown status
        return TerminalOutcomeKind.DEGRADED, response_text

    @staticmethod
    def _build_error_ref(
        state: AgentState,
        kind: TerminalOutcomeKind,
        stop: StopDecision,
    ) -> ErrorRef | None:
        """Build the :class:`ErrorRef` for a terminal outcome (ADR-0077 invariant).

        The ADR-0077 invariant for FAILED requires ``error_ref`` to be set;
        upstream ``StopDecision`` does not carry a structured error field,
        so a FAILED terminal can land here with ``state.last_error`` empty
        (e.g. when stop_reason=ERROR fires without an explicit failure
        message). Fall back to the stop reason value so the invariant
        always holds and downstream consumers see a coherent reason.
        """
        if state.last_error:
            return ErrorRef(
                kind="error",
                message=state.last_error,
                source_ref="",
                diagnostic=getattr(stop, "failure", None),
            )
        if kind is TerminalOutcomeKind.FAILED:
            stop_reason_value = getattr(stop.reason, "value", str(stop.reason))
            return ErrorRef(
                kind="error",
                message=stop_reason_value or "stop_reason=error",
                source_ref="",
                diagnostic=getattr(stop, "failure", None),
            )
        if kind is TerminalOutcomeKind.CANCELED:
            return ErrorRef(kind="canceled", message="canceled", source_ref="")
        if kind is TerminalOutcomeKind.DEGRADED:
            return ErrorRef(kind="degraded", message="degraded", source_ref="")
        return None

    def _is_handoff_completion(self, state: AgentState) -> bool:
        """HANDOFF is a valid terminal action even when response_text is empty."""
        from lca.contracts.atoms.enums import ActionType

        if not state.history:
            return False
        last = state.history[-1]
        decision = getattr(last, "decision", None)
        return decision is not None and decision.action_type == ActionType.HANDOFF

    def _extract_response_text(self, state: AgentState, stop: StopDecision) -> str | None:
        """Resolve terminal response text without touching AgentState.final_output.

        ADR-0158 决策 四:AgentState.final_output 字段已删除;final output 改由
        StopDecision.final_output 显式传入,或回退到 state.history[-1].decision.response_text。

        返回值:non-empty str 表示有 carrier;空/None 表示走 handoff 占位或
        失败回退。
        """
        if stop.final_output:
            return stop.final_output
        if not state.history:
            return None
        last = state.history[-1]
        decision = getattr(last, "decision", None)
        if decision is None:
            return None
        text = getattr(decision, "response_text", None)
        return text if isinstance(text, str) and text else None

    @_instrument_apply
    def apply_error(self, state: AgentState, error: BaseException) -> AgentState:
        state.status = TaskStatus.FAILED
        state.last_error = repr(error)
        return state

    @_instrument_apply
    def apply_resume(
        self,
        state: AgentState,
        input_value: object | None,
        turn: Turn | None,
    ) -> AgentState:
        state.status = TaskStatus.WORKING
        if input_value is not None:
            state.working_memory["resume_input"] = input_value
        if turn is not None:
            state.history.append(turn)
            state.step += 1
        return state

    @_instrument_apply
    def apply_paused(self, state: AgentState, snapshot_ref: object) -> AgentState:
        state.status = TaskStatus.INPUT_REQUIRED
        return state


@plugin(
    id="lca-default-reducer",
    provides=["reducer"],
    implements=["Reducer"],
    layer="L2",
    effects="none",
    description="Default Reducer implementation (ADR-0066 C4 single-writer).",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("reducer", DefaultReducer())


__all__ = ["Config", "DefaultReducer", "setup"]
