"""ReactLoopAgent — default agent driver over queued turns and step-boundary input.

1:1 port of ``@deepseek-ai/dsh-agent-loop/agent.ts``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from lca.layer0_infra.dsh_core.agent import (
    AgentCancelCause,
    AgentOptions,
    AgentStatus,
    CancelOptions,
    Inbox,
    InboxTarget,
    PreStepDecision,
    RequestErrorAction,
    agent_events,
    assemble_context_for,
)
from lca.layer0_infra.dsh_core.agent_loop.runtime_context import RuntimeContextProjection
from lca.layer0_infra.dsh_core.agent_loop.tool_calls import execute_tool_calls
from lca.layer0_infra.dsh_core.scope import Scope, create_scope
from lca.layer0_infra.dsh_core.session import (
    Session,
    canonical_header,
    header_equals,
)

Phase = dict[str, Any]
StepEndReason = Literal["completed", "max-tokens"] | dict[str, Any]
PreparedStep = dict[str, Any]


@dataclass
class AbortController:
    """Simple abort controller for Python (asyncio.Event-based)."""

    signal: asyncio.Event = field(default_factory=asyncio.Event)
    reason: Any = None

    def abort(self, reason: Any = None) -> None:
        self.reason = reason
        self.signal.set()


def _request_proposal(header: Any) -> Any:
    """Remove adapter-derived values before plugins propose the next request config."""
    if not hasattr(header, "adapter_defaults") or header.adapter_defaults is None:
        return header.config
    proposal = dict(header.config) if isinstance(header.config, dict) else header.config
    if getattr(header.adapter_defaults, "reasoning_effort", False) is True and "reasoningEffort" in proposal:
        del proposal["reasoningEffort"]
    if getattr(header.adapter_defaults, "max_tokens", False) is True and "maxTokens" in proposal:
        del proposal["maxTokens"]
    return proposal


class ReactLoopAgent:
    """Drives one session through turn and step boundaries."""

    def __init__(
        self,
        loop_ctx: Any,
        agent_id: str,
        options: AgentOptions,
        session: Session,
    ) -> None:
        self._loop_ctx = loop_ctx
        self._agent_id = agent_id
        self.options = options
        self.session = session

        self.inbox = Inbox(session, {
            "inserted": lambda msg: self.dispatch.emit("agent/inbox/inserted", {"message": msg}),
            "discarded": lambda msg: self.dispatch.emit("agent/inbox/discarded", {"message": msg}),
            "claimed": lambda msg, turn: self.dispatch.emit("agent/inbox/claimed", {"message": msg, "turn": turn}),
        })

        # Find last turn
        last_turn = 0
        for event in reversed(session.events):
            if event.type == "turn/start":
                last_turn = event.data.get("turn", 0)
                break

        self._phase: dict[str, Any] = {"kind": "idle", "lastTurn": last_turn}
        self._activity_done: asyncio.Future = asyncio.Future()
        self._activity_done.set_result(None)
        self._request_header_logged = False

        self.dispatch = agent_events(loop_ctx, self)
        self.scope: Scope = create_scope(loop_ctx, self)
        self.runtime_context = RuntimeContextProjection(loop_ctx, session)

    @property
    def status(self) -> AgentStatus:
        return "idle" if self._phase["kind"] in ("idle", "maintenance") else "running"

    def _set_phase(self, next_phase: dict[str, Any]) -> None:
        prev = self.status
        self._phase = next_phase
        if self.status != prev:
            self.dispatch.emit("agent/status", {"status": self.status})

    def send(self, message: Any, target: InboxTarget, wakeup: bool) -> None:
        waking_after_abort = (
            wakeup
            and self._phase["kind"] != "idle"
            and self._phase.get("abort") is not None
            and self._phase["abort"].signal.is_set()
        )
        resolved_target = "next-turn" if waking_after_abort else target
        # Inbox splice at infinity = append
        self.inbox.splice(resolved_target, float("inf"), 0, [message])
        if wakeup:
            self._wake_driver(waking_after_abort)

    def followup(self, message: Any) -> None:
        self.send(message, "next-turn", True)

    def steer(self, message: Any) -> None:
        self.send(message, "next-step", True)

    def inject(self, message: Any) -> None:
        self.send(message, "next-step", False)

    def cancel(self, cause: AgentCancelCause, options: CancelOptions | None = None) -> None:
        keep_inbox = bool(options and getattr(options, "keep_inbox", False))
        if not keep_inbox:
            if hasattr(self.inbox, "clear"):
                self.inbox.clear()
            self._phase["wakeRequested"] = False
        if self._phase["kind"] != "idle":
            self._phase["abort"].abort(cause)

    def run_maintenance(self, job: Callable[[asyncio.Event], Awaitable[Any]]) -> asyncio.Future:
        if self._phase["kind"] != "idle":
            raise RuntimeError(f'agent "{self._agent_id}" already has active work')
        done = asyncio.Future()
        maintenance: dict[str, Any] = {
            "kind": "maintenance",
            "abort": AbortController(),
            "lastTurn": self._phase.get("lastTurn", 0),
            "wakeRequested": False,
        }
        self._set_phase(maintenance)
        self._activity_done = done

        async def _runner() -> None:
            try:
                await job(maintenance["abort"].signal)
            finally:
                self._set_phase({"kind": "idle", "lastTurn": maintenance["lastTurn"]})
                if maintenance["wakeRequested"] and self.inbox.has_pending:
                    self._wake_driver()
                done.set_result(None)

        asyncio.create_task(_runner())
        return done

    def _wake_driver(self, wake_after_abort: bool = False) -> None:
        if self._phase["kind"] != "idle":
            reason = self._phase["abort"].reason
            if (
                reason != "disposed"
                and (self._phase["kind"] == "maintenance" or wake_after_abort)
            ):
                self._phase["wakeRequested"] = True
            return
        driver = asyncio.Future()
        self._activity_done = driver
        self._set_phase({
            "kind": "running",
            "abort": AbortController(),
            "turn": self._phase.get("lastTurn", 0),
            "step": 0,
            "wakeRequested": False,
        })

        async def _kick_wrapper() -> None:
            try:
                await self._kick()
            finally:
                driver.set_result(None)

        asyncio.create_task(_kick_wrapper())

    async def when_idle(self) -> None:
        while True:
            activity = self._activity_done
            with contextlib.suppress(Exception):
                await activity
            if activity is self._activity_done:
                break

    def _throw_error(self, error: Any) -> None:
        turn = self._phase["turn"] if self._phase["kind"] == "running" else self._phase.get("lastTurn", 0)
        step = self._phase["step"] if self._phase["kind"] == "running" else 0
        self.dispatch.emit("agent/error", {"turn": turn, "step": step, "error": error})
        raise error

    async def _kick(self) -> None:
        try:
            while await self._turn():
                pass
        except Exception:
            pass
        finally:
            if self._phase["kind"] == "running":
                turn = self._phase.get("turn", 0)
                self._set_phase({"kind": "idle", "lastTurn": turn})
                if self._phase.get("wakeRequested") and self.inbox.has_pending:
                    self._wake_driver()

    async def _pre_step(self, target: InboxTarget, position: dict[str, int]) -> PreparedStep:
        if self._phase["kind"] != "running":
            raise RuntimeError(f'agent "{self._agent_id}": pre-step outside running phase')
        signal = self._phase["abort"].signal
        claimed = self.inbox.claim(target, position["turn"])

        # Assemble system prompt
        try:
            assembly = await self._loop_ctx.system_prompt.assemble(assemble_context_for(self, signal))
        except Exception:
            assembly = None

        if signal.is_set():
            raise asyncio.CancelledError()

        sections = []
        context = self.runtime_context.project(getattr(assembly, "context_snapshot", "") or "", sections) if assembly else None

        default_decision: PreStepDecision = {
            "kind": "enter",
            "messages": [*claimed, *(["context"] if context else [])],
        }

        try:
            decision = await self.dispatch.waterfall(
                "agent/pre-step",
                {"messages": claimed, **position, "signal": signal},
                terminal=lambda: asyncio.sleep(0, result=default_decision),
            )
        except Exception:
            decision = default_decision

        if signal.is_set():
            raise asyncio.CancelledError()

        return {"kind": decision.get("kind", "enter"), "messages": decision.get("messages", []), "assembly": assembly}

    async def _turn(self) -> bool:
        if self._phase["kind"] != "running":
            self._throw_error(RuntimeError(f'agent "{self._agent_id}": turn without driver reservation'))
        phase = self._phase
        signal = phase["abort"].signal
        if signal.is_set():
            raise asyncio.CancelledError()

        turn = phase.get("turn", 0) + 1
        self.session.append("turn/start", {"turn": turn})
        phase["turn"] = turn
        turn_ends: dict[str, Any] | None = None
        target: InboxTarget = "next-turn"

        try:
            while True:
                if signal.is_set():
                    raise asyncio.CancelledError()
                step = phase.get("step", 0) + 1
                decision = await self._pre_step(target, {"turn": turn, "step": step})
                if decision["kind"] == "reject":
                    turn_ends = {"kind": "blocked"}
                    return False
                if turn_ends is not None and len(decision["messages"]) == 0:
                    break
                if phase.get("step", 0) == 0 and len(decision["messages"]) == 0:
                    turn_ends = {"kind": "completed"}
                    return False
                if signal.is_set():
                    raise asyncio.CancelledError()
                self.session.append("step/start", {"turn": turn, "step": step})
                phase["step"] = step
                try:
                    for msg in decision["messages"]:
                        if isinstance(msg, dict):
                            self.session.append("user/message", msg, {"surfaceOp": "append"})
                    step_end = await self._step(decision.get("assembly"))
                    if turn_ends is None or turn_ends.get("kind") != "max-tokens":
                        turn_ends = step_end
                finally:
                    self.session.append("step/end", {"turn": turn, "step": step})
                if signal.is_set():
                    raise asyncio.CancelledError()
                if turn_ends is not None and len(self.inbox.next_step) == 0:
                    with contextlib.suppress(Exception):
                        await self.dispatch.serial("agent/turn-stopping", {"turn": turn, "signal": signal})
                    if signal.is_set():
                        raise asyncio.CancelledError()
                if turn_ends is not None and len(self.inbox.next_step) == 0:
                    break
                target = "next-step"
        except asyncio.CancelledError:
            reason = phase["abort"].reason
            turn_ends = {"kind": "aborted", "reason": reason}
            raise
        except Exception as exc:
            turn_ends = {
                "kind": "error",
                "error": {"message": str(exc), "code": "UNKNOWN"},
            }
            self._throw_error(exc)
        finally:
            try:
                self.session.append("turn/end", {"turn": turn, "reason": turn_ends})
            except Exception as exc:
                self._throw_error(exc)

        if not self.inbox.has_pending:
            return False
        phase["abort"] = AbortController()
        phase["wakeRequested"] = False
        phase["step"] = 0
        return True

    async def _step(self, assembly: Any) -> dict[str, Any]:
        if self._phase["kind"] != "running":
            raise RuntimeError(f'agent "{self._agent_id}": step outside running phase')
        turn = self._phase["turn"]
        step = self._phase["step"]
        signal = self._phase["abort"].signal
        if signal.is_set():
            raise asyncio.CancelledError()

        system = ""
        if assembly is not None and hasattr(assembly, "system"):
            system = assembly.system or ""

        while True:
            request, prepared_call = await self._build_request(turn, step, [], system, [], signal)

            stream = prepared_call.stream(request) if prepared_call is not None else self._loop_ctx.llm.stream(request)

            chunk_seqs = []
            blocks = []
            finish: dict[str, Any] = {"kind": "ok"}
            try:
                async for chunk in stream:
                    if signal.is_set():
                        raise asyncio.CancelledError()
                    event = self.session.append(
                        "assistant/chunk",
                        {"turn": turn, "step": step, "chunk": chunk},
                    )
                    chunk_seqs.append(event.seq)
                    if hasattr(chunk, "type"):
                        if chunk.type == "text-delta" or chunk.type == "reasoning-delta":
                            blocks.append({"type": "text", "text": getattr(chunk, "text", "")})
                        elif chunk.type == "tool-call-delta":
                            pass  # accumulate for tool call assembly
            except asyncio.CancelledError:
                finish = {"kind": "aborted", "failure": {"message": "aborted", "code": "ABORTED"}}
            except Exception as exc:
                finish = {"kind": "error", "failure": {"message": str(exc), "code": "UNKNOWN"}}

            if signal.is_set():
                raise asyncio.CancelledError()

            if finish["kind"] in ("error", "aborted"):
                default_action: RequestErrorAction = None
                try:
                    action = await self.dispatch.waterfall(
                        "agent/request-error",
                        {
                            "turn": turn,
                            "step": step,
                            "provider": request.get("provider", ""),
                            "failure": finish["failure"],
                            "signal": signal,
                        },
                        terminal=lambda: asyncio.sleep(0, result=default_action),
                    )
                except Exception:
                    action = default_action
                if action is not None and action.get("kind") == "retry":
                    continue
                raise RuntimeError(finish["failure"]["message"])

            message = {
                "content": blocks,
                "source": {
                    "kind": "model",
                    "provider": request.get("provider", ""),
                    "model": request.get("model", ""),
                },
            }
            self.session.append(
                "assistant/message",
                {"turn": turn, "step": step, "message": message},
                {"surfaceOp": "append", "sourceEventSeqs": chunk_seqs},
            )

            if finish["kind"] == "max-tokens":
                return {"kind": "max-tokens"}

            tool_calls = [b for b in blocks if b.get("type") == "tool-call"]
            if not tool_calls:
                return {"kind": "completed"}

            async def _inject_ctx(msg: Any) -> None:
                self.inbox.splice("next-step", len(self.inbox.next_step), 0, [msg])

            result = await execute_tool_calls(
                self._loop_ctx, turn, step, tool_calls, signal,
                inject_context=_inject_ctx,
            )
            return {"kind": "completed"} if result.concluded else None

    async def _build_request(
        self,
        turn: int,
        step: int,
        tools: Any,
        system: str,
        boundary_messages: Any,
        signal: asyncio.Event,
    ) -> tuple[dict[str, Any], Any]:
        session = self.session

        persisted_header = session.request_header() if hasattr(session, "request_header") else None
        persisted_config = getattr(persisted_header, "config", None) if persisted_header else None
        route = {
            "provider": getattr(self.options, "provider", "") or "",
            "model": getattr(self.options, "model", "") or "",
        }
        reasoning_effort = None
        if persisted_config and persisted_config.get("provider") == route["provider"] and persisted_config.get("model") == route["model"]:
            adapter_defaults = getattr(persisted_header, "adapter_defaults", None)
            if not (adapter_defaults and getattr(adapter_defaults, "reasoning_effort", False)):
                reasoning_effort = persisted_config.get("reasoningEffort")

        max_tokens = getattr(self.options, "max_tokens", None)
        if not self._request_header_logged:
            seed_config: dict[str, Any] = dict(route)
            if reasoning_effort is not None:
                seed_config["reasoningEffort"] = reasoning_effort
            if max_tokens is not None:
                seed_config["maxTokens"] = max_tokens
        else:
            seed_config = _request_proposal(persisted_header) if persisted_header else dict(route)

        try:
            proposed_config = await self.dispatch.waterfall(
                "agent/request",
                {"turn": turn, "step": step, "signal": signal},
                terminal=lambda: asyncio.sleep(0, result=dict(seed_config)),
            )
        except Exception:
            proposed_config = dict(seed_config)

        if signal.is_set():
            raise asyncio.CancelledError()
        if not proposed_config.get("provider") or not proposed_config.get("model"):
            raise RuntimeError(f'agent "{self._agent_id}" has no provider/model')

        prepared_call = None
        try:
            prepared_call = await self._loop_ctx.llm.prepare_call(proposed_config, signal)
            config = prepared_call.config
        except Exception:
            config = proposed_config

        if signal.is_set():
            raise asyncio.CancelledError()

        header = canonical_header({
            "config": config,
            "system": system,
            "tools": tools,
        })

        baseline = session.request_header() if hasattr(session, "request_header") else None
        if not self._request_header_logged:
            reason = "initial" if baseline is None else "resume"
            self.session.append("request/header", {"header": header, "reason": reason})
            self._request_header_logged = True
        elif baseline is None or not header_equals(baseline, header):
            self.session.append("request/header", {"header": header, "reason": "change"})

        previous_context = session.request_context() if hasattr(session, "request_context") else None
        ctx_window = getattr(getattr(prepared_call, "context", None), "context_window", None)
        request_context = {
            "provider": config.get("provider"),
            "model": config.get("model"),
        }
        if ctx_window is not None:
            request_context["contextWindow"] = ctx_window
        if previous_context is None or previous_context.get("provider") != request_context["provider"] or previous_context.get("model") != request_context["model"] or previous_context.get("contextWindow") != request_context.get("contextWindow"):
            with contextlib.suppress(Exception):
                self.session.append("request/context", request_context)

        if signal.is_set():
            raise asyncio.CancelledError()

        request = {
            **config,
            "messages": boundary_messages,
            "system": system,
        }
        if tools:
            request["tools"] = tools
        if session.id:
            request["sessionId"] = session.id

        return request, prepared_call
