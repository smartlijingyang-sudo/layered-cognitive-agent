"""run.py — entry point.

Usage:
  python -m agent_lab.run model_eye
  python -m agent_lab.run act
  python -m agent_lab.run agent_loop
  python -m agent_lab.run --negative
  python -m agent_lab.run --describe [--target node:<id>|graph:<id>]

Defaults to agent_loop. Tool dispatch is driven by
``agent_lab/tools/registry.yaml`` (the named-tool inventory); the LLM
is driven by graph config and reads its secrets from the env
(``LLM_API_KEY`` / ``LLM_MODEL`` / ``LLM_BASE_URL``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_lab.graphs import load_graph_manifest, load_registry
from agent_lab.primitives.artifact import (
    Artifact,
    ArtifactKind,
    make_message,
    make_text,
)
from agent_lab.runtime.runner import run as run_graph

# ---------- Boot ---------------------------------------------------------


def _bootstrap() -> None:
    """Eagerly load .env (for LLM secrets) and the tool registry, then wire
    the registry into the dispatch nodes.

    This is the only place the registry is loaded.  Act execute (and the
    legacy dispatch_tool singleton) share it via configure_registry.
    """
    # Load project .env if present so OpenAICompatAdapter can read
    # LLM_API_KEY / LLM_MODEL / LLM_BASE_URL out of the environment.
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except Exception:  # noqa: S110 — missing .env is fine, env is the fallback
        pass

    from agent_lab.nodes.act.execute.plugin import configure_registry
    from agent_lab.nodes.act.execute.runtime_bind import ensure_act_runtime
    from agent_lab.tools import ToolRegistry
    from lca.plugins.lab.internal.loader import load_all

    registry = ToolRegistry()
    registry.load_from_yaml(Path(__file__).parent / "tools" / "registry.yaml")
    configure_registry(registry)
    ensure_act_runtime()
    load_all()


def _register_lca_mv() -> None:
    """No-op kept for backwards compatibility with --mv-provider flags."""


# ---------- Demo runners --------------------------------------------------


def _run_model_eye(specs, mv_provider: str = "default") -> None:
    del mv_provider  # reserved; model_eye has no alternate provider path
    spec = specs["model_eye"]
    initial = {
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(
            kind=ArtifactKind.MESSAGE,
            content=[{"role": "assistant", "content": "previous turn"}],
            schema_ref="openai.messages.v1",
        ),
        "context_manifest": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "items": [
                    {
                        "kind": "clock",
                        "payload": "2026-09-08 Monday",
                        "provenance": "clock_sensor",
                    }
                ],
                "digest": "demo",
                "schema_version": "1.0",
            },
            schema_ref="context.manifest.v1",
        ),
        "user_turn": Artifact(
            kind=ArtifactKind.MESSAGE,
            content={"role": "user", "content": "hello"},
            schema_ref="openai.message.v1",
        ),
        "observation": Artifact(
            kind=ArtifactKind.TEXT,
            content="tool said ok",
            schema_ref="tool.v1",
        ),
        "config": Artifact(
            kind=ArtifactKind.FACT, content={"temperature": 0.0}, schema_ref="config.v1"
        ),
        "tools": Artifact(
            kind=ArtifactKind.FACT,
            content=[{"type": "function", "function": {"name": "read_file"}}],
            schema_ref="tools.v1",
        ),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print("=== ContextManifest (model_eye.freeze) ===")
    manifest = trace.final_artifacts.get("manifest")
    print(json.dumps(manifest.content if manifest else None, indent=2, ensure_ascii=False))


def _run_act(specs) -> None:
    spec = specs["act"]
    # Demo: Decision(call_tool=read_file) against this very file.
    demo_path = str(Path(__file__).resolve())
    initial = {
        "decision": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_demo",
                "action_type": "call_tool",
                "tool_calls": [
                    {
                        "call_id": "c1",
                        "name": "read_file",
                        "arguments": {"path": demo_path, "max_bytes": 256},
                    }
                ],
                "rationale": "demo",
                "confidence": 1.0,
            },
            schema_ref="decision.v1",
        ),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print("=== final outputs ===")
    for k, v in trace.final_artifacts.items():
        print(f"  {k}: kind={v.kind.value} digest={v.short_id()} content={v.content!r}")


def _run_agent_loop(specs) -> None:
    spec = specs["agent_loop"]
    # Demo turn: perceive → think → act → reflect → remember (+ stop control).
    initial = {
        "user_turn": make_message(
            "user",
            "please run `bash -c 'echo hi from real bash'`",
            tool_calls=[],
        ),
        "state": Artifact(
            kind=ArtifactKind.FACT,
            content={"trace_id": "demo", "task": "bash echo", "step": 0},
            schema_ref="agent.state.v1",
        ),
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
    """Strip execute's receipt OUT port from act.yaml; expect a validation error."""
    src = Path(__file__).parent / "graphs" / "configs" / "act.yaml"
    dst = src.with_suffix(".broken.yaml")
    text = src.read_text(encoding="utf-8")
    broken = text.replace(
        "    ins: [authorized]\n    outs: [receipt]",
        "    ins: [authorized]\n    outs: []",
    )
    if broken == text:
        print("FAILED to mutate act.yaml for negative test")
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
        print("FAIL: broken act compiled cleanly (this is wrong)")
        sys.exit(2)
    finally:
        dst.unlink(missing_ok=True)


# ---------- CLI -----------------------------------------------------------

_DISPATCH = {
    "model_eye": _run_model_eye,
    "act": _run_act,
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
        for stem in ("agent_loop", "model_eye", "act", "perceive", "think"):
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
        # Tool registry
        from agent_lab.tools import ToolRegistry

        reg = ToolRegistry()
        try:
            reg.load_from_yaml(Path(__file__).parent / "tools" / "registry.yaml")
        except Exception as exc:  # pragma: no cover
            print(f"\n[tool registry] load failed: {exc!r}")
        else:
            print("\n\n=== Tool Registry ===")
            for n in reg.names():
                t = reg.get(n)
                print(f"\n[{n}]  ({type(t).__module__}.{type(t).__name__})")
                print(f"  description: {getattr(t, 'description', '')}")
                print(f"  is_idempotent={getattr(t, 'is_idempotent', '?')}")
                print(f"  default_timeout_s={getattr(t, 'default_timeout_s', '?')}")
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
    parser.add_argument(
        "graph",
        nargs="?",
        default="agent_loop",
        choices=list(_DISPATCH.keys()),
        help="which graph to run",
    )
    parser.add_argument(
        "--negative",
        action="store_true",
        help="compile a broken copy of act and expect a ValidationError",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print self-describing node + graph + tool manifests and exit",
    )
    parser.add_argument("--target", default=None, help="describe target: node:<id> | graph:<id>")
    parser.add_argument(
        "--mv-provider",
        default="default",
        choices=["default", "lca"],
        help="for model_eye: which provider feeds assemble_lca node",
    )
    args = parser.parse_args(argv)

    if args.describe:
        _describe(args.target)
        return 0
    if args.negative:
        _run_negative()
        return 0

    # Real boot: load the tool registry before any graph runs.
    _bootstrap()
    if args.mv_provider == "lca" or args.graph == "model_eye":
        _register_lca_mv()
    specs = load_registry(
        "perceive", "model_eye", "act", "agent_loop", "think", "reflect", "remember"
    )
    if args.graph == "model_eye":
        _DISPATCH[args.graph](specs, args.mv_provider)
    else:
        _DISPATCH[args.graph](specs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
