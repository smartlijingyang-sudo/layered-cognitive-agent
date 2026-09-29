#!/usr/bin/env python3
"""跑 YAML 定义的团队场景（tests/fixtures/team_scenarios/*.yaml）。

Examples
--------
  uv run python scripts/run_scenario_file.py tests/fixtures/team_scenarios/saas_renewal_rescue.yaml
  uv run python scripts/run_scenario_file.py <yaml> --team rescue_board --case renewal_rescue
  uv run python scripts/run_scenario_file.py <yaml> --list

可观测性后端由 env ``LCA_OBS_BACKENDS`` 决定（不传 --observability 时），例如灌 Langfuse：

  LCA_OBS_BACKENDS=console+langfuse uv run python scripts/run_scenario_file.py <yaml>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lca.application.api.api import ensure_default_ctx  # noqa: E402
from lca.contracts.protocols import LLMAdapter  # noqa: E402
from lca.infrastructure.llm_adapter import (  # noqa: E402
    load_dotenv_if_present,
    resolve_llm_adapter,
)
from tests.support.scenario_loader import (  # noqa: E402
    CaseSpec,
    ScenarioSpec,
    build_team,
    load_scenario,
)

_STATUS_COMPLETED = "completed"


@dataclass
class CaseRunResult:
    case_key: str
    team: str
    status: str
    total_steps: int
    duration_s: float
    failures: list[str]
    output_preview: str


def _resolve_real_llm() -> LLMAdapter:
    load_dotenv_if_present()
    if not os.getenv("LLM_API_KEY"):
        print(
            "错误: 需要环境变量 LLM_API_KEY（可放项目根 .env）。\n  export LLM_API_KEY=sk-...",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return resolve_llm_adapter()


def _pick_case(spec: ScenarioSpec, team: str | None, case: str | None) -> tuple[str, CaseSpec]:
    if case is not None:
        if case not in spec.cases:
            raise SystemExit(f"未知 case: {case!r}；可用：{sorted(spec.cases)}")
        return case, spec.cases[case]
    candidates = {k: c for k, c in spec.cases.items() if team is None or c.team == team}
    if not candidates:
        raise SystemExit(f"team {team!r} 下没有可用 case")
    key = next(iter(candidates))
    return key, candidates[key]


def _check_assertions(case: CaseSpec, status: str, total_steps: int) -> list[str]:
    failures: list[str] = []
    expected_status = case.assertions.get("status")
    if expected_status is not None and status != expected_status:
        failures.append(f"status={status!r}，期望 {expected_status!r}")
    min_steps = case.assertions.get("min_steps")
    if min_steps is not None and total_steps < int(min_steps):
        failures.append(f"total_steps={total_steps}，期望 ≥ {min_steps}")
    return failures


async def _execute_case(
    spec: ScenarioSpec,
    case_key: str,
    case: CaseSpec,
    llm: LLMAdapter,
    obs: str | None,
    objective_override: str | None = None,
) -> tuple[CaseRunResult, str]:
    objective = objective_override if objective_override is not None else case.objective
    team = build_team(spec, case.team, llm, observability=obs)
    start_time = time.perf_counter()
    result = await team.run(objective)
    duration = time.perf_counter() - start_time
    status = str(getattr(result.status, "value", result.status))
    failures = _check_assertions(case, status, result.total_steps)
    out = (result.output or "").strip()
    preview = out if len(out) <= 80 else out[:77] + "..."
    case_res = CaseRunResult(
        case_key=case_key,
        team=case.team,
        status=status,
        total_steps=result.total_steps,
        duration_s=duration,
        failures=failures,
        output_preview=preview,
    )
    return case_res, out


async def _run(args: argparse.Namespace) -> int:
    await ensure_default_ctx()
    spec = load_scenario(args.scenario)

    if getattr(args, "mock", False):
        from lca.infrastructure.llm_adapter.mock.llm import MockLLMAdapter

        llm = MockLLMAdapter()
    else:
        llm = _resolve_real_llm()

    obs = args.observability or os.getenv("LCA_OBS_BACKENDS")

    if args.all:
        cases_to_run = {
            k: c for k, c in spec.cases.items() if args.team is None or c.team == args.team
        }
        if not cases_to_run:
            print(f"没有符合条件的 case (team={args.team!r})", file=sys.stderr)
            return 1

        print(f"=== 开始全量评测: {Path(args.scenario).name} (共 {len(cases_to_run)} 个 Case) ===\n")
        results: list[CaseRunResult] = []
        for i, (ck, c) in enumerate(cases_to_run.items(), 1):
            print(f"[{i}/{len(cases_to_run)}] 正在执行: {ck} (team={c.team})...")
            case_res, out = await _execute_case(spec, ck, c, llm, obs)
            results.append(case_res)
            res_str = "PASS" if not case_res.failures else "FAIL"
            print(
                f"    -> {res_str} | status={case_res.status} | steps={case_res.total_steps} | {case_res.duration_s:.2f}s"
            )
            if case_res.failures:
                for f in case_res.failures:
                    print(f"       断言失败: {f}", file=sys.stderr)
            print()

        print("\n" + "=" * 80)
        print(f"{'Case ID':<40} {'Team':<16} {'Status':<10} {'Steps':<6} {'Time':<7} {'Result'}")
        print("-" * 80)
        total_failures = 0
        for r in results:
            verdict = "✅ PASS" if not r.failures else "❌ FAIL"
            if r.failures:
                total_failures += 1
            print(
                f"{r.case_key:<40} {r.team:<16} {r.status:<10} {r.total_steps:<6} {r.duration_s:>5.2f}s {verdict}"
            )
        print("=" * 80)
        print(f"总计: {len(results)} 个 Case，通过: {len(results) - total_failures}，失败: {total_failures}")
        return 0 if total_failures == 0 else 1

    case_key, case = _pick_case(spec, args.team, args.case)
    objective = args.objective if args.objective is not None else case.objective

    print(f"场景: {Path(args.scenario).name} · team={case.team} · case={case_key}")
    print(f"任务: {objective.strip()[:120]}…\n")

    case_res, out = await _execute_case(
        spec, case_key, case, llm, obs, objective_override=args.objective
    )

    print("\n── 执行结束 ──")
    print(
        f"  status={case_res.status!r}  total_steps={case_res.total_steps}  duration={case_res.duration_s:.2f}s"
    )
    if out:
        preview = out if len(out) <= 600 else out[:600] + "…"
        print(f"  output: {preview}")

    for f in case_res.failures:
        print(f"断言失败: {f}", file=sys.stderr)
    return 0 if not case_res.failures else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_scenario_file",
        description="跑 YAML 团队场景（真实 LLM）；后端由 LCA_OBS_BACKENDS 控制。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("scenario", help="场景 YAML 路径")
    p.add_argument("--team", default=None, help="限定 team（case 省略时用于筛选）")
    p.add_argument("--case", default=None, help="指定 case；省略取第一个")
    p.add_argument("--all", "-a", action="store_true", help="按顺序跑文件中的全部 case 并打印汇总表格")
    p.add_argument("--objective", "-o", default=None, help="覆盖 case 的 objective")
    p.add_argument(
        "--observability",
        default=None,
        help="后端选择串（如 console+langfuse）；省略读 env LCA_OBS_BACKENDS",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="使用离线确定性 MockLLMAdapter（用于冒烟验证，不调真实 LLM）",
    )
    p.add_argument("--list", "-l", action="store_true", help="列出 teams/cases 后退出")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.list:
        spec = load_scenario(args.scenario)
        print("teams:", ", ".join(spec.teams))
        for key, case in spec.cases.items():
            print(f"cases: {key} (team={case.team})")
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
