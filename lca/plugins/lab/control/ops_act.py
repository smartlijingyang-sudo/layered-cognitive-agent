from __future__ import annotations

"""Inlined lab adapter (PR-D).

Source: commit 0eb66079^:agent_lab/adapters/.py.
The lab plugin tree is the only consumer.

delete-when: lab plugin tree fuses with LCA production path.
"""

import importlib
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Shared: process-local fixture registries (one per slot)
# ---------------------------------------------------------------------------
_FIXTURE_PERCEIVE_CONTEXT: dict[str, Any] = {}
_FIXTURE_ACT_AUTHORIZE: dict[str, Any] = {}
_FIXTURE_ACT_BUDGET: dict[str, Any] = {}
_FIXTURE_ACT_CONSTRAIN: dict[str, Any] = {}
_FIXTURE_ACT_EXECUTE: dict[str, Any] = {}
_FIXTURE_ACT_SAFE_BOUNDARY: dict[str, Any] = {}
_FIXTURE_OBSERVE_WILDCARD: dict[str, Any] = {}


def register_fixture_perceive_context(name: str, fn: Any) -> None:
    _FIXTURE_PERCEIVE_CONTEXT[name] = fn


def unregister_fixture_perceive_context(name: str) -> None:
    _FIXTURE_PERCEIVE_CONTEXT.pop(name, None)


def register_fixture_act_authorize(name: str, fn: Any) -> None:
    _FIXTURE_ACT_AUTHORIZE[name] = fn


def unregister_fixture_act_authorize(name: str) -> None:
    _FIXTURE_ACT_AUTHORIZE.pop(name, None)


def register_fixture_act_budget(name: str, fn: Any) -> None:
    _FIXTURE_ACT_BUDGET[name] = fn


def unregister_fixture_act_budget(name: str) -> None:
    _FIXTURE_ACT_BUDGET.pop(name, None)


def register_fixture_act_constrain(name: str, fn: Any) -> None:
    _FIXTURE_ACT_CONSTRAIN[name] = fn


def unregister_fixture_act_constrain(name: str) -> None:
    _FIXTURE_ACT_CONSTRAIN.pop(name, None)


def register_fixture_act_execute(name: str, fn: Any) -> None:
    _FIXTURE_ACT_EXECUTE[name] = fn


def unregister_fixture_act_execute(name: str) -> None:
    _FIXTURE_ACT_EXECUTE.pop(name, None)


def register_fixture_act_safe_boundary(name: str, fn: Any) -> None:
    _FIXTURE_ACT_SAFE_BOUNDARY[name] = fn


def unregister_fixture_act_safe_boundary(name: str) -> None:
    _FIXTURE_ACT_SAFE_BOUNDARY.pop(name, None)


def register_fixture_observe_wildcard(name: str, fn: Any) -> None:
    _FIXTURE_OBSERVE_WILDCARD[name] = fn


def unregister_fixture_observe_wildcard(name: str) -> None:
    _FIXTURE_OBSERVE_WILDCARD.pop(name, None)


# ---------------------------------------------------------------------------
# Fallback: always-allow
# ---------------------------------------------------------------------------


class _AlwaysAllow:
    """Fallback callable that returns allowed=True for any input."""

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"allowed": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        obj = importlib.import_module(mod)
        return getattr(obj, attr)
    return importlib.import_module(ref)


def _make_allowed_artifact(allowed: bool, **extra: Any) -> Artifact:
    content: dict[str, Any] = {"allowed": allowed, **extra}
    return Artifact(kind=ArtifactKind.FACT, content=content, schema_ref="control.allowed.v1")


# ---------------------------------------------------------------------------
# PerceiveContext provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlPerceiveContextProvider:
    """Wraps a callable for perceive.context — decides if data becomes trusted.

    eval(args) -> {allowed: bool, trust_label: str}. Fallback: always accept.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlPerceiveContextProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_PERCEIVE_CONTEXT:
            return cls(_fn=_FIXTURE_PERCEIVE_CONTEXT[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(self, args_artifact: Artifact | None) -> dict[str, Artifact]:
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(args_content) if callable(self._fn) else {"allowed": True}
        if isinstance(result, dict):
            allowed = bool(result.get("allowed", True))
            extra = {k: v for k, v in result.items() if k != "allowed"}
        else:
            allowed = bool(result)
            extra = {}
        return {"allowed": _make_allowed_artifact(allowed, **extra)}


# ---------------------------------------------------------------------------
# ActAuthorize provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlActAuthorizeProvider:
    """Wraps a callable / allowlist for act.authorize — tool authorization.

    eval(tool_name, args) -> {allowed: bool}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlActAuthorizeProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_ACT_AUTHORIZE:
            return cls(_fn=_FIXTURE_ACT_AUTHORIZE[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(self, args_artifact: Artifact | None) -> dict[str, Artifact]:
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(args_content) if callable(self._fn) else {"allowed": True}
        allowed = bool(result.get("allowed", True)) if isinstance(result, dict) else bool(result)
        return {"allowed": _make_allowed_artifact(allowed)}


# ---------------------------------------------------------------------------
# ActBudget provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlActBudgetProvider:
    """Wraps a BudgetPolicy for act.budget — budget check.

    eval(state, args) -> {allowed: bool}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlActBudgetProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_ACT_BUDGET:
            return cls(_fn=_FIXTURE_ACT_BUDGET[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(
        self,
        state_artifact: Artifact | None,
        args_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        state_content = state_artifact.content if state_artifact else {}
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(state_content, args_content) if callable(self._fn) else {"allowed": True}
        allowed = bool(result.get("allowed", True)) if isinstance(result, dict) else bool(result)
        return {"allowed": _make_allowed_artifact(allowed)}


# ---------------------------------------------------------------------------
# ActConstrain provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlActConstrainProvider:
    """Wraps a callable for act.constrain — strategy constraints.

    eval(args) -> {allowed: bool}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlActConstrainProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_ACT_CONSTRAIN:
            return cls(_fn=_FIXTURE_ACT_CONSTRAIN[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(self, args_artifact: Artifact | None) -> dict[str, Artifact]:
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(args_content) if callable(self._fn) else {"allowed": True}
        allowed = bool(result.get("allowed", True)) if isinstance(result, dict) else bool(result)
        return {"allowed": _make_allowed_artifact(allowed)}


# ---------------------------------------------------------------------------
# ActExecute provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlActExecuteProvider:
    """Wraps a callable for act.execute — safe execution gate.

    eval(args) -> {allowed: bool}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlActExecuteProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_ACT_EXECUTE:
            return cls(_fn=_FIXTURE_ACT_EXECUTE[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(self, args_artifact: Artifact | None) -> dict[str, Artifact]:
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(args_content) if callable(self._fn) else {"allowed": True}
        allowed = bool(result.get("allowed", True)) if isinstance(result, dict) else bool(result)
        return {"allowed": _make_allowed_artifact(allowed)}


# ---------------------------------------------------------------------------
# ActSafeBoundary provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlActSafeBoundaryProvider:
    """Wraps a callable for act.safe-boundary — last-chance isolation gate.

    eval(args) -> {allowed: bool}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlActSafeBoundaryProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_ACT_SAFE_BOUNDARY:
            return cls(_fn=_FIXTURE_ACT_SAFE_BOUNDARY[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllow())

    def evaluate(self, args_artifact: Artifact | None) -> dict[str, Artifact]:
        args_content = args_artifact.content if args_artifact else {}
        result = self._fn(args_content) if callable(self._fn) else {"allowed": True}
        allowed = bool(result.get("allowed", True)) if isinstance(result, dict) else bool(result)
        return {"allowed": _make_allowed_artifact(allowed)}


# ---------------------------------------------------------------------------
# ObserveWildcard provider — observe.* cross-cutting slot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlObserveWildcardProvider:
    """Wraps the observe.* wildcard observer.

    Default executor is a no-op that returns ``{verdict: allow}`` for any
    input, matching LCA's ``ObserveWildcardExecutor.execute`` semantics.
    Tests can inject a callable via ``provider_config.fixture_name`` that
    returns either a dict ``{verdict: allow|deny, ...}`` or a plain bool.

    eval(event) -> {verdict: allow|deny}. Fallback: always allow.
    """

    _fn: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlObserveWildcardProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_name")
        if name and name in _FIXTURE_OBSERVE_WILDCARD:
            return cls(_fn=_FIXTURE_OBSERVE_WILDCARD[name])
        factory = cfg.get("callable_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            fn = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_fn=fn(**kwargs))
        return cls(_fn=_AlwaysAllowWildcard())

    def emit(
        self,
        *,
        event_type: str = "wildcard",
        in_event: Artifact | None = None,
        out_port: str = "wildcard_event",
    ) -> dict[str, Artifact]:
        event_content = in_event.content if in_event else {}
        result = self._fn(event_content) if callable(self._fn) else {"verdict": "allow"}
        if isinstance(result, dict):
            verdict = str(result.get("verdict", "allow"))
            extra = {k: v for k, v in result.items() if k != "verdict"}
        else:
            verdict = "allow" if bool(result) else "deny"
            extra = {}
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "verdict": verdict,
                    "event_type": event_type,
                    **extra,
                },
                schema_ref="observe.wildcard.v1",
            ),
        }


class _AlwaysAllowWildcard:
    """Fallback wildcard observer — always returns verdict=allow."""

    def __call__(self, _event: Any) -> dict[str, Any]:
        return {"verdict": "allow"}


__all__ = [
    "LcaControlActAuthorizeProvider",
    "LcaControlActBudgetProvider",
    "LcaControlActConstrainProvider",
    "LcaControlActExecuteProvider",
    "LcaControlActSafeBoundaryProvider",
    "LcaControlObserveWildcardProvider",
    "LcaControlPerceiveContextProvider",
    "register_fixture_act_authorize",
    "register_fixture_act_budget",
    "register_fixture_act_constrain",
    "register_fixture_act_execute",
    "register_fixture_act_safe_boundary",
    "register_fixture_observe_wildcard",
    "register_fixture_perceive_context",
    "unregister_fixture_act_authorize",
    "unregister_fixture_act_budget",
    "unregister_fixture_act_constrain",
    "unregister_fixture_act_execute",
    "unregister_fixture_act_safe_boundary",
    "unregister_fixture_observe_wildcard",
    "unregister_fixture_perceive_context",
]
