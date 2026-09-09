"""Invoke a graph worker without agent_lab.nodes.

PR-D deleted ``agent_lab/nodes``. Hosts are builtins (``graph.call`` /
``identity``). Other factories resolve through the Worker registry;
missing execute implementations fail loud instead of importing deleted
modules.
"""

from __future__ import annotations

from typing import Any

from agent_lab.graph.spec import InfoNode
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_HOST = frozenset({"graph.call", "identity", "passthrough__identity"})


def _has_dataclass_fields(obj: Any) -> bool:
    """True if obj is a dataclass instance (typed worker output)。"""
    return hasattr(obj, "__dataclass_fields__") and not isinstance(obj, type)


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """dataclass → dict,递归 nested dataclass / list[dataclass]。"""
    import dataclasses

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    return obj


def _to_dict(obj: Any) -> Any:
    return _dataclass_to_dict(obj)


def _passthrough(node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
    empty = Artifact(kind=ArtifactKind.TEXT, content="")
    outs = {port: inputs.get(port, empty) for port in node.outs}
    cfg = node.config or {}
    src = cfg.get("from")
    dst = cfg.get("to")
    if src in inputs and dst in (node.outs or [dst]):
        if dst:
            outs[dst] = inputs[src]
    return outs


def invoke(
    node: InfoNode,
    inputs: dict[str, Artifact],
    seams: Any = None,
) -> dict[str, Artifact]:
    """Dispatch ``node.factory`` to its registered worker marker.

    Stage workers register under ``lab.<stage>.<basename>`` via the loader's
    ``bind_worker`` reflection; missing markers fall back to host passthrough
    for the small set of builtin factories (``graph.call`` / ``identity``).
    """
    from lca.plugins.lab.internal.loader import load_all, _LAB_HOOKS

    load_all()
    marker = _LAB_HOOKS.get(node.factory)
    if marker is None or "worker_fn" not in marker:
        # 无反射 worker:host passthrough(``identity``-like)或 fail-loud。
        if node.factory in _HOST:
            return _passthrough(node, inputs)
        raise KeyError(
            f"factory {node.factory!r} has no reflected worker_fn marker; "
            "agent_lab invoke expects every plugin to expose a typed worker_fn."
        )
    cfg = dict(node.config or {})
    # config-only 参数(不进 requires)从 node.config 读取
    for cp in marker.get("config_params", []):
        if cp in cfg:
            inputs = {**inputs, cp: cfg[cp]}
    # ADR-0211 §7:port_name → param_name 重写(来自 docstring ``in:`` 映射)。
    port_to_param = marker.get("port_to_param") or {}
    mapped_inputs: dict[str, Any] = {}
    for port_name, value in inputs.items():
        param_name = port_to_param.get(port_name, port_name)
        mapped_inputs[param_name] = value
    result = marker["worker_fn"](**mapped_inputs)
    # worker 返回 typed dataclass(单 out_port)或 dict[str, Artifact](多 out_port);
    # framework 只接受 dict[str, Artifact]——typed dataclass 自动包成 Artifact。
    from agent_lab.primitives.artifact import Artifact, ArtifactKind
    # out_port 命名:graph spec node.outs[0] 优先(框架的 port 命名空间);
    # marker.outputs[0] 是反射时的语义 port 名。优先用 graph spec 的 out。
    graph_outs = list(node.outs or [])
    default_out = (
        graph_outs[0]
        if graph_outs
        else (marker.get("outputs", (("out",),))[0][0] if marker.get("outputs") else "out")
    )
    if isinstance(result, dict):
        wrapped: dict[str, Artifact] = {}
        for k, v in result.items():
            if isinstance(v, Artifact):
                wrapped[k] = v
            else:
                wrapped[k] = Artifact(
                    kind=ArtifactKind.FACT,
                    content=_dataclass_to_dict(v) if _has_dataclass_fields(v) else {"value": v},
                )
        return wrapped
    if isinstance(result, Artifact):
        return {default_out: result}
    return {
        default_out: Artifact(
            kind=ArtifactKind.FACT,
            content=_dataclass_to_dict(result) if _has_dataclass_fields(result) else {"value": result},
        )
    }
