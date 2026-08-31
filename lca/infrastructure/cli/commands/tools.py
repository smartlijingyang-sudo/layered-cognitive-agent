"""Coding agent tool commands (ADR-0065 §六 / PR-9).

9 read-only CLI wrappers over ``coding_agent_tools/`` implementations:
trace, explain, optimize, graph-run, minimal-repro, diff-context,
diff-runs, cost, evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import emit_report, resolve_journal_path


def register(app: typer.Typer) -> None:
    """Register coding-agent tool commands on the typer app."""

    @app.command(name="trace")
    def trace(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(  # noqa: B008
            None, "--jsonl", help="journal.jsonl 路径(默认 traces/lca_journal.jsonl)"
        ),
        json_mode: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
        focus: str = typer.Option("all", "--focus", help="焦点:all / llm / tools / delegation"),
        depth: int = typer.Option(24, "--depth", help="事件深度"),
    ) -> None:
        """检查一个 run 的 journal 轨迹(只读)。"""
        from lca.plugins.tools.diagnostics.trace_inspector_tool import (
            TraceInspectorToolAdapter,
        )

        path = resolve_journal_path(jsonl, run_id)
        report = TraceInspectorToolAdapter(path).inspect_trace(
            run_id=run_id, focus=focus, depth=depth
        )
        emit_report(report, json_mode=json_mode)

    @app.command(name="explain")
    def explain(
        target: str = typer.Argument(..., help="Run id, or control"),
        slot: str | None = typer.Argument(
            None, help="Semantic phase (only when target is control)"
        ),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
        depth: int = typer.Option(24, "--depth"),
        profile: Path = typer.Option(  # noqa: B008
            Path("profiles/web-standard.yaml"),
            "--profile",
            "-p",
            help="Profile YAML for explain declarative control",
        ),
    ) -> None:
        """Explain a run failure or compiled declarative controls for one phase."""
        if target == "plan":
            selected_profile = Path(slot) if slot is not None else profile
            if not selected_profile.exists():
                print(f"Profile not found: {selected_profile}", file=sys.stderr)
                raise typer.Exit(2)
            from lca.infrastructure.cli.commands.declarative import explain_declarative_plan

            try:
                report = explain_declarative_plan(selected_profile)
            except (TypeError, ValueError) as exc:
                print(f"explain plan: {exc}", file=sys.stderr)
                raise typer.Exit(2) from exc
            emit_report(report, json_mode=json_mode)
            raise typer.Exit(0)

        if target == "control":
            if slot is None:
                print("explain control requires <semantic-phase>", file=sys.stderr)
                raise typer.Exit(2)
            if not profile.exists():
                print(f"Profile not found: {profile}", file=sys.stderr)
                raise typer.Exit(2)
            from lca.contracts.protocols.declarative.declarative_common import SemanticPhase
            from lca.harness.profile.plan_compiler import compile_plan
            from lca.harness.profile.resolve import resolve_profile

            try:
                phase = SemanticPhase(slot)
                plan = compile_plan(resolve_profile(profile))
                entries = tuple(entry for entry in plan.control_entries if entry.phase is phase)
                report = {
                    "phase": phase.value,
                    "entry_count": len(entries),
                    "entries": [
                        {
                            "executor_capability": entry.executor_capability,
                            "predicate": entry.predicate,
                            "aggregation": entry.aggregation,
                            "evidence_required": entry.evidence_required,
                        }
                        for entry in entries
                    ],
                }
            except (TypeError, ValueError) as exc:
                print(f"explain control: {exc}", file=sys.stderr)
                raise typer.Exit(2) from exc
            emit_report(report, json_mode=json_mode)
            raise typer.Exit(0)

        if slot is not None:
            print("explain <run_id> does not accept a second positional argument", file=sys.stderr)
            raise typer.Exit(2)
        from lca.plugins.tools.diagnostics.failure_explainer import (
            FailureExplainer,
        )

        path = resolve_journal_path(jsonl, target)
        report = FailureExplainer(path).explain_failure(run_id=target, depth=depth)
        emit_report(report, json_mode=json_mode)

    @app.command(name="optimize")
    def optimize(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
        limit: int = typer.Option(5, "--limit", "-n"),
    ) -> None:
        """优化候选 —— 按延迟/token/重试排序。"""
        from lca.plugins.tools.diagnostics.optimization_finder import (
            OptimizationFinder,
        )

        path = resolve_journal_path(jsonl, run_id)
        candidates = OptimizationFinder(path).find_optimization_candidates(
            run_id=run_id, limit=limit
        )
        emit_report(candidates, json_mode=json_mode)

    @app.command(name="graph-run")
    def graph_run(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
    ) -> None:
        """Mermaid 插件交互图(写到 stdout;供 docs / dashboard 嵌入)。"""
        from lca.plugins.tools.diagnostics.plugin_graph_renderer import (
            PluginGraphRenderer,
        )

        path = resolve_journal_path(jsonl, run_id)
        mermaid = PluginGraphRenderer(path).render(run_id=run_id)
        typer.echo(mermaid)

    @app.command(name="minimal-repro")
    def minimal_repro(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
    ) -> None:
        """失败因果链 + 必要 evidence refs(供离线复现)。"""
        from lca.plugins.tools.diagnostics.minimal_reproduction import (
            MinimalReproduction,
        )

        path = resolve_journal_path(jsonl, run_id)
        pkg = MinimalReproduction(path).export(run_id=run_id)
        payload = {
            "schema": "lca.minimal_reproduction/1",
            "run_id": run_id,
            "failure_seq": pkg.failure_seq,
            "failure_event_type": pkg.failure_event_type,
            "causal_chain": list(pkg.causal_chain),
            "evidence_refs": list(pkg.evidence_refs),
            "extra": dict(pkg.extra),
        }
        emit_report(payload, json_mode=json_mode)

    @app.command(name="diff-context")
    def diff_context(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
        step: int = typer.Option(0, "--step", help="DiffContext.diff 的 step 参数"),
    ) -> None:
        """同 run 在 step 处的上下文快照(返回 ContextDiff)。"""
        from lca.plugins.tools.diagnostics.diff_context import (
            DiffContext,
        )

        path = resolve_journal_path(jsonl, run_id)
        diff = DiffContext(path).diff(run_id=run_id, step=step)
        payload = {
            "run_id": diff.run_id,
            "step_a": diff.step_a,
            "step_b": diff.step_b,
            "items_added": list(diff.items_added),
            "items_removed": list(diff.items_removed),
        }
        emit_report(payload, json_mode=json_mode)

    @app.command(name="diff-runs")
    def diff_runs(
        run_id_a: str = typer.Argument(..., help="Run id A"),
        run_id_b: str = typer.Argument(..., help="Run id B"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
        step: int = typer.Option(0, "--step"),
    ) -> None:
        """两次 run 同 step 的差异(prompt_hash + delta)。"""
        from lca.plugins.tools.diagnostics.run_diff import (
            RunDiffToolAdapter,
        )

        path = resolve_journal_path(jsonl, run_id_a)
        diff = RunDiffToolAdapter(path).diff(run_id_a=run_id_a, run_id_b=run_id_b, step=step)
        payload = {
            "run_id_a": diff.run_id_a,
            "run_id_b": diff.run_id_b,
            "step": diff.step,
            "prompt_hash_a": diff.prompt_hash_a,
            "prompt_hash_b": diff.prompt_hash_b,
            "delta": dict(diff.delta),
        }
        emit_report(payload, json_mode=json_mode)

    @app.command(name="cost")
    def cost(
        run_id: str = typer.Argument(..., help="Run id"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json"),
        pricing_ref: str = typer.Option("", "--pricing-ref", help="按 pricing_ref 过滤"),
    ) -> None:
        """按 LlmCallCompleted 累加成本(ADR-0065 §六 / PR-6 CostProjector)。"""
        from lca.infrastructure.observability.cost.projector import CostProjector
        from lca.infrastructure.observability.journal.engine.journal_io import (
            load_journal_records,
            record_to_stamped,
        )

        path = resolve_journal_path(jsonl, run_id)
        projector = CostProjector()
        for payload in load_journal_records(path, strict=False):
            stamped = record_to_stamped(payload)
            if stamped is not None:
                projector.on_event(stamped)
        report = projector.render()
        if pricing_ref:
            report["filtered_pricing_ref"] = pricing_ref
        emit_report(report, json_mode=json_mode)

    @app.command(name="evidence")
    def evidence(
        run_id: str = typer.Argument(..., help="Run id"),
        ref: str = typer.Argument(..., help="EvidenceRef digest (sha256:<hex> 或裸 64-hex)"),
        jsonl: Path = typer.Option(None, "--jsonl"),  # noqa: B008
        json_mode: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
    ) -> None:
        """Look up an arguments_ref / output_ref → evidence payload by digest.

        ADR-0101 PR-2:state_ref → arguments_ref (ToolStarted) / output_ref
        (ToolInvoked) per journal v2 schema。
        """
        from lca.contracts.observability.evidence import (
            Classification,
            EvidenceIntegrityError,
            EvidenceRef,
        )
        from lca.infrastructure.observability.facade import current_bound

        raw = ref.strip()
        if raw.startswith("sha256:"):
            digest_only = raw[len("sha256:") :]
        elif len(raw) == 64 and all(c in "0123456789abcdef" for c in raw.lower()):
            digest_only = raw.lower()
        else:
            print(f"ERROR: invalid ref format: {ref!r}", file=sys.stderr)
            raise typer.Exit(1)

        from lca.infrastructure.observability.journal.engine.journal_io import load_journal_records

        path = resolve_journal_path(jsonl, run_id)
        full_ref: EvidenceRef | None = None
        for payload in load_journal_records(path, strict=False):
            # ADR-0101 PR-2:tool 事件带 arguments_ref (ToolStarted) /
            # output_ref (ToolInvoked);state_ref 字段已废弃但保留兼容读。
            data = payload.get("data", {})
            sr_raw = data.get("arguments_ref") or data.get("output_ref") or data.get("state_ref")
            if not isinstance(sr_raw, dict):
                continue
            if str(sr_raw.get("digest", "")).lower() != digest_only:
                continue
            try:
                full_ref = EvidenceRef.from_dict(sr_raw)
            except (ValueError, TypeError, KeyError):
                full_ref = None
            break

        if full_ref is None:
            print(
                f"ERROR: no evidence referenced — run {run_id!r} has no Tool* event "
                f"with state_ref.digest={digest_only!r}",
                file=sys.stderr,
            )
            raise typer.Exit(1)

        bound = current_bound()
        evidence = bound.evidence_binding() if bound is not None else None
        if evidence is None or evidence.store is None:
            print("ERROR: evidence_store not configured (no seam)", file=sys.stderr)
            raise typer.Exit(2)

        requester = f"lca-ops:evidence:{run_id}"
        try:
            payload = evidence.store.get(
                full_ref, requester=requester, audience=Classification.INTERNAL
            )
        except EvidenceIntegrityError as exc:
            print(f"ERROR: integrity violation: {exc}", file=sys.stderr)
            raise typer.Exit(1) from exc

        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"ERROR: evidence payload not JSON: {exc}", file=sys.stderr)
            raise typer.Exit(1) from exc

        report = {
            "run_id": run_id,
            "ref": raw,
            "byte_length": len(payload),
            "data": decoded,
        }
        emit_report(report, json_mode=json_mode)
