# Agent Note: agent_lab 双挂桥接 → 单图种吸收

Status: proposed

## Problem

`agent_lab/` 持有 ADR-0206 细粒度嵌套 `InfoEdgeSpec`（阶段内工人链）；生产出厂 Profile 仍跑 ADR-0075 粗阶段图（`declarative-phase-graph` → `CompiledRunPlan.phase_graph` → `GenericPlanInterpreter`）。两套语义需要对照验证，但同一份 `CompiledRunPlan` 不能同时编译两套 topology（单 entry）。若把 lab 解释器焊进出厂 `web-standard`，会留下难拆的第二 Runtime；若永远只在进程外 `python -m agent_lab.run`，Profile/`why-plugin` 又看不见图 B。

需要一条桥接口径：两张图都能跑、都能选；合并后只剩一种可执行图。

## Proposal

将用 **专用 Profile + Bundle 双挂** 对照两张图，吸收完成后只留一张 InfoEdge 树进入 `GenericPlanInterpreter`。

### 双挂（桥接）

| 图 | 启用面 | 解释器 |
|---|---|---|
| A — 0075 粗阶段图 | 出厂 `profiles/web-standard.yaml` + `bundles/declarative-phase-graph.yaml` | `GenericPlanInterpreter` |
| B — InfoEdge 嵌套图 | 专用 `profiles/agent-lab-infoedge.yaml` + `bundles/agent-lab-infoedge.yaml` | 薄 `RunLoopDriver(infoedge)` → `agent_lab.runtime.runner` |

约束：

1. **出厂 `web-standard` 不挂图 B**（默认生产树零 diff）。
2. 图 B 仅经专用 Profile；切换面是 argv `--profile`，不是 env。
3. 薄适配器注入 Run 已有 Session（`configure_session`）；禁止 `agent_lab_default` 第二事实源；禁止插件 `load_dotenv` / 自读密钥。
4. 工人节点保持图内 `factory`，不逐个 Cordis 化。
5. 双挂件头注释写死 delete-when；吸收 PR 内删除，不跨 PR 留后门。

### 合并后（终态）

- 一种可执行图：`InfoEdgeSpec` 嵌套树进入 `CompiledRunPlan`（region，非平行图种）。
- 解释器仍是 `GenericPlanInterpreter`（Binding / Join / 路由递归）。
- 0075 粗阶段图降级为 `region=phase:*`；lab runner 适配器与专用 Profile/Bundle 删除。
- 管理面与 declarative 同构：Profile/Bundle、effects、`why-plugin`。

### delete-when

`profiles/agent-lab-infoedge.yaml`、`bundles/agent-lab-infoedge.yaml`、`lca/plugins/loop/driver/infoedge/` 在同时满足时删除：

1. `InfoEdgeSpec` ⊆ `CompiledRunPlan`
2. `GenericPlanInterpreter` 递归嵌套子图
3. `rg 'agent_lab.runtime.runner' lca/ lca_kernel/ profiles/ bundles/` = 0
4. `python -m agent_lab.run` 不再是 Gateway/生产入口
5. 出厂 Profile 上 `why-plugin` 能回答图事实归属
6. 测试断言 `web-standard` 无 `infoedge` driver

## Alternatives considered

### Why dedicated Profile dual-mount (chosen)?

专用 Profile + Bundle 把图 B 留在出厂树外；切换面是 argv `--profile`，不是 env。桥接件带 delete-when，吸收完成后可整组删除。这是选定桥接。

### Why not 一个 Profile 里两 Bundle + flag 切换？

同 Plan 两套 topology 触发单 entry 失败；或编译 A、执行 B 会把第二解释器焊进生产默认树，合并时更难拆。`LCA_PROFILE` 也禁止从 env 覆盖。

### Why not 把 lab 挂进出厂 web-standard？

出厂路径出现第二解释器与 why-plugin 混视，违反 ADR-0206 Reject 第二 Runtime，且误流量会打进原型图。否决。

### Why not 永久双轨、不合一张？

管理面永久分叉，Session/密钥面易漂，InfoEdge 语义进不了出厂 Plan 审计。双挂只服务对照与吸收，不是终点。

### Why not 每个 @node 工人一个 Cordis @plugin？

工人是图内 factory，不是进程级 capability；会爆炸 DAG，且与「topology 是数据、executor 是 capability」切法不一致。

## Acceptance criteria

- `web-standard` 与 `agent-lab-infoedge` 均可解析；前者无 infoedge bundle/driver，后者 `why-plugin lca-loop-infoedge` 可见。
- 图 A、图 B 各有一条可运行入口（kernel Profile / lab Profile 或 `python -m agent_lab.run`）。
- infoedge 驱动路径使用注入 Session，不创建 `session_id=agent_lab_default`。
- Note、Profile、Bundle、plugin 头均写明 delete-when；吸收完成后出厂只剩一张 InfoEdge 树。

## Commands

命令真值在 [profiles/README.md](../../../../profiles/README.md)（`agent-lab-infoedge` 节）与
[agent_lab/README.md](../../../../agent_lab/README.md)；`./scripts/lca-ops` 无参手册
（`lca/infrastructure/cli/guide/guide.py`）含图 B 启动摘要。

```bash
# 图 A（出厂）
./scripts/lca-ops inspect-tree profiles/web-standard.yaml
uv run python -m lca_kernel serve --profile profiles/web-standard.yaml \
    --host 0.0.0.0 --port 8765 --allow-unknown-env

# 图 B（专用 Profile）
./scripts/lca-ops inspect-tree profiles/agent-lab-infoedge.yaml
./scripts/lca-ops why-plugin lca-loop-infoedge -p profiles/agent-lab-infoedge.yaml
uv run python -m lca_kernel serve --profile profiles/agent-lab-infoedge.yaml \
    --host 0.0.0.0 --port 8765 --allow-unknown-env

# 图 B（进程外 lab）
python -m agent_lab.run agent_loop
```

## Risks

- lab Profile 若仍挂 `declarative-phase-graph` 仅为过 compile，0075 成为死 Plan region — 必须在头注释标明，合并时删除。
- 薄驱动若走完整 Gateway `/runs`，装配成本高 — MVP 以注册 + Session 单轨 + runner 可调用为门槛，完整 carrier e2e 可后续补。
- contracts 引入 `InfoEdge*` 时保持 `contracts` 无 I/O、单向依赖。
