"""Driver-level debug commands (post-mortem of think subgraph flow).

落地自 ADR-0220 P10 之后的几次真实 run 调试经验 —— 把"通过 stderr 抓 driver 日志"
这条临时路径压成 CLI 命令,让 agent 或人拿一个 run_id 就能复现节点执行链。

四条命令:
  lca-ops debug-credentials                 验 .env / LLM adapter 形态
  lca-ops debug-factories <profile>          验 plan spec factory 解析
  lca-ops debug-driver-chain <run_id>        从 stderr 还原节点链路
  lca-ops debug-short-circuits               当前 kernel stderr 里的 fail-loud 信号
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.commands.kernel._shared import emit_report


@dataclass(frozen=True)
class DriverLogEntry:
    """One row from the kernel stderr driver log stream."""

    ts: str
    event: str
    fields: dict[str, Any] = field(default_factory=dict)


# ── log parsing ────────────────────────────────────────────────────────

_LOG_PREFIX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"\[(?P<level>\w+)\s*\]\s+"
    r"(?P<logger>[\w\.]+)\s+"
    r"(?P<event>phase_graph\.\S+)\s*(?P<rest>.*)$"
)


def parse_driver_stderr(stderr_path: Path) -> list[DriverLogEntry]:
    """Parse ``phase_graph.*`` lines out of one kernel stderr log."""
    out: list[DriverLogEntry] = []
    if not stderr_path.is_file():
        return out
    pattern = re.compile(r"phase_graph\.(?P<event>\S+)\s*(?P<rest>.*)$")
    for line in stderr_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "phase_graph." not in line:
            continue
        m = pattern.search(line)
        if not m:
            continue
        ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
        ts = ts_match.group(1) if ts_match else ""
        rest = m.group("rest").strip()
        fields = _parse_kv(rest)
        out.append(DriverLogEntry(ts=ts, event=f"phase_graph.{m.group('event')}", fields=fields))
    return out


def _parse_kv(rest: str) -> dict[str, Any]:
    """Parse ``key=value`` pairs (with quoted string support) from a log tail."""
    fields: dict[str, Any] = {}
    i = 0
    while i < len(rest):
        while i < len(rest) and rest[i] == " ":
            i += 1
        if i >= len(rest):
            break
        eq = rest.find("=", i)
        if eq < 0:
            break
        key = rest[i:eq]
        i = eq + 1
        if i < len(rest) and rest[i] == "'":
            end = rest.find("'", i + 1)
            if end < 0:
                fields[key] = rest[i:]
                break
            fields[key] = rest[i + 1 : end]
            i = end + 1
        else:
            end = i
            while end < len(rest) and rest[end] != " ":
                end += 1
            fields[key] = rest[i:end]
            i = end
    return fields


# ── kernel stderr discovery ───────────────────────────────────────────

def find_stderr_for_run(run_id: str) -> Path | None:
    """Best-effort: find the kernel stderr file that contains this run's events.

    Two strategies (first match wins):
    1. Grep each candidate stderr for ``run_id=<run_id>`` in any
       ``runtime_lifecycle journal_sequence=None lifecycle_event=started`` line.
       This is exact but slow.
    2. Fall back to closest mtime to ``manifest.started_at``.
    """
    trace_dir = Path("traces/runs") / run_id
    manifest = trace_dir / "manifest.json"
    started_at: float | None = None
    if manifest.is_file():
        try:
            started_at = json.loads(manifest.read_text(encoding="utf-8")).get("started_at")
        except Exception:
            started_at = None
    candidates = sorted(glob.glob("/tmp/lca-kernel.stderr.*.log"))
    if not candidates:
        return None
    # Strategy 1: exact run_id match in stderr body.
    needle_run = f"run_id={run_id}"
    needle_trace = None
    if manifest.is_file():
        try:
            needle_trace = json.loads(manifest.read_text(encoding="utf-8")).get("trace_id")
        except Exception:
            needle_trace = None
    for path in candidates:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if needle_run in text and (needle_trace is None or needle_trace in text):
            return Path(path)
    # Strategy 2: mtime fallback.
    if started_at is None:
        return Path(candidates[-1])
    target = float(started_at)
    best = min(candidates, key=lambda p: abs(os.path.getmtime(p) - target))
    return Path(best)


def find_latest_kernel_stderr() -> Path | None:
    """Most recently modified kernel stderr file (current kernel process)."""
    candidates = sorted(glob.glob("/tmp/lca-kernel.stderr.*.log"), key=os.path.getmtime)
    return Path(candidates[-1]) if candidates else None


# ── command implementations ──────────────────────────────────────────

def cmd_debug_credentials(json_mode: bool) -> None:
    """Verify .env load + LLM adapter resolve end-to-end (no kernel needed)."""
    from lca.infrastructure.llm.config import (
        load_provider_settings,
        llm_credentials,
        llm_openai_credentials,
        normalize_llm_environ,
        prepare_llm_environ,
    )

    prepare_llm_environ()
    normalize_llm_environ()
    settings = load_provider_settings()
    env_snapshot = {
        "LLM_API_KEY": "present" if os.environ.get("LLM_API_KEY") else "absent",
        "LLM_BASE_URL": os.environ.get("LLM_BASE_URL"),
        "LLM_MODEL": os.environ.get("LLM_MODEL"),
        "LLM_API_STYLE": os.environ.get("LLM_API_STYLE"),
    }
    agent_key, agent_base, agent_model = llm_credentials()
    openai_key, openai_base, openai_model = llm_openai_credentials()
    adapter: Any = None
    adapter_info: dict[str, Any] = {"resolved": False}
    if agent_key:
        try:
            from lca.infrastructure.llm.resolver import ProductionLLMResolver

            resolver = ProductionLLMResolver(
                api_key=agent_key,
                base_url=agent_base,
                default_model=agent_model,
                api_style=os.environ.get("LLM_API_STYLE"),
            )
            adapter = resolver.resolve()
            adapter_info = {
                "resolved": True,
                "type": type(adapter).__name__,
                "model": getattr(adapter, "_model", None) or getattr(adapter, "model", None),
                "base_url": (
                    getattr(adapter, "_base_url", None)
                    or getattr(adapter, "base_url", None)
                ),
                "api_style": (
                    str(getattr(adapter, "_api", None) or getattr(adapter, "api", None))
                    if (getattr(adapter, "_api", None) or getattr(adapter, "api", None))
                    else None
                ),
                "_strategy": type(getattr(adapter, "_strategy", None)).__name__
                if getattr(adapter, "_strategy", None)
                else None,
            }
        except Exception as exc:
            adapter_info = {"resolved": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        adapter_info = {
            "resolved": False,
            "error": "LLM_API_KEY not in env (BOOTSTRAP_PREFIXES includes LLM_; "
            "check .env at cwd or pass via Profile {from_env})",
        }
    report = {
        "env": env_snapshot,
        "agent_face_credentials": {
            "api_key_present": bool(agent_key),
            "base_url": agent_base,
            "model": agent_model,
        },
        "openai_compat_face_credentials": {
            "api_key_present": bool(openai_key),
            "base_url": openai_base,
            "model": openai_model,
        },
        "pydantic_settings": {
            "api_key_configured": bool(settings.api_key),
            "model_configured": settings.configured_model(),
            "agent_endpoint_base_url": settings.agent_endpoint().base_url,
        },
        "adapter": adapter_info,
    }
    if json_mode:
        emit_report(report, json_mode=True)
        return
    typer.echo("== debug-credentials ==")
    for k, v in env_snapshot.items():
        typer.echo(f"  env.{k} = {v!r}")
    typer.echo(f"  agent_face.api_key_present = {bool(agent_key)}")
    typer.echo(f"  agent_face.base_url = {agent_base!r}")
    typer.echo(f"  openai_face.api_key_present = {bool(openai_key)}")
    typer.echo(f"  adapter = {adapter_info}")


def _build_factory_index() -> dict[str, list[str]]:
    """Walk plugin directory tree and harvest composite-key ``region::factory``.

    Best-effort static parse: scans ``lca/plugins/**/*.py`` for ``@plugin``
    decorated callables whose args include ``provides=...``. The
    decorator hides provides on the function itself; this walks the
    source text instead.
    """
    import re

    registry: dict[str, list[str]] = {}
    pattern = re.compile(r"provides\s*=\s*\(([^)]*)\)")
    for path in Path("lca/plugins").rglob("*.py"):
        if path.name == "__init__.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in pattern.finditer(text):
            inner = m.group(1)
            for cap_match in re.finditer(r"""['"]([^'"]+::[^'"]+)['"]""", inner):
                cap_str = cap_match.group(1)
                registry.setdefault(cap_str, []).append(path.stem)
                registry.setdefault(f"{cap_str}.ref", []).append(path.stem)
    return registry


def _boot_factory_index(profile: Path) -> dict[str, list[str]]:
    """Boot the profile (if not already) and harvest ``provides`` from resolved tree.

    Falls back to ``_build_factory_index`` (static scan) when the kernel
    cannot boot in this CLI session (port already bound, profile broken,
    etc.). The boot path is what we want — it's the source of truth the
    driver itself uses at runtime.
    """
    import asyncio
    import contextlib

    try:
        from lca.harness.diagnostics.inspect.inspect import inspect_profile_tree

        async def _boot() -> dict[str, list[str]]:
            ctx = await inspect_profile_tree(profile)
            from lca.harness.diagnostics.inspect.inspect import (
                format_capability_graph,
            )

            cap_graph = format_capability_graph(ctx, profile=str(profile))
            out: dict[str, list[str]] = {}
            for node in cap_graph.get("nodes", []):
                for cap in node.get("provides", []) or []:
                    if "::" in cap:
                        out.setdefault(cap, []).append(f"{node['id']}")
                        out.setdefault(f"{cap}.ref", []).append(f"{node['id']}")
            return out

        return asyncio.run(_boot())
    except Exception:
        return _build_factory_index()


def cmd_debug_factories(profile: Path, json_mode: bool) -> None:
    """Resolve every factory referenced in the profile's bundles and report misses.

    Walks the phase graph's ``sub_spec_ref`` references recursively, loading
    each referenced bundle YAML and harvesting factory names. For each
    factory, the registry (built by booting the profile and reading the
    resolved plugin tree's ``provides``) reports which plugin(s) implement
    ``f"{region}::{factory}"``. A ``.ref`` suffix on the graph's factory
    field is tolerated (framework strips it at lookup).
    """
    if not profile.is_file():
        typer.echo(f"Profile not found: {profile}", err=True)
        raise typer.Exit(2)
    from lca.harness.profile.resolve.resolve import resolve_profile
    from lca.harness.composition.plan_compiler import compile_plan

    resolved = resolve_profile(profile)
    plan = compile_plan(resolved)
    factory_index = _boot_factory_index(profile)
    visited: set[str] = set()
    referenced: list[tuple[str, str, str, str, str]] = []  # (bundle, node, factory, region, kind)

    def load_bundle(bundle_path: str) -> dict[str, Any]:
        path = Path(bundle_path)
        if not path.is_file():
            return {}
        try:
            import yaml

            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def walk_bundle(bundle_path: str, depth: int = 0) -> None:
        if bundle_path in visited or depth > 8:
            return
        visited.add(bundle_path)
        spec = load_bundle(bundle_path)
        region = spec.get("region") or ""
        for node in spec.get("nodes", []) or []:
            factory = node.get("factory")
            node_id = node.get("id")
            node_region = node.get("region") or region
            sub_ref = (node.get("config") or {}).get("sub_spec_ref")
            if factory and node_id:
                kind = "sub_spec_ref_delegate" if isinstance(sub_ref, dict) else "executor"
                referenced.append(
                    (bundle_path, node_id, factory, node_region, kind)
                )
            if isinstance(sub_ref, dict) and sub_ref.get("plan_ref"):
                walk_bundle(sub_ref["plan_ref"], depth + 1)

    pg = plan.phase_graph
    if pg is not None:
        for node in pg.nodes:
            sub = getattr(node, "sub_spec_ref", None)
            if sub is not None and getattr(sub, "plan_ref", None):
                walk_bundle(sub.plan_ref)
        for edge in getattr(pg, "edges", []) or []:
            sub = getattr(edge, "subgraph_ref", None)
            if sub is not None and getattr(sub, "plan_ref", None):
                walk_bundle(sub.plan_ref)

    rows: list[dict[str, Any]] = []
    miss_count = 0
    for bundle_path, node_id, factory, region, kind in referenced:
        if kind == "sub_spec_ref_delegate":
            rows.append(
                {
                    "bundle": bundle_path,
                    "node_id": node_id,
                    "factory": factory,
                    "region": region,
                    "status": "delegate",
                    "kind": kind,
                    "note": "sub_spec_ref: factory not resolved at this layer (delegated to inner graph)",
                }
            )
            continue
        if not region:
            rows.append(
                {
                    "bundle": bundle_path,
                    "node_id": node_id,
                    "factory": factory,
                    "region": "",
                    "status": "missing_region",
                }
            )
            miss_count += 1
            continue
        candidates = [f"{region}::{factory}"]
        if factory.endswith(".ref"):
            candidates.append(f"{region}::{factory[:-4]}")
        else:
            candidates.append(f"{region}::{factory}.ref")
        matched = next((factory_index[k] for k in candidates if k in factory_index), None)
        if matched is not None:
            rows.append(
                {
                    "bundle": bundle_path,
                    "node_id": node_id,
                    "factory": factory,
                    "region": region,
                    "status": "ok",
                    "providers": matched,
                    "resolved_key": next(
                        k for k in candidates if k in factory_index
                    ),
                }
            )
        else:
            rows.append(
                {
                    "bundle": bundle_path,
                    "node_id": node_id,
                    "factory": factory,
                    "region": region,
                    "status": "missing",
                    "tried_keys": candidates,
                }
            )
            miss_count += 1
    report = {
        "profile": str(profile),
        "bundles_visited": sorted(visited),
        "total_factories": len(rows),
        "missing": miss_count,
        "rows": rows,
    }
    if json_mode:
        emit_report(report, json_mode=True)
        return
    typer.echo(f"== debug-factories {profile} ==")
    typer.echo(f"  bundles visited: {len(visited)}")
    typer.echo(f"  total factories: {len(rows)} (missing: {miss_count})")
    for row in rows:
        if row["status"] == "ok":
            typer.echo(
                f"  ✓ {row['bundle']}::{row['node_id']} "
                f"({row['resolved_key']})"
            )
        elif row["status"] == "delegate":
            typer.echo(
                f"  ↪ {row['bundle']}::{row['node_id']} factory={row['factory']} "
                f"(sub_spec_ref delegate, no resolve needed)"
            )
        else:
            typer.echo(
                f"  ✗ {row['bundle']}::{row['node_id']} factory={row['factory']} "
                f"region={row['region']!r} tried={row.get('tried_keys')}"
            )


def cmd_debug_driver_chain(run_id: str, json_mode: bool) -> None:
    """Reconstruct the driver node-execution chain from kernel stderr."""
    stderr = find_stderr_for_run(run_id)
    if stderr is None:
        typer.echo(f"No kernel stderr found for run {run_id}", err=True)
        raise typer.Exit(1)
    entries = parse_driver_stderr(stderr)
    # Filter to entries within the run window. We approximate window by
    # started_at ± 5 minutes; if started_at missing, take everything.
    trace_dir = Path("traces/runs") / run_id
    manifest = trace_dir / "manifest.json"
    started_at: float | None = None
    closed_at: float | None = None
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            started_at = data.get("started_at")
            closed_at = data.get("closed_at")
        except Exception:
            pass
    run_id_marker = run_id
    chain: list[DriverLogEntry] = []
    seen_run_marker = started_at is None
    for entry in entries:
        if not seen_run_marker:
            chain.append(entry)
            if run_id_marker in json.dumps(entry.fields):
                seen_run_marker = True
        else:
            chain.append(entry)
    if started_at is not None and closed_at is not None:
        # Refine: only keep entries whose ts is between started_at and closed_at.
        # Kernel stderr timestamps are local time (no TZ marker); started_at /
        # closed_at are unix epoch seconds (UTC). Convert local → epoch via
        # ``datetime.astimezone()`` to avoid naive/aware mixing.
        from datetime import datetime, timezone

        def parse_ts(ts: str) -> float | None:
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
                return dt.replace(tzinfo=datetime.now().astimezone().tzinfo).timestamp()
            except Exception:
                return None

        lo, hi = started_at, closed_at
        chain = [e for e in chain if (parse_ts(e.ts) or 0) >= lo - 1 and (parse_ts(e.ts) or 0) <= hi + 1]
    # Sequence the chain: outer driver.start + loop_iter + node.executing/executed
    # + edge_selected + subgraph close_out. Render as ordered timeline.
    rows: list[dict[str, Any]] = []
    for entry in chain:
        rows.append({"ts": entry.ts, "event": entry.event, **entry.fields})
    report = {
        "run_id": run_id,
        "stderr_path": str(stderr),
        "started_at": started_at,
        "closed_at": closed_at,
        "entry_count": len(rows),
        "chain": rows,
    }
    if json_mode:
        emit_report(report, json_mode=True)
        return
    typer.echo(f"== debug-driver-chain {run_id} ==")
    typer.echo(f"  stderr: {stderr}")
    typer.echo(f"  entries: {len(rows)}")
    last_plan: str | None = None
    for row in rows:
        if row.get("plan_ref") and row["plan_ref"] != last_plan:
            typer.echo(f"  ── subgraph {row['plan_ref']} entry={row.get('entry', row.get('current_id','?'))} ──")
            last_plan = row["plan_ref"]
        line = f"  {row['ts']} {row['event']}"
        if row.get("current_id"):
            line += f" current={row['current_id']}"
        if row.get("factory"):
            line += f" factory={row['factory']}"
        if row.get("edge_target") is not None:
            line += f" → {row['edge_target']}"
        if row.get("port_values_keys"):
            line += f" ports={row['port_values_keys']}"
        if row.get("declared_inputs"):
            line += f" inputs={row['declared_inputs']}"
        if row.get("inner_outputs_keys") is not None:
            line += f" inner={row['inner_outputs_keys']}"
        if row.get("projected_keys") is not None:
            line += f" projected={row['projected_keys']}"
        if row.get("error"):
            line += f" ERROR={row['error']}"
        typer.echo(line)


def cmd_debug_short_circuits(json_mode: bool) -> None:
    """Surface fail-loud signals from current kernel stderr."""
    stderr = find_latest_kernel_stderr()
    if stderr is None:
        typer.echo("No kernel stderr found under /tmp/lca-kernel.stderr.*", err=True)
        raise typer.Exit(1)
    text = stderr.read_text(encoding="utf-8", errors="replace")
    short_circuits: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for line in text.splitlines():
        if "phase_graph.node.short_circuit" in line:
            short_circuits.append(_parse_lca_log_line(line))
        elif "factory_resolution_failed" in line:
            failures.append(_parse_lca_log_line(line))
        elif "loop_overflow" in line:
            failures.append(_parse_lca_log_line(line))
    report = {
        "stderr_path": str(stderr),
        "short_circuit_count": len(short_circuits),
        "factory_resolution_failed_count": len(failures),
        "short_circuits": short_circuits,
        "failures": failures,
    }
    if json_mode:
        emit_report(report, json_mode=True)
        return
    typer.echo(f"== debug-short-circuits {stderr} ==")
    typer.echo(f"  short_circuit: {len(short_circuits)}")
    for row in short_circuits:
        typer.echo(
            f"    ⚠ {row.get('node_id')} factory={row.get('factory')} "
            f"missing_inputs={row.get('missing_inputs')} "
            f"declared_outputs={row.get('declared_outputs')}"
        )
    typer.echo(f"  factory_resolution_failed: {len(failures)}")
    for row in failures:
        typer.echo(
            f"    ✗ {row.get('node_id')} factory={row.get('factory')} "
            f"region={row.get('region')} exc={row.get('exc')}"
        )


def _parse_lca_log_line(line: str) -> dict[str, Any]:
    """Best-effort parse of one ``[...] message ... key=value`` log line."""
    m = re.match(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\[\s*\w+\s*\]\s+\S+\s+(?P<rest>.*)$",
        line,
    )
    if not m:
        return {}
    rest = m.group("rest")
    out = {"ts": m.group("ts"), "message": rest.split("plan_ref")[0].strip()}
    out.update(_parse_kv(rest))
    return out


def register(app: typer.Typer) -> None:
    """Register driver-debug commands."""

    @app.command(name="debug-credentials")
    def debug_credentials_cmd(
        json_mode: bool = typer.Option(False, "--json"),
    ) -> None:
        """Verify .env load + LLM adapter resolve end-to-end (no kernel boot)."""
        cmd_debug_credentials(json_mode)

    @app.command(name="debug-factories")
    def debug_factories_cmd(
        profile: Path = typer.Option(
            Path("profiles/web-standard.yaml"),
            "--profile",
            "-p",
            help="Profile YAML to inspect",
        ),
        json_mode: bool = typer.Option(False, "--json"),
    ) -> None:
        """Resolve every factory referenced in the profile's bundles."""
        cmd_debug_factories(profile, json_mode)

    @app.command(name="debug-driver-chain")
    def debug_driver_chain_cmd(
        run_id: str = typer.Argument(..., help="Run id"),
        json_mode: bool = typer.Option(False, "--json"),
    ) -> None:
        """Reconstruct the driver node-execution chain from kernel stderr."""
        cmd_debug_driver_chain(run_id, json_mode)

    @app.command(name="debug-short-circuits")
    def debug_short_circuits_cmd(
        json_mode: bool = typer.Option(False, "--json"),
    ) -> None:
        """Surface fail-loud signals from the current kernel stderr."""
        cmd_debug_short_circuits(json_mode)
