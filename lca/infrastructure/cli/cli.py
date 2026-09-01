"""CLI entry point — thin shell that delegates to focused command modules.

Design: each command group lives in ``commands/`` as a deepening module.
This file creates the typer app, loads the GUIDE, and registers all
command groups via their ``register(app)`` entry points.

Backward compatibility: ``from lca.infrastructure.cli.cli import app``
still works — tests and scripts import ``app`` directly.
"""

from __future__ import annotations

import typer

import lca.infrastructure.cli.steps  # noqa: F401
from lca.infrastructure.cli.commands import (
    audit,
    creator_plan,
    declarative,
    diagnostics,
    journal,
    journal_migrate,
    journal_steps,
    kernel,
    package_organization,
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
  看 infra / lobehub / daemon / onlyboxes。异常会写出原因。
  onlyboxes 未钉 LCA terminal 镜像时会提示 configure-terminal-runtime。
  注意: status 不包含 LCA 进程;LCA 进程由 lca_kernel serve 自管。
  ./scripts/lca-ops status
  ./scripts/lca-ops status --json          给 agent 用

heal
  自己把不健康的服务拉起来（复用已有容器、重启过期 lobehub、连 daemon）。
  ./scripts/lca-ops heal

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
单服务（lca-ops 只管外部平台服务）
────────────────────────────────
infra      postgres / redis / s3
  动作    start | stop | status
  start   端口不通才 docker compose up，不拆已有 lobe-postgres
  ./scripts/lca-ops infra start

lobehub    Next 前端 :3010    日志 .lca-ops/lobehub.log
  动作    start | stop | restart | status | ensure
  ensure  同步源码 / 打补丁 / 写 .env / bun install，不启进程
  ./scripts/lca-ops lobehub restart

daemon     sandbox-user 连接器
  日志    /home/sandbox-user/.lca/daemon.log
  动作    start | stop | restart | status | ensure
  ensure  感知源码变更 → 自动重建部署 packages/lca-cli
  整机首次  ./scripts/lca-ops provision
  ./scripts/lca-ops daemon restart

onlyboxes  worker runtime(只读;无 start/stop 命令)
  ./scripts/lca-ops status --json  看 onlyboxes 详情

────────────────────────────────
工作流(全站)
────────────────────────────────
status     看上面四个服务 + onlyboxes,JSON 加 --json
heal       自己修不健康的服务(优先用这个;不是 restart)
stop       停外部平台服务(daemon / lobehub / infra),不含 LCA 进程
provision  整机首次:装包 / venv / sandbox 用户 / 工作区 / CLI

  注: dev / restart 已删除(ADR-0119 决定 4:lca-ops 不再管 kernel_serve 进程)。

────────────────────────────────
LCA 进程 (kernel serve)  ADR-0119 决定 4
────────────────────────────────
lca-ops 不管理 LCA 进程。LCA API :8765 由 lca_kernel serve 自管,
SIGTERM/SIGINT 由 K6 ``lca_kernel.lifecycle`` 守护。

  # 启动(前台)
  uv run python -m lca_kernel serve \\
      --profile profiles/web-standard.yaml \\
      --host 0.0.0.0 --port 8765 --allow-unknown-env

  # 打印启动命令(脚本化集成用)
  ./scripts/lca-ops kernel_serve [--host H] [--port P] [profile_path]

  # 仅 boot profile 并 block 到 SIGINT(无 transport)
  ./scripts/lca-ops kernel-boot [profile_path]

  # LCA 进程出问题 → 看 journal 而非 restart
  ./scripts/lca-ops logs
  ./scripts/lca-ops explain <run_id>
  ./scripts/lca-ops diagnose <alias>

────────────────────────────────
Run 复盘  coding-agent tools(ADR-0065 §六 / PR-9,只读)
────────────────────────────────
  7 个只读工具 —— trace / explain / optimize / graph-run / minimal-repro /
  diff-context / diff-runs / cost。默认走人类可读,加 --json 给 agent。
  ./scripts/lca-ops trace <run_id>           通用轨迹
  ./scripts/lca-ops explain <run_id>         失败路径投影
  ./scripts/lca-ops explain control <phase>  解析 profile 的声明式控制贡献
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
package_organization.register(app)
audit.register(app)
creator_plan.register(app)
declarative.register(app)
# journal 注册逻辑: journal.py 建 journal group + logs 子命令;
# journal_steps 增 steps / narrative / raw 子命令。两者共用同一 group
# 以避免双 add_typer。
_journal_group = journal.create_journal_group(app)
journal.register(app, group=_journal_group)
journal_steps.register(_journal_group)
journal_migrate.register(_journal_group)
kernel.register(app)


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
