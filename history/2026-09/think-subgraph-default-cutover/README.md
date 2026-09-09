# Think subgraph default cutover — 2026-09-09

生产默认 profile (`profiles/web-standard.yaml`) 的 `think.main` 已切到
`phase.think.subgraph_host`(5 步子图 `shortcut → route → reason → classify → gate`)。
本目录收录切后 agent 应该知道的"启动命令、加载了什么、配置从哪来、怎么验证"。

权威实现 commit 是 `feat(think): decompose think phase via production subgraph host`。
本目录不是规范,只是把"agent 一次 restart 怎么自助验证"的现场命令和输出固定下来。

## 一句话概览

```text
web-standard.yaml ──(patch)──▶ think.main binding = phase.think.subgraph_host
phase.think.subgraph_host ──(plan_ref)──▶ bundles/think-subgraph.yaml
   ├─(compile fixture)──▶ profiles/fixtures/fthink-subgraph-compile.yaml
   │     ├─ bundles/think-subgraph-steps.yaml   (5 个 step plugin)
   │     └─ bundles/think-subgraph-graph.yaml   (5 节点拓扑 + 边)
   └─(entry_node)──▶ think.subgraph.shortcut → route → reason → classify → gate
```

## 三层"它真的跑新链路"证据

| 证据类型 | 命令 | 看哪里 |
|---|---|---|
| profile 解析后 `think.main` binding | `./scripts/lca-ops inspect-tree profiles/web-standard.yaml` | 列表里的 `phase.think.subgraph_host` 行 |
| 启动命令 | `./scripts/lca-ops kernel_serve` | stdout `To start, run:` 那行 |
| subgraph host 来自哪个 bundle | `./scripts/lca-ops why-plugin phase.think.subgraph_host --profile profiles/web-standard.yaml` | `source: bundles/think-subgraph-host.yaml` |
| 拓扑补丁来自哪 | `./scripts/lca-ops why-plugin phase.topology.standard --profile profiles/web-standard.yaml` | `source: bundles/declarative-phase-graph.yaml+patch` |
| Parity 套件 | `uv run pytest tests/cognition/test_think_subgraph_parity.py` | `Decision payload` 与 standard 相等 |
| Kernel boot stderr | `/tmp/lca-kernel.stderr.<pid>.<yyyymmddhhmmss>.log` | `[debug] cognitive_run_driver_registered`、`event pipeline registered pipeline=web-standard-event-pipeline` |

## Agent 操作剧本(0 配置前置)

切后,任何 agent 拿到一份 checkout 都可以用下面 4 条命令自助:

```bash
# 1) 启动 kernel(默认 profile + 默认 host/port,带 --allow-unknown-env)
./scripts/lca-ops kernel-restart

# 2) 看启了什么 plugin / 图
./scripts/lca-ops inspect-tree profiles/web-standard.yaml | grep phase.think

# 3) 验证 think.main 是否真的绑到 subgraph host
./scripts/lca-ops why-plugin phase.think.subgraph_host --profile profiles/web-standard.yaml
./scripts/lca-ops why-plugin phase.topology.standard --profile profiles/web-standard.yaml

# 4) 出问题:看 kernel stderr / status / journal logs
ls -lt /tmp/lca-kernel.stderr.*.log | head -3
./scripts/lca-ops status --json
./scripts/lca-ops journal logs -v | tail -80
```

## 文件清单(本目录)

| 文件 | 内容 |
|---|---|
| `commands.md` | 每条命令的精确调用 + 期望输出 + 怎么解读 |
| `inspect-tree.web-standard.yaml.txt` | 切后默认 profile 的完整 plugin 树(522 行) |
| `why-plugin.subgraph_host.txt` | `phase.think.subgraph_host` 的来源 / kind / test_suite |
| `why-plugin.topology.txt` | `phase.topology.standard` 的来源(注意 `+patch` 后缀) |
| `kernel_serve.cmd.txt` | `lca-ops kernel_serve` 的输出:它就是 `kernel-restart` 用的 spawn 命令 |
| `last-kernel-stderr.log` | 最近一次 kernel boot 的 stderr 截取(不含 plugin enumeration,但有 boot 事件) |

## 关键事实(不要再翻代码确认)

- `KernelServeConfig.profile` 默认 = `profiles/web-standard.yaml`(`lca/infrastructure/cli/config/config.py:34`)。
- `_DEFAULT_PROFILE` 默认 = `profiles/web-standard.yaml`(`lca/application/api/default_context.py:27`)。
- `web-standard.yaml` 的 `think.main` 已绑 `phase.think.subgraph_host`(本仓库工作树里的状态)。
- `phase.think.standard` plugin 仍注册,但不被任何生产 phase graph 节点调用 — 它是历史锚点;`think-subgraph-steps.yaml` 引到 host 所以 host也能 fallback 到它(实际上 `_shared.py:run_shortcut_step` 不会)。
- 共享 bundle `bundles/declarative-phase-graph.yaml` **未动**;其它引用它的 profile
(`coding-agent`/`benchmark`/`test-minimal` 等)继续走 standard。要切别的 profile,看
`profiles/think-subgraph-dev.yaml` 模板。

## 不在范围

- 切换前没跑 `kernel-restart` 的机器,需要手动先 SIGTERM 旧 kernel。`./scripts/lca-ops kernel-restart` 已经处理。
- 真实 e2e(`runs create --user-text "..."`)需要 LLM key;切本身已通过 parity 测试覆盖,运行时一致性由 `tests/cognition/test_think_subgraph_parity.py` 保证。
- `lobehub`/`daemon`/`onlyboxes` 等其它服务与 think subgraph 无关;它们通过 `./scripts/lca-ops status` 一并可见。