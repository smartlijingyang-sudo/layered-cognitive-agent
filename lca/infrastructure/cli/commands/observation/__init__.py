"""Observation CLI —— 4 个 lca-ops 子命令,SSOT 入口。

子命令( 全部挂在 ``observation`` typer group 下):
  lca-ops observation plan-show <profile_or_plan_ref>
  lca-ops observation trace-show <run_id> [--node <id>] [--filter kind=...]
  lca-ops observation run-explain <run_id>
  lca-ops observation run-replay <run_id>

默认 --json 输出,agent 直消费;--human 投影 markdown。
"""

from __future__ import annotations

import typer

from lca.infrastructure.cli.commands.observation import (
    plan_show,
    run_explain,
    run_replay,
    trace_show,
)

__all__ = ["register"]


def register(app: typer.Typer) -> None:
    """注册到 ``lca-ops observation <subcmd>``。"""
    obs_app = typer.Typer(help="观察面 + 诊断面 SSOT 入口。")
    app.add_typer(obs_app, name="observation")
    plan_show.register(obs_app)
    trace_show.register(obs_app)
    run_explain.register(obs_app)
    run_replay.register(obs_app)
