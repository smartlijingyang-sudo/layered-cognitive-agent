"""run.py — entry point.

Usage:
  python -m agent_lab.run mv_assemble
  python -m agent_lab.run effect_dispatch
  python -m agent_lab.run agent_loop
  python -m agent_lab.run --negative effect_dispatch
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

    This is the only place the registry is loaded.  The dispatch nodes
    access it via the singleton exposed in
    :mod:`agent_lab.nodes.tool.dispatch_tool`.
    """
    # Load project .env if present so OpenAICompatAdapter can read
    # LLM_API_KEY / LLM_MODEL / LLM_BASE_URL out of the environment.
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except Exception:  # noqa: S110 — missing .env is fine, env is the fallback
        pass

    from agent_lab.nodes.tool import configure_registry
    from agent_lab.tools import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(Path(__file__).parent / "tools" / "registry.yaml")
    configure_registry(registry)


def _register_lca_mv() -> None:
    """Register LCA's DefaultModelContextAssembler as the agent_lab mv provider.

    Lazy-imported so the framework still boots if lca isn't importable.
    """
    try:
        from agent_lab.adapters.lca_mv import LcaMvProvider
        from agent_lab.nodes.mv import register_lca_mv_provider

        register_lca_mv_provider("lca", LcaMvProvider())
    except Exception as exc:  # pragma: no cover
        print(f"[warn] LCA mv provider not registered: {exc!r}")


# ---------- Demo runners --------------------------------------------------


def _run_mv_assemble(specs, mv_provider: str = "default") -> None:
    spec = specs["mv_assemble"]
    initial = {
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(
            kind=ArtifactKind.MESSAGE,
            content=[{"role": "assistant", "content": "previous turn"}],
            schema_ref="openai.messages.v1",
        ),
        "results": Artifact(
            kind=ArtifactKind.TEXT,
            content="result line A\nresult line A\nresult line B",
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
    if mv_provider != "default":
        for n in spec.nodes:
            if n.id == "assemble_lca":
                n.config["provider_kind"] = mv_provider
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
    # Demo call: a real read_file against this very file. The whole point
    # is that the dispatch graph talks to the real LCA Tool, not a stub.
    demo_path = str(Path(__file__).resolve())
    initial = {
        "args": Artifact(
            kind=ArtifactKind.FACT,
            content={"tool": "read_file", "args": {"path": demo_path, "max_bytes": 256}},
            schema_ref="tool.args.v1",
        ),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    print("=== final outputs ===")
    for k, v in trace.final_artifacts.items():
        print(f"  {k}: kind={v.kind.value} digest={v.short_id()} content={v.content!r}")


def _run_agent_loop(specs) -> None:
    spec = specs["agent_loop"]
    # Demo turn: tell the LLM to call bash; the agent loop will go
    # through flatten_manifest → call_llm → parse_decision → think →
    # act (effect_dispatch) → mv_assemble.classify → ... → stop.
    # The bash call will actually run unless LLM_API_KEY is missing, in
    # which case OpenAICompatAdapter will surface the auth error in the
    # receipt (this is the real-failure path, not a hidden mock).
    initial = {
        "user_turn": make_message(
            "user",
            "please run `bash -c 'echo hi from real bash'`",
            tool_calls=[],
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
    """Build a copy of effect_dispatch with no discard_sink, drop the receipt node's
    'receipt' OUT port and the discard_sink field. Expect a C2/C3 violation.
    """
    src = Path(__file__).parent / "graphs" / "configs" / "effect_dispatch.yaml"
    dst = src.with_suffix(".broken.yaml")
    text = src.read_text(encoding="utf-8")
    broken = text.replace(
        "    ins: [routed]\n    outs: [receipt]",
        "    ins: [routed]\n    outs: []",  # strip receipt out port to trigger C6
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
        help="compile a broken copy of effect_dispatch and expect a ValidationError",
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
        help="for mv_assemble: which provider feeds assemble_lca node",
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
    if args.mv_provider == "lca" or args.graph == "mv_assemble":
        _register_lca_mv()
    specs = load_registry("mv_assemble", "effect_dispatch", "agent_loop")
    if args.graph == "mv_assemble":
        _DISPATCH[args.graph](specs, args.mv_provider)
    else:
        _DISPATCH[args.graph](specs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
