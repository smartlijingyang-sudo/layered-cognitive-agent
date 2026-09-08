"""Adapter: agent_lab perceive.sub_spec ↔ LCA SequentialPerceiveHub.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.think.cognition.PerceiveHub
  - lca.contracts.models.core.perceive.perception.ContextManifest
  - lca.contracts.models.core.perceive.perception.ContextItem
  - lca.contracts.models.core.state.state.AgentState

agent_lab provides (this file):
  - LcaPerceiveProvider: wraps a PerceiveHub, takes agent_lab artifacts,
    returns an agent_lab Artifact carrying a frozen ContextManifest.
  - register_fixture_hub(name, hub): stash a Hub in a process-local dict,
    referenced by name from node.config (avoids serializing live objects
    through the plan_hash dump).

The Hub is the SOLE emitter of ContextManifested (per LCA contracts);
this adapter never constructs a ContextManifest by hand. It only glues
agent_lab Artifact inputs to Hub.perceive(state).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# Process-local fixture Hub registry. Looked up by name from
# ``provider_config.fixture_hub_name`` so node.config stays JSON-serializable
# (compile() calls model_dump(mode="json") on the whole spec to compute
# plan_hash; live objects would crash the dump).
_FIXTURE_HUBS: dict[str, Any] = {}


def register_fixture_hub(name: str, hub: Any) -> None:
    """Register a Hub under ``name`` for later resolution by config."""
    _FIXTURE_HUBS[name] = hub


def unregister_fixture_hub(name: str) -> None:
    _FIXTURE_HUBS.pop(name, None)


@dataclass(frozen=True)
class LcaPerceiveProvider:
    """Build a frozen ContextManifest via LCA's PerceiveHub.

    Provider selection is data, not code: see
    ``agent_lab/nodes/mv/perceive_build/plugin.py`` for the call site.
    Resolution order:
      1. ``provider_config.fixture_hub_name`` (looks up ``_FIXTURE_HUBS``;
         test-only; keeps node.config JSON-serializable).
      2. ``provider_config.hub_factory`` (module:Class form).
      3. Fallback: ``NullPerceiveHub`` from LCA's runtime fixtures.
    """

    _hub: Any  # lca.contracts.protocols.PerceiveHub; late-bound

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaPerceiveProvider:
        """Resolve a Hub from the node's provider_config block."""
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_hub_name")
        if name and name in _FIXTURE_HUBS:
            return cls(_hub=_FIXTURE_HUBS[name])
        factory = cfg.get("hub_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            hub_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_hub=hub_cls(**kwargs))
        # Fallback: NullPerceiveHub (always works, requires only contracts).
        from lca.plugins.composer.runtime.fixture.runtime_factory import (
            NullPerceiveHub,
        )

        return cls(_hub=NullPerceiveHub())

    def build(
        self,
        *,
        sanitized_artifact: Artifact | None,
        state_artifact: Artifact | None,
        out_port: str = "manifest",
    ) -> dict[str, Artifact]:
        """Run Hub.perceive(state) and wrap the frozen ContextManifest."""
        state = _coerce_state(state_artifact)
        manifest = _run_async(self._hub.perceive(state))
        return {
            out_port: Artifact(
                kind=ArtifactKind.MANIFEST,
                content={
                    "items": [_item_to_dict(item) for item in manifest.items],
                    "digest": manifest.digest,
                    "schema_version": manifest.schema_version,
                    "extra": dict(manifest.extra or {}),
                },
                schema_ref="context.manifest.v1",
            )
        }


def _coerce_state(artifact: Artifact | None) -> Any:
    """Coerce an agent_lab state artifact into a minimal LCA AgentState.

    AgentState is a frozen dataclass with three required positional fields
    (``trace_id``, ``task``, ``budget``) that the Hub never reads. We
    supply empty sentinels for those so the partial construction is
    correct. Anything not handled below is routed into ``state.extra``
    so profile-side state keeps round-tripping.
    """
    from lca.contracts.models.core.state.state import AgentState

    content = (artifact.content if artifact is not None else None) or {}
    if not isinstance(content, dict):
        content = {}
    extra = dict(content.get("extra") or {})
    known = {"step", "history", "retrieved_context", "working_memory", "schema_version"}
    for k, v in content.items():
        if k not in known and k != "extra":
            extra[k] = v
    return AgentState(
        trace_id="",
        task="",
        budget=None,
        step=int(content.get("step", 0) or 0),
        retrieved_context=tuple(content.get("retrieved_context") or ()),
        extra=extra,
    )


def _item_to_dict(item: Any) -> dict[str, Any]:
    return {
        "kind": getattr(item, "kind", ""),
        "payload": getattr(item, "payload", None),
        "provenance": getattr(item, "provenance", ""),
        "ref": getattr(item, "ref", None),
        "extra": dict(getattr(item, "extra", {}) or {}),
    }


def _import_dotted(ref: str) -> Any:
    """Import ``module.path:ClassName`` (or ``module.path``) form."""
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        obj = __import__(mod, fromlist=[attr])
        return getattr(obj, attr)
    return __import__(ref)


def _run_async(coro: Any) -> Any:
    """Run an awaitable from sync node.execute().

    agent_lab's runner invokes nodes synchronously (see
    agent_lab/runtime/runner.py:_run_node), so no loop is in flight when
    we reach this adapter. If a loop IS already running (e.g. an outer
    asyncio test), use nest_asyncio.apply() to nest it; otherwise a plain
    asyncio.run is correct.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        import nest_asyncio  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only in tests
        raise RuntimeError(
            "LcaPerceiveProvider called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


__all__ = ["LcaPerceiveProvider", "register_fixture_hub", "unregister_fixture_hub"]
