"""CLI entry point — thin shell that delegates to focused command modules.

Design: each command group lives in ``commands/`` as a deepening module.
This file creates the typer app, loads the GUIDE, and registers all
command groups via their ``register(app)`` entry points.

Backward compatibility: ``from lca.layer0_infra.ops.cli import app``
still works — tests and scripts import ``app`` directly.
"""

from __future__ import annotations

import typer

import lca.layer0_infra.ops.steps  # noqa: F401
from lca.layer0_infra.ops.commands import (
    audit,
    creator_plan,
    declarative,
    diagnostics,
    journal,
    profile_inspect,
    services,
    tools,
    workflow,
)

GUIDE = """\
LCA 开发平台编排  ./scripts/lca-ops

日常只记三句
  ./scripts/lca-ops status     看现在怎样
  ./scripts/lca-ops heal       有问题就修，不用再拆命令
  ./scripts/lca-ops logs       跟 journal 事实流

────────────────────────────────
全站
────────────────────────────────
status
  看 infra / gateway / lobehub / daemon / onlyboxes / dsh。异常会写出原因。
  onlyboxes 未钉 LCA terminal 镜像时会提示 configure-terminal-runtime。
  dsh 未建镜像时会提示 build-dsh-image。
  ./scripts/lca-ops status
  ./scripts/lca-ops status --json          给 agent 用

heal
  自己把不健康的服务拉起来（复用已有容器、重启过期 gateway、连 daemon）。
  ./scripts/lca-ops heal

dev
  第一次或全停之后：起 infra + gateway + lobehub + daemon。
  ./scripts/lca-ops dev

restart
  全停再起。setup 已做好会跳过。日常异常优先 heal，不要先 restart。
  ./scripts/lca-ops restart

stop
  停 daemon / lobehub / gateway / infra。
  ./scripts/lca-ops stop

────────────────────────────────
日志  logs
────────────────────────────────
  ./scripts/lca-ops logs              journal 事实流（模型所见即日志）
  ./scripts/lca-ops logs -v           + prompt/response/args/result
  ./scripts/lca-ops logs -d           + 增量事件（text/reasoning delta）
  ./scripts/lca-ops logs --replay     从 traces/lca_journal.jsonl 回放
  ./scripts/lca-ops logs lobehub      Next.js 进程日志
  ./scripts/lca-ops logs daemon       sandbox 连接器

  事实（decision / step / tool / llm）→ 观察（insight：冗余/循环/成本/关键路径）
  模型可见的一切都可从 journal 重建。

────────────────────────────────
单服务
────────────────────────────────
gateway    LCA API  :8765     日志 .lca-ops/gateway.log
  start | stop | restart | status
  ./scripts/lca-ops gateway restart

lobehub    Next 前端 :3010    日志 .lca-ops/lobehub.log
  start | stop | restart | status | ensure
  ensure = 源码 / 补丁 / .env / bun install，不启进程
  ./scripts/lca-ops lobehub restart

infra      postgres / redis / s3
  start | stop | status
  start 只补缺的（已有 lobe-postgres:25432 会复用）
  ./scripts/lca-ops infra start

daemon     sandbox-user 连 gateway
  start | stop | status | ensure
  ensure     部署 /opt/lca CLI
  provision  装包 / venv / 建用户 / 工作区 / CLI（原 lca-host.py）
  ./scripts/lca-ops daemon start
  ./scripts/lca-ops provision

────────────────────────────────
Run 复盘  coding-agent tools(ADR-0065 §六 / PR-9,只读)
────────────────────────────────
  7 个只读工具 —— trace / explain / optimize / graph-run / minimal-repro /
  diff-context / diff-runs / cost。默认走人类可读,加 --json 给 agent。
  ./scripts/lca-ops trace <run_id>           通用轨迹
  ./scripts/lca-ops explain <run_id>         失败路径投影
  ./scripts/lca-ops explain control <slot>   解析 profile 的 ControlPlan 槽位投稿
  ./scripts/lca-ops optimize <run_id>        优化候选(延迟/token/重试)
  ./scripts/lca-ops graph-run <run_id>       Mermaid 插件交互图
  ./scripts/lca-ops minimal-repro <run_id>   失败因果链 + evidence refs
  ./scripts/lca-ops diff-context <run_id>    同 run step 上下文
  ./scripts/lca-ops diff-runs <a> <b>        两次 run 对比
  ./scripts/lca-ops cost <run_id>            LlmCallCompleted 成本累加
  ./scripts/lca-ops evidence <run_id> <ref>  查 state_ref → evidence payload

  diagnose <alias> 已内置 4 个 alias:model-not-seen / loop-stuck /
  memory-poisoned / approval-rejected(看 DIAGNOSE_HINTS 拿修复建议)。

────────────────────────────
Audit 测量网  ADR-0074 PR-0（只读）
────────────────────────────
  4 个 AST 扫描器,让 reviewer 一行命令看清 hardcode 在哪。
  默认走人类可读,加 --json 给 agent。有发现时 exit 1（CI 可识别）。
  ./scripts/lca-ops audit-control-surface  Control Slot 投稿分布 + 缺 control 段
  ./scripts/lca-ops audit-state-writers     state.* 写入点(Reducer 单写校验基线)
  ./scripts/lca-ops audit-direct-commands   Body 直接 import sandbox/transport 的路径
  ./scripts/lca-ops audit-hook-attach       hooks.trigger / middleware_bag / _emit 残留

  ./scripts/lca-ops status-adr-supervision   一命令看 ADR-0066/0067/0068/0069/0074 监督状态
                                              = 验证 tracker.md 一致性 + 输出当前历史迁移基线
                                              (实现了 tracker 即实现 5 ADR)

────────────────────────────────
通用参数
────────────────────────────────
  --json           结构化 JSON（agent）
  -q / --quiet     少说话
  -c PATH          配置，默认 ./lca-ops.yaml
  密码文件         .lobehub-stack/sudo.pass
"""


app = typer.Typer(
    name="lca-ops",
    help=GUIDE,
    rich_markup_mode=None,
    add_completion=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["--help", "-h"]},
)


@app.callback()
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(GUIDE)
        raise typer.Exit(0)


# Register all command groups
workflow.register(app)
services.register(app)
journal.register(app)
tools.register(app)
profile_inspect.register(app)
diagnostics.register(app)
audit.register(app)
creator_plan.register(app)
declarative.register(app)


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
