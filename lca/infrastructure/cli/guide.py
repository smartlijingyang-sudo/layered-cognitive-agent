"""CLI banner — printed by ``lca-ops`` with no subcommand and as ``--help``.

Single source of truth for the operator-facing quick reference. Lives
outside :mod:`lca.infrastructure.cli.cli` so the entry module stays small
(register commands + typer wiring only) and so other surfaces (e.g.
docs, scripts) can import the banner text without pulling typer.
"""

from __future__ import annotations

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
  看 kernel_serve / infra / lobehub / daemon / onlyboxes。异常会写出原因。
  onlyboxes 未钉 LCA terminal 镜像时会提示 configure-terminal-runtime。
  kernel_serve 是 LCA 进程 (lca_kernel serve :8765)。
  本地便捷: lca-ops kernel-restart。 supervisor 长管: kill + heal 自愈。
  ./scripts/lca-ops status
  ./scripts/lca-ops status --json          给 agent 用

heal
  自己把不健康的服务拉起来（复用已有容器、重启过期 lobehub、连 daemon）。
  ./scripts/lca-ops heal

────────────────────────────────
日志  journal logs
────────────────────────────────
  ./scripts/lca-ops journal logs              tail 最新 run 的 spine SSOT(events.jsonl)
  ./scripts/lca-ops journal logs -v           + 完整 payload + offloaded sidecar traceback
  ./scripts/lca-ops journal logs -r <run_id>  离线回放指定 run 的 events.jsonl
  ./scripts/lca-ops journal logs lobehub      Next.js 进程日志
  ./scripts/lca-ops journal logs daemon       sandbox 连接器日志
  ./scripts/lca-ops logs                      (alias → journal logs)

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
          ⚠ ensure 是 short-circuit（hash 没变就不重打）；
            强制重打源码补丁 → python3 deploy/lobehub/patch_lobehub.py
            强制重打 pnpm patches → rm .lca-ops/lobehub-pnpm-patches.marker && ensure
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
status     看 kernel_serve + infra / lobehub / daemon / onlyboxes,JSON 加 --json
heal       自己修不健康的服务(只补缺失,不重启 healthy)。kernel-restart 用于本地改完代码后。
stop       停外部平台服务(daemon / lobehub / infra),不含 LCA 进程
provision  整机首次:装包 / venv / sandbox 用户 / 工作区 / CLI

  注: dev / compose 已删除(ADR-0119 决定 4)。
      本地便捷 LCA 重启走 ``kernel-restart`` 子命令(SIGTERM + spawn)。

────────────────────────────────
LCA 进程 (kernel serve)  ADR-0119 决定 4
────────────────────────────────
lca-ops 不长管 LCA 进程(K6 ``lca_kernel.lifecycle`` 只负责
SIGTERM/SIGINT LIFO dispose)。本地改完代码 / 换 profile / 强制刷新:

  ./scripts/lca-ops kernel-restart   # 一行重启: SIGTERM → 等 K6 dispose → spawn 新进程

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


__all__ = ["GUIDE"]
