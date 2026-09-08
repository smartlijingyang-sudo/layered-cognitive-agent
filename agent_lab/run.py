"""run.py — entry point.

Usage:
  python -m agent_lab.run mv_assemble
  python -m agent_lab.run effect_dispatch
  python -m agent_lab.run agent_loop
  python -m agent_lab.run --negative agent_loop   # compile a graph with a missing project edge

Defaults to agent_loop. Mocks the LLM and tools in-process.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_lab.graphs import load_registry
from agent_lab.nodes.llm import register_llm_provider
from agent_lab.nodes.tool import register_tool
from agent_lab.primitives.artifact import (
    Artifact,
    ArtifactKind,
    make_message,
    make_text,
)
from agent_lab.runtime.runner import run as run_graph

# ---------- Mock providers ------------------------------------------------

def _mock_llm(prompt, **kwargs):
    """Default in-process LLM callable.

    Accepts either a list[dict] of messages (legacy) or a flat prompt
    string (LCA shim form). Returns an assistant text reply.
    """
    if isinstance(prompt, list):
        last_user = next(
            (m["content"] for m in reversed(prompt) if isinstance(m, dict) and m.get("role") == "user"),
            "no user message",
        )
        return f"ack: {last_user}"
    # string prompt — pick last [user] line if present
    last_user = "no user message"
    for line in reversed(prompt.split("\n")):
        if line.startswith("[user]"):
            last_user = line.removeprefix("[user] ").strip()
            break
    return f"ack: {last_user}"


def _mock_tool_echo(args):
    return f"echo({args})"


def _mock_tool_calc(args):
    expr = str(args.get("expr", "0"))
    # Sandboxed eval; prototype only. noqa because mock is intentionally minimal.
    return str(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307


def _register_mocks() -> None:
    register_llm_provider("mock", _mock_llm)
    register_tool("echo", _mock_tool_echo)
    register_tool("calc", _mock_tool_calc)


def _register_lca_mv() -> None:
    """Register LCA's DefaultModelContextAssembler as the agent_lab mv provider.

    Lazy-imported so the framework still boots if lca isn't importable.
    """
    try:
        from agent_lab.adapters.lca_mv import LcaMvProvider
        from agent_lab.nodes.mv import register_lca_mv_provider

        register_lca_mv_provider("lca", LcaMvProvider())
    except Exception as exc:
        print(f"[warn] LCA mv provider not registered: {exc!r}")


def _register_lca_body() -> None:
    """Register LCA's SimpleSafeExecutor + Tool shims as the agent_lab body provider.

    Wires two in-process tools (echo, calc) so the executor has something
    to dispatch. Real apps would register ToolShim objects built from
    concrete LCA Tool implementations.
    """
    try:
        from agent_lab.adapters.lca_body import LcaBodyProvider, ToolShim
        from agent_lab.nodes.tool import register_body_provider

        provider = LcaBodyProvider(allowed_tools=("echo", "calc"))
        provider.register_tool(ToolShim(
            name="echo",
            description="Echo the args back as text.",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            is_idempotent=True,
            effect_kind="ephemeral",
            default_timeout_s=5,
            _callable=_mock_tool_echo,
        ))
        provider.register_tool(ToolShim(
            name="calc",
            description="Evaluate a python arithmetic expression.",
            parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
            is_idempotent=True,
            effect_kind="ephemeral",
            default_timeout_s=5,
            _callable=_mock_tool_calc,
        ))
        register_body_provider("lca", provider)
    except Exception as exc:
        print(f"[warn] LCA body provider not registered: {exc!r}")


def _register_lca_llm() -> None:
    """Register LCA's LLMAdapter Protocol-backed provider."""
    try:
        from agent_lab.adapters.lca_llm import LcaLlmProvider, LlmAdapterShim
        from agent_lab.nodes.llm import register_llm_provider_obj

        adapter = LlmAdapterShim(callable_=_mock_llm)
        register_llm_provider_obj("lca", LcaLlmProvider(adapter))
    except Exception as exc:
        print(f"[warn] LCA llm provider not registered: {exc!r}")


# ---------- Demo runners --------------------------------------------------

def _run_mv_assemble(specs, mv_provider: str = "default") -> None:
    spec = specs["mv_assemble"]
    initial = {
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(kind=ArtifactKind.MESSAGE, content=[
            {"role": "assistant", "content": "previous turn"}
        ], schema_ref="openai.messages.v1"),
        "results": Artifact(kind=ArtifactKind.TEXT, content="result line A\nresult line A\nresult line B", schema_ref="tool.v1"),
        "config": Artifact(kind=ArtifactKind.FACT, content={"temperature": 0.0}, schema_ref="config.v1"),
        "tools": Artifact(kind=ArtifactKind.FACT, content=[
            {"type": "function", "function": {"name": "echo"}}
        ], schema_ref="tools.v1"),
    }
    # Override the assemble_lca node config to use the requested provider.
    if mv_provider != "default":
        for n in spec.nodes:
            if n.id == "assemble_lca":
                n.config["provider"] = mv_provider
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print(f"=== manifest (provider={mv_provider}) ===")
    manifest = trace.final_artifacts.get("manifest")
    lca_manifest = trace.final_artifacts.get("lca_manifest")
    print("--- local commit_manifest:")
    print(json.dumps(manifest.content if manifest else None, indent=2, ensure_ascii=False))
    if lca_manifest is not None:
        print("--- LCA DefaultModelContextAssembler.assemble() output:")
        print(json.dumps(lca_manifest.content, indent=2, ensure_ascii=False))


def _run_effect_dispatch(specs) -> None:
    spec = specs["effect_dispatch"]
    initial = {
        "args": Artifact(kind=ArtifactKind.FACT, content={"text": "hello world"}, schema_ref="tool.args.v1"),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print("=== final outputs ===")
    for k, v in trace.final_artifacts.items():
        print(f"  {k}: kind={v.kind.value} digest={v.short_id()} content={v.content!r}")


def _run_agent_loop(specs) -> None:
    spec = specs["agent_loop"]
    initial = {
        "user_turn": make_message("user", "what is 2+2?", tool_calls=[{"tool": "calc", "args": {"expr": "2+2"}}]),
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(kind=ArtifactKind.MESSAGE, content=[], schema_ref="openai.messages.v1"),
        "results": Artifact(kind=ArtifactKind.TEXT, content=""),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print("=== final outputs ===")
    for k, v in trace.final_artifacts.items():
        print(f"  {k}: kind={v.kind.value} digest={v.short_id()} content={v.content!r}")


def _print_trace(trace) -> None:
    print(f"--- {len(trace.events)} trace events ---")
    for line in trace.to_lines():
        print(json.dumps(line, ensure_ascii=False))


# ---------- Negative compile test -----------------------------------------

def _run_negative() -> None:
    """Build a copy of effect_dispatch with no discard_sink, drop the receipt node's
    'receipt' OUT port and the discard_sink field. Expect a C2/C3 violation.
    """
    src = Path(__file__).parent / "graphs" / "configs" / "effect_dispatch.yaml"
    dst = src.with_suffix(".broken.yaml")
    text = src.read_text(encoding="utf-8")
    broken = text.replace(
        "    config: { from: routed, to: receipt, provider: lca }\n    ins: [routed]\n    outs: [receipt]",
        "    config: { from: routed, to: receipt, provider: lca }\n    ins: [routed]\n    outs: []",
    )
    if broken == text:
        print("FAILED to mutate effect_dispatch.yaml for negative test")
        sys.exit(2)
    dst.write_text(broken, encoding="utf-8")
    try:
        from agent_lab.graph.compile import compile as compile_spec
        from agent_lab.graph.validate import ValidationError
        from agent_lab.graphs import load_spec

        spec = load_spec(dst)
        try:
            compile_spec(spec, sub_registry={})
        except ValidationError as e:
            print(f"OK: negative compile test caught -> {len(e.errors)} invariant violation(s)")
            for err in e.errors[:5]:
                print(f"  - {err}")
            return
        print("FAIL: broken effect_dispatch compiled cleanly (this is wrong)")
        sys.exit(2)
    finally:
        dst.unlink(missing_ok=True)


# ---------- CLI -----------------------------------------------------------

_DISPATCH = {
    "mv_assemble": _run_mv_assemble,
    "effect_dispatch": _run_effect_dispatch,
    "agent_loop": _run_agent_loop,
}


def _describe(target: str | None) -> None:
    """Print self-describing manifests.

    Usage:
      python -m agent_lab.run describe                 # all nodes + graphs
      python -m agent_lab.run describe --target node:redact
      python -m agent_lab.run describe --target graph:agent_loop
    """
    from agent_lab.nodes import NodeRegistry

    if target is None or target == "all":
        # All node manifests
        print("=== Node Manifests ===")
        for node_id in sorted(NodeRegistry.known()):
            m = NodeRegistry.describe(node_id)
            print(f"\n[{node_id}]  {m.name}")
            print(f"  layer={m.layer.value}  kind={m.kind.value}")
            print(f"  description: {m.description}")
            if m.inputs:
                print("  inputs:")
                for p in m.inputs:
                    print(f"    - {p.id} ({p.kind.value}, required={p.required})")
            if m.outputs:
                print("  outputs:")
                for p in m.outputs:
                    print(f"    - {p.id} ({p.kind.value}, required={p.required})")
            if m.provides:
                print(f"  provides: {list(m.provides)}")
            if m.requires:
                print(f"  requires: {list(m.requires)}")
            if m.emits:
                print(f"  emits: {list(m.emits)}")
            if m.consumes:
                print(f"  consumes: {list(m.consumes)}")
            if m.relates_to:
                print(f"  relates_to: {list(m.relates_to)}")
        # All graph manifests
        print("\n\n=== Graph Manifests ===")
        for stem in ("agent_loop", "mv_assemble", "effect_dispatch"):
            from pathlib import Path

            from agent_lab.graphs.loader import load_graph_manifest
            yaml_path = Path(__file__).parent / "graphs" / "configs" / f"{stem}.yaml"
            gm = load_graph_manifest(yaml_path)
            if not gm:
                continue
            print(f"\n[{gm.get('id', stem)}]  layer={gm.get('layer', '?')}")
            print(f"  purpose: {gm.get('purpose', '')}")
            if gm.get("members"):
                print(f"  members: {list(gm['members'])}")
            if gm.get("references"):
                print(f"  references: {list(gm['references'])}")
            if gm.get("relations"):
                for rel in gm["relations"]:
                    print(f"  relation: {rel}")
            if gm.get("capabilities"):
                caps = gm["capabilities"]
                if caps.get("provides"):
                    print(f"  provides: {list(caps['provides'])}")
                if caps.get("requires"):
                    print(f"  requires: {list(caps['requires'])}")
        return

    kind, _, name = target.partition(":")
    if kind == "node":
        m = NodeRegistry.describe(name)
        print(f"[{m.id}] {m.name}")
        print(f"  layer={m.layer.value}  kind={m.kind.value}  description={m.description}")
        print(f"  inputs={[p.id for p in m.inputs]}  outputs={[p.id for p in m.outputs]}")
        print(f"  provides={list(m.provides)}  requires={list(m.requires)}")
        print(f"  emits={list(m.emits)}  consumes={list(m.consumes)}")
        print(f"  relates_to={list(m.relates_to)}")
    elif kind == "graph":
        from pathlib import Path

        from agent_lab.graphs.loader import load_graph_manifest
        yaml_path = Path(__file__).parent / "graphs" / "configs" / f"{name}.yaml"
        gm = load_graph_manifest(yaml_path)
        if not gm:
            print(f"no graph manifest for: {name}")
            return
        print(f"[{gm.get('id')}]  layer={gm.get('layer')}  purpose={gm.get('purpose')}")
        print(f"  members={list(gm.get('members', []))}")
        print(f"  references={list(gm.get('references', []))}")
        print(f"  relations={list(gm.get('relations', []))}")
        print(f"  capabilities={gm.get('capabilities', {})}")
    else:
        print(f"unknown target kind: {kind} (use 'node:<id>' or 'graph:<id>')")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_lab")
    parser.add_argument("graph", nargs="?", default="agent_loop",
                        choices=list(_DISPATCH.keys()),
                        help="which graph to run")
    parser.add_argument("--negative", action="store_true",
                        help="compile a broken copy of agent_loop and expect a ValidationError")
    parser.add_argument("--describe", action="store_true",
                        help="print self-describing node + graph manifests and exit")
    parser.add_argument("--target", default=None,
                        help="describe target: node:<id> | graph:<id>")
    parser.add_argument("--mv-provider", default="default",
                        choices=["default", "mock", "lca"],
                        help="for mv_assemble: which provider feeds assemble_lca node")
    args = parser.parse_args(argv)

    _register_mocks()
    _register_lca_body()
    _register_lca_llm()
    if args.mv_provider == "lca" or args.graph == "mv_assemble":
        _register_lca_mv()
    if args.describe:
        _describe(args.target)
        return 0
    if args.negative:
        _run_negative()
        return 0
    specs = load_registry("mv_assemble", "effect_dispatch", "agent_loop")
    if args.graph == "mv_assemble":
        _DISPATCH[args.graph](specs, args.mv_provider)
    else:
        _DISPATCH[args.graph](specs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
