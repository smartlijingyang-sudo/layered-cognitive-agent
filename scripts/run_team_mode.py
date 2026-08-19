#!/usr/bin/env python3
"""Team mode probe CLI — zero-config friendly.

Defaults
--------
- track=real LLM (LLM_API_KEY / .env)
- per-mode scenario card + default objective (no -o needed)
- full live spans + full TRACE digest

Examples
--------
  uv run python scripts/run_team_mode.py
  uv run python scripts/run_team_mode.py board
  uv run python scripts/run_team_mode.py --list
  uv run python scripts/run_team_mode.py solo --track scripted
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lca.contracts.protocols import LLMAdapter  # noqa: E402
from tests.harness.collector import LiveCollector  # noqa: E402
from tests.harness.modes import (  # noqa: E402
    ALL_MODES,
    default_objective,
    get_scenario,
    scripted_llm_for_mode,
)
from tests.harness.report import format_case_digest  # noqa: E402
from tests.harness.runner import run_mode  # noqa: E402

_TRACK_SCRIPTED = "scripted"
_TRACK_REAL = "real"
_QUIT = frozenset({"q", "quit", "exit", ""})


def _silence_framework_logs(*, verbose: bool) -> None:
    """Hide structlog chatter unless --verbose. Live uses plain print()."""
    import structlog

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s", force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def _print_mode_table() -> None:
    print("可用场景（直接回车序号即可，无需其它参数）：")
    for i, mode in enumerate(ALL_MODES, start=1):
        sc = get_scenario(mode)
        print(f"  {i:>2}) {mode:<12}  {sc.title}")
        print(f"      {sc.blurb}")
    print()


def _pick_mode_interactive() -> list[str]:
    _print_mode_table()
    print("输入序号 / mode 名 / all；q 退出")
    raw = input("选择> ").strip().lower()
    if raw in _QUIT:
        print("已取消。")
        raise SystemExit(0)
    if raw in ("all", "a", "*"):
        return list(ALL_MODES)
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(ALL_MODES):
            return [ALL_MODES[idx - 1]]
        print(f"无效序号: {raw}（1–{len(ALL_MODES)}）", file=sys.stderr)
        raise SystemExit(2)
    if raw in ALL_MODES:
        return [raw]
    print(f"未知 mode: {raw!r}", file=sys.stderr)
    _print_mode_table()
    raise SystemExit(2)


def _resolve_real_llm() -> LLMAdapter:
    from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter

    load_dotenv_if_present()
    if not os.getenv("LLM_API_KEY"):
        print(
            "错误: 默认走真实 LLM，需要环境变量 LLM_API_KEY（可放项目根 .env）。\n"
            "  export LLM_API_KEY=sk-...\n"
            "  # 可选: LLM_BASE_BASE_URL / LLM_MODEL\n"
            "离线假 LLM 请显式加:  --track scripted",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return resolve_llm_adapter()


async def _run_one(
    mode: str,
    *,
    track: str,
    live: bool,
    digest: bool,
    objective: str | None,
    max_rounds: int,
) -> int:
    """Run via framework Team/Agent path; console 叙述导出器打印场景卡+步骤."""
    llm: LLMAdapter = (
        scripted_llm_for_mode(mode) if track == _TRACK_SCRIPTED else _resolve_real_llm()
    )

    # CLI-only convenience: mode-specific default task (framework prints whatever is passed).
    obj = objective if objective is not None else default_objective(mode)
    # LiveCollector = InMemory + console 叙述导出器（同一份叙事，不双写）。
    col = LiveCollector(live=live)

    # The runner already booted cordis_ctx at the start of run_mode. It's
    # passed to all Agent() constructors below so the composer resolves
    # services from the booted ctx.

    try:
        outcome = await run_mode(
            mode,
            llm,
            collector=col,
            objective=obj,
            max_rounds=max_rounds,
        )
    except Exception as exc:
        print(f"\n运行失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        if digest and (col.bundle().spans if col.bundle() else []):
            print(format_case_digest(col.bundle(), title=f"{mode} (failed)"))
        return 1

    status = getattr(outcome.result.status, "value", outcome.result.status)
    print()
    print("── 执行结束 ──")
    print(f"  status={status!r}  total_steps={outcome.result.total_steps}")
    out = (outcome.result.output or "").strip()
    if out:
        preview = out if len(out) <= 400 else out[:400] + "…"
        print(f"  output: {preview}")

    if digest:
        print()
        print(format_case_digest(col.bundle(), title=mode, result=outcome.result))

    if track == _TRACK_SCRIPTED:
        return 0 if status == "completed" else 1
    return 0 if status in ("completed", "failed", "input_required") else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_team_mode",
        description=(
            "跑 Team 协作场景：开场打印场景卡（角色/计划步骤/默认任务），"
            "边跑边打 span，结束出全量 TRACE。默认真实 LLM，无需额外参数。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法（尽量零参数）:
  uv run python scripts/run_team_mode.py           # 菜单选场景
  uv run python scripts/run_team_mode.py board
  uv run python scripts/run_team_mode.py --list

场景卡 / 步骤进度来自框架 console 叙述导出器（Team/Agent.run 内），
不是测试脚本私货。本 CLI 只负责：选 mode、默认任务文案、结束 TRACE digest。

可选:
  -o / --objective   覆盖默认任务
  --track scripted   离线假 LLM
  -q                 不 live（仍可结束 digest）
""",
    )

    p.add_argument(
        "mode",
        nargs="?",
        choices=[*ALL_MODES, "all"],
        help="场景 mode；省略则菜单选择",
    )
    p.add_argument("--list", "-l", action="store_true", help="列出场景后退出")
    p.add_argument("--all", action="store_true", help="依次跑全部场景")
    p.add_argument(
        "--track",
        "-t",
        choices=(_TRACK_REAL, _TRACK_SCRIPTED),
        default=_TRACK_REAL,
        help="real=真 LLM（默认）；scripted=假 LLM",
    )
    live_g = p.add_mutually_exclusive_group()
    live_g.add_argument(
        "--live",
        dest="live",
        action="store_true",
        default=True,
        help="边跑边打印 span（默认开）",
    )
    live_g.add_argument(
        "--quiet",
        "-q",
        dest="live",
        action="store_false",
        help="不实时打印",
    )
    dig_g = p.add_mutually_exclusive_group()
    dig_g.add_argument(
        "--digest",
        dest="digest",
        action="store_true",
        default=True,
        help="结束打印 TRACE（默认开）",
    )
    dig_g.add_argument(
        "--no-digest",
        dest="digest",
        action="store_false",
        help="不打印结束 TRACE",
    )
    p.add_argument(
        "--objective",
        "-o",
        default=None,
        help="覆盖该场景的默认任务（一般不需要）",
    )
    p.add_argument(
        "--max-rounds",
        type=int,
        default=2,
        help="debate / peer_swarm 轮次（默认 2）",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="框架内部日志",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _silence_framework_logs(verbose=args.verbose)

    if args.list:
        _print_mode_table()
        return 0

    modes: list[str]
    if args.all or args.mode == "all":
        modes = list(ALL_MODES)
    elif args.mode:
        modes = [args.mode]
    else:
        modes = _pick_mode_interactive()

    if args.track == _TRACK_REAL:
        _resolve_real_llm()

    async def _run_all() -> int:
        worst = 0
        for mode in modes:
            code = await _run_one(
                mode,
                track=args.track,
                live=args.live,
                digest=args.digest,
                objective=args.objective,
                max_rounds=args.max_rounds,
            )
            if code != 0:
                worst = code
        if len(modes) > 1:
            print()
            print(f"完成 {len(modes)} 个场景，exit={worst}")
        return worst

    return asyncio.run(_run_all())


if __name__ == "__main__":
    raise SystemExit(main())
