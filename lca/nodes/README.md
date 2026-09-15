# `lca/nodes/` — Graph Node Implementations

Single tree for every graph node implementation in the LCA runtime.
Node files here are the typed-boundary primitives of the cognitive
six-phase closed set (ADR-0194 / ADR-0228) plus the outer-loop
graph-node-executors.

## 1. 职责

六语义 phase 闭集的 typed-boundary 节点实现，加上外循环的
`graph_node_executor`（`loop/`，非 phase region）。目录即契约：
`lca/<region>/<sub-group>/<node>.py`，`id` 与 region 前缀决定 Cordis 复合键
`<region>::<id>`。

## 2. 不负责

- 图的构建与遍历（`lca/framework/graph/`、`bundles/*.yaml`）
- 插件 Manifest 词汇与装配（`lca/plugins/`、`lca/harness/`）
- 认知算法本体（`lca/cognition/`）；节点只做边界投影与调用编排
- 控制面 State 单写（Reducer / RunCommitter，C4）

## 7. 副作用

节点是**图的一次 visit**，不直接写世界：

| 通道 | 后果 |
|---|---|
| 端口输出 | 返回 `NodeOutput`，由 kernel 合并进 PortRegistry 并记录 `VisitRecord`；节点不自行改 State |
| 事实投递 | 需要落事实的节点（如 `think/dispatch/llm.py`）经注入的 writer / `FactGateway` 调 `append_assistant_message` / `append_tool_call` / `append_tool_result`，仍收敛到 `Session.append` 单入口 |
| 失败 | 抛给 kernel：kernel 记录带 `error` 的 `VisitRecord` 后向上抛；节点内不做 `except: pass` 式吞没 |

`perceive/`、`act/`、`remember/`、`reflect/`、`stop/` 目前是保留空目录，尚无节点实现。

## 3. 输入

`NodeContext` 与 `NodeInput`（kernel 合并后的端口值）、节点自身 `io_schema`、
`BindingKind` 与 region 前缀；think 侧节点还接收注入的 reasoner / adapter 接缝对象。

## 4. 输出

每个节点返回 `NodeOutput`：端口值（decision / observation / routing / facts 等）
加 `producer_node`；kernel 负责合并端口、记录 `VisitRecord` 并选择下一条边。
节点自身不返回控制面 State，也不写事实。

## 5. 允许依赖

`lca.contracts`（绝大多数 import）、`lca.harness`（NodeContext / plugin API 接缝）、
`lca.cognition`（调用认知原语）、`lca.infrastructure`、`lca.plugins` 各一处。
不 import `lca_kernel` 内部。

## 6. 禁止依赖

`lca.application`、`lca.agent`、`lca.runtime`、`lca.session`、`lca.loop`。
节点不得直接写事实或触控制面：需要落事实时经接缝由 runtime 侧完成（C2 双平面）。

## 8. 失败语义

按源码 `raise` 统计：`TypeError` 77、`ValueError` 14、`RuntimeError` 11、
`KeyError` 2、`MissingPromptSectionError` 1、`CapabilityGrantExceededError` 1。
端口/类型不符即抛错，绝不静默降级；能力越界由 `CapabilityGrantExceededError`
拒绝（C5）。异常向上传给 kernel，由它记录失败 visit 后再抛。

## 9. 公共入口

包门面为空（`lca/nodes/__init__.py` 不重导出符号），调用方按 region 路径取用节点
模块，例如 `lca/nodes/think/dispatch/llm.py`、`lca/nodes/think/route/`、
`lca/nodes/loop/`（外循环 graph_node_executor，非六语义 phase region）。
新增节点走「Adding a new node」一节的两步：实现 `@plugin` + 注册 bundle 条目。

## Layout

```
lca/nodes/
├── think/                # region = "think" (closed-set phase)
│   ├── history/          # sub-group: session-history assembly
│   │   └── assemble.py   # id="history.derive" → think::history.derive
│   ├── dispatch/         # sub-group: LLM I/O
│   │   └── llm.py        # id="llm.dispatch"   → think::llm.dispatch
│   ├── decision/         # sub-group: decision-shape projection
│   │   └── parse.py      # id="decision.parse"  → think::decision.parse
│   ├── route/            # sub-group: graph access (shortcut + skill route)
│   │   ├── shortcut.py   # id="think.shortcut"  → think::think.shortcut
│   │   └── route.py      # id="think.route"     → think::think.route
│   ├── reason/           # sub-group: LLM-backed reasoning
│   │   ├── plan.py       # id="think.reason.plan"   → think::think.reason.plan
│   │   └── render.py     # id="think.reason.render" → think::think.reason.render
│   └── gate.py           # single-node sub-group: think.gate
├── loop/                 # outer-loop graph_node_executors (NOT a six-phase region)
│   ├── agent/plugin.py   # NodeType.AGENT
│   ├── aggregator/plugin.py
│   ├── topology/plugin.py
│   └── registry/plugin.py
├── perceive/             # reserved for six-phase nodes (empty today)
├── act/                  # reserved
├── remember/             # reserved
├── reflect/              # reserved
└── stop/                 # reserved
```

## Rules

1. **Region is the first directory level.** `lca/nodes/<region>/<sub-group>/<node>.py`
   for nodes that cluster; `lca/nodes/<region>/<node>.py` for single-node
   sub-groups (`think/gate.py`).
2. **All six phase regions exist as directories.** Even when empty, the
   directory tree mirrors the six-phase closed set `{perceive, think, act,
   remember, reflect, stop}`. A new phase node always has a home.
3. **`loop/` is region-equivalent for outer-loop graph-node-executors.**
   The four roles (`agent` / `aggregator` / `topology` / `registry`) do not
   appear in the six-phase closed set; they implement `NodeExecutor` for
   the outer runtime loop. They are siblings to `think/`, not children.
4. **Plugin id and composite key are unchanged.** The bundler
   (`bundles/*.yaml:plugins:`) discovers nodes by id, not by import path.
   Only the Python import path changes; `phase.think.shortcut` and
   `think::think.shortcut` continue to be the discovery keys.
5. **All nodes use the hand-written `@plugin(...)` carrier pattern.** See
   `think/route/shortcut.py` and ADR-0228 D2 for the canonical shape.

## Adding a new node

1. Decide the region (one of the six phases, or `loop/` for outer-loop executors).
2. Decide whether the node clusters with existing siblings (sub-group) or
   stands alone (file directly under `<region>/`).
3. Pick the implementation mechanism:
   - **Hand-written `@plugin(...)` carrier** (the only canonical shape per
     ADR-0228 D2) when `node_execute` reads capabilities from runtime, has
     type assertions, or branches on capability-presence (e.g.
     `think/route/shortcut.py` — capability absence falls through to next
     node).
4. Place the file at `lca/nodes/<region>/<sub-group>/<node>.py`.
5. Register it in `bundles/<bundle>.yaml:plugins:` with the existing
   `phase.<region>.<id>` plugin id (unchanged) and the new
   `$module: lca.nodes.<region>.<sub-group>.<node>` import path.
6. The plugin id ↔ module path pair is the only thing the bundler cares about.
   `bundles/concept/<node>.yaml` does not change.

## History

This tree was introduced in note
[`2026-09-15-unified-nodes-directory-layout`](../notes/implemented/seam/2026-09-15-unified-nodes-directory-layout.md)
after PR3 introduced the typed-boundary mechanism but left the node files
scattered across `lca/framework/graph/nodes/`, `lca/plugins/think/`, and
`lca/plugins/loop/graph/nodes/`. The unified tree gives every node a
home discoverable by `ls` without reading docs.
