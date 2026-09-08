"""model_eye.see — derive the model's field of view for this turn.

Collects Session-derived history/header (ADR-0191 DSH) and merges this-turn
feeds (Hub context_manifest, user_turn, effect observation, system/tools/config)
into one unfrozen ``sight`` bag. Pure derive: no State write, no LLM call.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="model_eye.see",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description=(
        "Derive sight from Session + perceive.bundle + observation + header. "
        "Output is an unfrozen bag for guard/shape/freeze."
    ),
    inputs=[
        PortInfo("context_manifest", kind=PortKind.ARTIFACT, required=False),
        PortInfo("perceive_bundle", kind=PortKind.ARTIFACT, required=False),
        PortInfo("observation", kind=PortKind.ARTIFACT, required=False),
        PortInfo("system", kind=PortKind.TEXT, required=False),
        PortInfo("history", kind=PortKind.MESSAGE, required=False),
        PortInfo("config", kind=PortKind.FACT, required=False),
        PortInfo("tools", kind=PortKind.FACT, required=False),
        PortInfo("user_turn", kind=PortKind.MESSAGE, required=False),
    ],
    outputs=[PortInfo("sight", kind=PortKind.FACT)],
    provides=["model_eye_sight"],
    requires=["session_reader"],
    emits=[],
    relates_to=["model_eye.guard", "model_eye.shape", "model_eye.freeze"],
)
class ModelEyeSee(Node):
    name = "model_eye.see"

    def execute(self, node, inputs):
        messages, system, config, tools = _derive_session()
        messages = _merge_history(messages, inputs.get("history"))
        messages = _merge_user_turn(messages, inputs.get("user_turn"))
        system = _overlay_text(system, inputs.get("system"))
        config = _overlay_dict(config, inputs.get("config"))
        tools = _overlay_tools(tools, inputs.get("tools"))
        hub_art = inputs.get("context_manifest") or inputs.get("perceive_bundle")
        perceive_items = _artifact_list(hub_art, key="items")
        observation = _artifact_content(inputs.get("observation"))

        sight = {
            "messages": messages,
            "system": system,
            "config": config,
            "tools": tools,
            "perceive_items": perceive_items,
            "observation": observation,
        }
        out = node.config.get("to", "sight")
        return {
            out: Artifact(
                kind=ArtifactKind.FACT,
                content=sight,
                schema_ref="model_eye.sight.v1",
            )
        }


def _derive_session() -> tuple[list[dict[str, Any]], str | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Read Session derive_messages + request_header when available.

    Fail-loud only when the Session API itself raises; an empty Session is a
    valid first-turn state (messages=[], header=None).
    """
    try:
        from agent_lab.nodes.session_log._sink import get_session

        sess = get_session()
    except Exception as exc:  # pragma: no cover - import/boot failure
        raise RuntimeError(f"model_eye.see: Session unavailable: {exc}") from exc

    messages: list[dict[str, Any]] = []
    derive = getattr(sess, "derive_messages", None)
    if callable(derive):
        raw = derive()
        if isinstance(raw, list):
            messages = [dict(m) for m in raw if isinstance(m, dict)]

    system: str | None = None
    config: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = []
    header_fn = getattr(sess, "request_header", None)
    header = header_fn() if callable(header_fn) else None
    if isinstance(header, dict):
        system = header.get("system") if isinstance(header.get("system"), str) else None
        cfg = header.get("config")
        config = dict(cfg) if isinstance(cfg, dict) else None
        tls = header.get("tools")
        if isinstance(tls, (list, tuple)):
            tools = [dict(t) for t in tls if isinstance(t, dict)]
    elif header is not None:
        sys_v = getattr(header, "system", None)
        system = sys_v if isinstance(sys_v, str) else None
        cfg_v = getattr(header, "config", None)
        config = dict(cfg_v) if isinstance(cfg_v, dict) else None
        tls_v = getattr(header, "tools", None)
        if isinstance(tls_v, (list, tuple)):
            tools = [dict(t) for t in tls_v if isinstance(t, dict)]
    return messages, system, config, tools


def _merge_history(
    base: list[dict[str, Any]], history_a: Artifact | None
) -> list[dict[str, Any]]:
    if history_a is None:
        return base
    content = history_a.content
    if isinstance(content, list):
        extra = [dict(m) for m in content if isinstance(m, dict)]
        return base + extra if base else extra
    return base


def _merge_user_turn(
    base: list[dict[str, Any]], user_a: Artifact | None
) -> list[dict[str, Any]]:
    if user_a is None:
        return base
    content = user_a.content
    if isinstance(content, dict) and content.get("role"):
        return [*base, dict(content)]
    if isinstance(content, list):
        extra = [dict(m) for m in content if isinstance(m, dict)]
        return [*base, *extra]
    return base


def _overlay_text(base: str | None, art: Artifact | None) -> str | None:
    if art is not None and isinstance(art.content, str) and art.content:
        return art.content
    return base


def _overlay_dict(
    base: dict[str, Any] | None, art: Artifact | None
) -> dict[str, Any] | None:
    if art is not None and isinstance(art.content, dict):
        return dict(art.content)
    return base


def _overlay_tools(
    base: list[dict[str, Any]], art: Artifact | None
) -> list[dict[str, Any]]:
    if art is None:
        return base
    content = art.content
    if isinstance(content, (list, tuple)):
        return [dict(t) for t in content if isinstance(t, dict)]
    return base


def _artifact_list(art: Artifact | None, *, key: str) -> list[dict[str, Any]]:
    if art is None:
        return []
    content = art.content
    if isinstance(content, dict):
        items = content.get(key, content.get("items", []))
        if isinstance(items, list):
            return [dict(x) for x in items if isinstance(x, dict)]
        return []
    if isinstance(content, list):
        return [dict(x) for x in content if isinstance(x, dict)]
    return []


def _artifact_content(art: Artifact | None) -> Any:
    if art is None:
        return None
    return art.content
