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

def _mock_llm(messages):
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "no user message",
    )
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


# ---------- Demo runners --------------------------------------------------

def _run_mv_assemble(specs) -> None:
    spec = specs["mv_assemble"]
    initial = {
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(kind=ArtifactKind.MESSAGE, content=[
            {"role": "assistant", "content": "previous turn"}
        ], schema_ref="openai.messages.v1"),
        "results": Artifact(kind=ArtifactKind.TEXT, content="result line A\nresult line A\nresult line B", schema_ref="tool.v1"),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    _print_trace(trace)
    manifest = trace.final_artifacts.get("manifest")
    print("=== final manifest content ===")
    print(json.dumps(manifest.content if manifest else None, indent=2, ensure_ascii=False))


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
        "    config: { from: routed, to: receipt }\n    ins: [routed]\n    outs: [receipt]",
        "    config: { from: routed, to: receipt }\n    ins: [routed]\n    outs: []",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_lab")
    parser.add_argument("graph", nargs="?", default="agent_loop",
                        choices=list(_DISPATCH.keys()),
                        help="which graph to run")
    parser.add_argument("--negative", action="store_true",
                        help="compile a broken copy of agent_loop and expect a ValidationError")
    args = parser.parse_args(argv)

    _register_mocks()
    if args.negative:
        _run_negative()
        return 0
    specs = load_registry("mv_assemble", "effect_dispatch", "agent_loop")
    _DISPATCH[args.graph](specs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
