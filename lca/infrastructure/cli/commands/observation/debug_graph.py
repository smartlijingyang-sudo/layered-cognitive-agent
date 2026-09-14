"""lca-ops debug-graph —— 一次性图 + 数据 + 根因(spine SSOT 直读)。

不依赖 observation-9module bundle 的 facts fan-out,直接读
``<run_id>.spine.jsonl`` 拼出图骨架、每节点真实 payload、reducer 决策序列、
llm 响应、tool_calls、gate verdict,并按可靠性自动标注每一步状态。

设计动机:`observation run-replay` / `explain` 都依赖 `observation.*` facts
经 observation-9module bundle fan-out;reducer 走 ``lifecycle.finally`` 但未
触发 ``RunTerminalizer.terminalize`` 时,``journal.json`` / observation facts
可能缺失,那两个命令返 0 facts。``debug-graph`` 只读 spine(每个 run 收尾
必生成),任何 run 都能出图。

观察面专用(AGENTS.md §2.3),不触发控制面副作用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

_LOG_DEBUG_GRAPH_TAG = "debug-graph"

# 根因启发式:节点 outcome 或 reducer method 含此集合 → 标记 ✗
_FAIL_OUTCOMES = {"fail", "failed", "failure", "error", "rejected"}
_STOP_METHODS = {"apply_stop", "apply_error"}


def _spine_path(run_id: str) -> Path:
    return Path("traces/runs") / run_id / f"{run_id}.spine.jsonl"


def _load_events(run_id: str) -> list[dict[str, Any]]:
    """Read spine.jsonl; missing file returns empty list.

    Kept on raw JSON dicts (not EventRecord) so test fixtures with synthetic
    execution_points can render — debug-graph is the fallback path that must
    work even when the spine contains non-whitelisted EPs.
    """
    from lca.infrastructure.cli.commands._shared.projection import (
        spine_filename_for_run_cwd,
    )

    p = spine_filename_for_run_cwd(run_id)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _classify_node(end_event: dict[str, Any]) -> tuple[str, str]:
    """从 phase_graph.node.end 推 (marker, reason)。marker ∈ {✓, ✗, ~}。"""
    p = end_event.get("payload") or {}
    outcome = str(p.get("outcome") or "").lower()
    error = str(p.get("error") or "")
    if outcome in _FAIL_OUTCOMES or error:
        return "✗", error or outcome
    return "✓", ""


def _truncate(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def _safe_repr(v: Any, n: int = 60) -> str:
    """repr 但抑制 object 地址(`<...object at 0x...>`)和 datetime repr。

    spine.jsonl 里 datetime 是字符串字面量 ``"datetime.datetime(...)"``,
    Python 对象是 ``datetime.datetime(...)``。两种都要识别。
    """
    is_string_dt = isinstance(v, str) and v.startswith("datetime.datetime(")
    r = repr(v)
    # object 地址类: '<abc.Tool_search object at 0x7f...>'
    if "object at 0x" in r:
        return f"<{type(v).__name__}>"
    # datetime repr (对象或字符串字面量)
    if is_string_dt or r.startswith("datetime.datetime("):
        # 字符串字面量: 'datetime.datetime(2026, 9, 14, 12, ...)'  → 抽出 ISO 段
        if is_string_dt:
            # 截到 'tzinfo=...' 之前作为可读摘要
            inner = v[len("datetime.datetime(") : -1]
            return _truncate(inner, n)
        try:
            return v.isoformat()
        except Exception:
            return f"<{type(v).__name__}>"
    return _truncate(r, n)


def _summarize_outputs(outputs: dict[str, Any]) -> list[str]:
    """每个 out key 一行可读摘要(节点真实产出物)。"""
    if not isinstance(outputs, dict):
        return []
    lines: list[str] = []
    for k, v in outputs.items():
        if isinstance(v, dict):
            sub_keys = list(v.keys())[:4]
            sample = []
            for sk in sub_keys:
                sv = v.get(sk)
                if isinstance(sv, (str, int, float, bool)):
                    sample.append(f"{sk}={_safe_repr(sv, 40)}")
                elif isinstance(sv, list):
                    sample.append(f"{sk}=list[{len(sv)}]")
                elif isinstance(sv, dict):
                    sample.append(f"{sk}=dict[{len(sv)}]")
                else:
                    sample.append(f"{sk}={_safe_repr(sv, 30)}")
            lines.append(f"    out.{k} {{ {', '.join(sample)} }}")
        elif isinstance(v, list):
            lines.append(f"    out.{k} = list[{len(v)}]")
        elif isinstance(v, str):
            lines.append(f"    out.{k} = {_safe_repr(v, 80)}")
        else:
            lines.append(f"    out.{k} = {_safe_repr(v, 60)}")
    return lines


def _summarize_response(response: dict[str, Any]) -> list[str]:
    """llm.call.end 的 stream 段或 node out.response 段 —— 拆出 tool_calls / text。"""
    if not isinstance(response, dict):
        return []
    lines: list[str] = []
    if response.get("model"):
        lines.append(f"    model: {response['model']}")
    if "tool_calls" in response and isinstance(response["tool_calls"], list):
        for tc in response["tool_calls"]:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name") or tc.get("tool_name") or "?"
            args = tc.get("arguments") or {}
            if isinstance(args, dict):
                args_str = ", ".join(f"{k}={_truncate(repr(v), 50)}" for k, v in args.items())
            else:
                args_str = _truncate(repr(args), 80)
            lines.append(f"    tool_call: {name}({args_str})")
    elif response.get("text"):
        lines.append(f"    text: {_truncate(response['text'], 160)}")
    if response.get("finish_reason"):
        lines.append(f"    finish_reason: {response['finish_reason']}")
    usage = response.get("usage") or {}
    if isinstance(usage, dict) and usage:
        lines.append(f"    usage: {usage}")
    return lines


def build_debug_graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    """组装一份调试报告 dict(human 渲染和 json 模式共用)。"""
    nodes: list[dict[str, Any]] = []  # graph skeleton
    reduces: list[dict[str, Any]] = []  # reducer 序列
    llms: list[dict[str, Any]] = []  # llm 响应
    lifecycles: list[dict[str, Any]] = []  # kernel.run.stop 等终态
    anomalies: list[str] = []  # 根因标记

    # 1. 节点骨架 —— 把 phase_graph.node.{start, end} 配对
    starts: dict[tuple[str, int], dict[str, Any]] = {}
    ends: dict[tuple[str, int], dict[str, Any]] = {}
    for ev in events:
        ep = ev.get("execution_point") or ""
        node_id = (ev.get("payload") or {}).get("node_id") or ""
        visit = (ev.get("payload") or {}).get("visit_index", 1)
        key = (node_id, visit)
        if ep == "phase_graph.node.start":
            starts[key] = ev
        elif ep == "phase_graph.node.end":
            ends[key] = ev

    for key, end_ev in ends.items():
        node_id, visit = key
        marker, reason = _classify_node(end_ev)
        p = end_ev.get("payload") or {}
        elapsed = p.get("elapsed_ms", 0)
        dispatch = p.get("dispatch", "")
        in_keys = list((p.get("inputs") or {}).keys())
        outputs = p.get("outputs") or {}
        entry = {
            "marker": marker,
            "node_id": node_id,
            "visit": visit,
            "elapsed_ms": elapsed,
            "dispatch": dispatch,
            "input_keys": in_keys,
            "outputs": outputs,
            "reason": reason,
        }
        # 抽出 out.response 里的 tool_calls
        resp = outputs.get("response") if isinstance(outputs, dict) else None
        if isinstance(resp, dict) and "tool_calls" in resp:
            entry["tool_calls"] = resp["tool_calls"]
        if marker == "✗":
            anomalies.append(f"node {node_id} failed: {reason or 'unknown'}")
        nodes.append(entry)

    # 2. reducer 决策序列
    for ev in events:
        if (ev.get("execution_point") or "") != "runtime.reducer.apply":
            continue
        p = ev.get("payload") or {}
        reduces.append(
            {
                "method": p.get("method"),
                "phase": p.get("phase"),
                "outcome": p.get("outcome"),
            }
        )
        if p.get("method") in _STOP_METHODS:
            anomalies.append(f"reducer invoked {p.get('method')} (phase={p.get('phase')})")

    # 3. llm 响应
    for ev in events:
        if (ev.get("execution_point") or "") != "llm.call.end":
            continue
        p = ev.get("payload") or {}
        llms.append(
            {
                "model": p.get("model"),
                "latency_ms": p.get("latency_ms"),
                "prompt_tokens": p.get("prompt_tokens"),
                "completion_tokens": p.get("completion_tokens"),
                "outcome": p.get("outcome"),
                "stream": p.get("stream"),
            }
        )

    # 4. 终态事件
    for ep in ("kernel.run.stop", "agent_loop.iteration.end"):
        for ev in events:
            if (ev.get("execution_point") or "") == ep:
                lifecycles.append({"ep": ep, "payload": ev.get("payload") or {}})
                p = ev.get("payload") or {}
                if ep == "kernel.run.stop":
                    outcome = str(p.get("outcome") or "").lower()
                    if outcome in _FAIL_OUTCOMES:
                        anomalies.append(f"kernel.run.stop outcome={outcome}")

    return {
        "node_count": len(nodes),
        "nodes": nodes,
        "reducer_sequence": reduces,
        "llm_calls": llms,
        "lifecycle": lifecycles,
        "anomalies": anomalies,
    }


def render_human(report: dict[str, Any], run_id: str) -> str:
    """人读渲染 —— 第一列 marker, 第二列节点名 + dispatch + elapsed, 之后 input/output 摘要。"""
    out: list[str] = []
    out.append(f"=== debug-graph run_id={run_id} ===")
    out.append(f"nodes={report['node_count']}  "
               f"reducer_steps={len(report['reducer_sequence'])}  "
               f"llm_calls={len(report['llm_calls'])}  "
               f"anomalies={len(report['anomalies'])}")
    out.append("")

    # 图骨架
    out.append("─── graph skeleton ───")
    for n in report["nodes"]:
        line = f"  {n['marker']} {n['node_id']:35s} {n['dispatch']:9s} {n['elapsed_ms']:>6d}ms"
        if n["marker"] == "✗":
            line += f"   ← {n['reason']}"
        out.append(line)
    out.append("")

    # reducer 序列
    if report["reducer_sequence"]:
        out.append("─── reducer apply_* sequence ───")
        for r in report["reducer_sequence"]:
            mark = "✗" if r["method"] in _STOP_METHODS else "·"
            out.append(f"  {mark} {r['method']:30s} phase={r['phase']!s:8s} outcome={r['outcome']}")
        out.append("")

    # llm 响应
    if report["llm_calls"]:
        out.append("─── llm.call.end ───")
        for i, lc in enumerate(report["llm_calls"], 1):
            out.append(f"  call #{i}: model={lc.get('model')}  "
                       f"latency={lc.get('latency_ms')}ms  "
                       f"tokens(prompt={lc.get('prompt_tokens')}, "
                       f"completion={lc.get('completion_tokens')})  "
                       f"outcome={lc.get('outcome')}")
            for line in _summarize_response({"stream": lc.get("stream")}):
                out.append(line)
        out.append("")

    # 每节点详细 output
    out.append("─── node outputs (real payload, auto-truncated) ───")
    for n in report["nodes"]:
        if not n["outputs"]:
            continue
        out.append(f"  {n['node_id']}  in_keys={n['input_keys']}")
        for line in _summarize_outputs(n["outputs"]):
            out.append(line)
        # tool_calls 单列
        for tc in n.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name") or tc.get("tool_name") or "?"
            args = tc.get("arguments") or {}
            if isinstance(args, dict):
                args_str = ", ".join(f"{k}={_safe_repr(v, 60)}" for k, v in args.items())
            else:
                args_str = _truncate(repr(args), 100)
            out.append(f"    tool_call: {name}({args_str})")
    out.append("")

    # 根因
    if report["anomalies"]:
        out.append("─── root-cause markers ───")
        for a in report["anomalies"]:
            out.append(f"  ✗ {a}")
        out.append("")

    # 终态
    if report["lifecycle"]:
        out.append("─── lifecycle ───")
        for lc in report["lifecycle"]:
            out.append(f"  {lc['ep']}: {json.dumps(lc['payload'], ensure_ascii=False, default=str)[:200]}")

    return "\n".join(out)


def register(app: typer.Typer) -> None:
    """挂到 ``lca-ops observation debug-graph`` 子命令。"""

    @app.command(
        name="debug-graph",
        help=(
            "一次性图骨架 + 每节点 input/output 真实 payload + reducer 决策 + "
            "llm 响应 + 自动根因标记。直读 spine SSOT,不依赖 observation "
            "bundle fan-out。"
        ),
    )
    def debug_graph_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        json_mode: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
    ) -> None:
        events = _load_events(run_id)
        if not events:
            typer.echo(f"no spine at {_spine_path(run_id)}", err=True)
            raise typer.Exit(code=1)
        report = build_debug_graph(events)
        if json_mode:
            typer.echo(json.dumps({"run_id": run_id, **report}, ensure_ascii=False, indent=2, default=str))
        else:
            typer.echo(render_human(report, run_id))


def debug_graph_command(run_id: str, as_json: bool = False) -> None:
    """供顶层 alias (``lca-ops debug-graph``) 复用的实函数。"""
    events = _load_events(run_id)
    if not events:
        typer.echo(f"no spine at {_spine_path(run_id)}", err=True)
        raise typer.Exit(code=1)
    report = build_debug_graph(events)
    if as_json:
        typer.echo(json.dumps({"run_id": run_id, **report}, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(render_human(report, run_id))


__all__ = ["build_debug_graph", "debug_graph_command", "register"]
