# ADR-0286：N9 节点命名闭集的家族命名空间裁决

## 状态

**Proposed — 2026-10-04**（待李超拍板；本 ADR 不改 ADR-0220 正文，0220 状态不变）

本 ADR 裁决 todo-44：`tests/business/test_three_tier_graph_dispatch.py::TestNodeIdVocabulary`
（ADR-0220 §0.4 N9 守卫）稳定 3 红背后的契约歧义——`primitive.*` 家族命名空间节点 id 与
`history.derive` 遗留命名，到底是违规还是 spec-gap。

## 1. 第一原理

**节点 id 的命名规则服务于可读性与可审计性，而不是词表洁癖。**

N9 的真实意图有两层：① 禁止含糊动词（`process` / `handle` / `manage` / `do_*` /
`xxx_impl` / `xxx_helper`）——这类词让节点职责不可判定；② 要求首段落在有意义的动作域闭集，
让审计者一眼知道节点在干哪类事。任何裁决都必须同时满足这两层意图：禁词一票否决，
动作域的"有意义"按 ADR 自身的层架构解释，而不是按字面首段机械匹配。

## 2. 不变量（非协商项）

- **ADR-0220 §3.2 / §3.3 的层家族命名空间**：`primitive.` / `concept.` / `agent.` 是 ADR-0220
  自己定义的图家族前缀（`THREE_TIER_PREFIXES` 在测试文件中显式合法），不是外部入侵的命名。
- **作者自己的验收标准**：ADR-0220 §14 的 N9 验收命令只在
  `bundles/primitive bundles/concept bundles/agent` 查禁词
  （`grep -rn "id: [a-z_]*\.process\b\|..." ... # = 0`），从未对这些目录执行"闭集首段"检查——
  作者不认为家族命名空间是违规。
- **禁词零容忍**：3 个红 id 均不含禁词（`process/handle/manage/do_/_impl/_helper` 全仓 grep = 0），
  N9 的第一层意图（禁词）无人违反。
- **P10 正典路径未落地**：`scripts/lca-ops audit-bundle-node-naming` 尚未实现；当前测试是 N9
  唯一的执行者，裁决必须同时给出测试侧的落地路径。

## 3. 证据（2026-10-04，基 main@7d313d74a）

全仓 `bundles/{primitive,concept,agent}/*.yaml` 的 `- id:` 去重后，首段既不在闭集也不在禁词的
只有两类：

| 节点 id | 位置 | 首段 | 第二段 | 定性 |
|---|---|---|---|---|
| `primitive.spine.compose` / `primitive.spine.dispatch` | `bundles/primitive/spine_emit.yaml`（`factory:` 同名，`source:` 边引用） | `primitive`（层家族） | `spine` ∈ 闭集 | `<家族>.<动作域>.<细节>`：家族前缀是 ADR-0220 自己的命名空间，动作域落在闭集，合规意图明确 |
| `primitive.dto.map` | `bundles/primitive/typed_transform.yaml` | `primitive`（层家族） | `dto` ∉ 闭集 | 首段与上同源；`dto` 作为第二段的合法性不在本轮裁决（守卫只查首段），记为观察项 |
| `history.derive` | `bundles/concept/history_assemble.yaml`（`factory: history.derive`；`think_subgraph.yaml` 以 `entry_node: history.derive` / `binding_edge: think.history.assemble` 引用；bundle 图 id 为 `concept.history.assemble`） | `history`（既非闭集也非家族命名空间） | — | P5/P8/P10 时代内图接线遗留：真正的命名债 |

补充证据：`concept.*` 前缀的节点 id 全仓 **零** 个（家族命名空间在节点层只有 `primitive.*` 在用）；
`agent.*` / `think.*` / `phase.*` 前缀的节点 id 在受检 bundle 中零个（`think.`/`phase.` 仅见于
compat-era 顶层 bundle，已被测试显式豁免）。

## 4. 裁决

- **C1（`primitive.*` 家族命名空间）**：接受为合法。给 `ALLOWED_ACTION_DOMAINS` 加 `primitive`
  例外，注释沿用已有 4 个例外（`reason` / `act` / `remember` / `loop`）的 spec-gap 格式，
  注明"ADR-0220 §3.2 层家族命名空间，`<家族>.<动作域>.<细节>`，动作域仍受闭集约束"。
  `concept` 不加——当前零节点 id 使用，加了是预防性 slop；将来出现 `concept.*` 节点 id 时再评估。
  tests lane 可落地，运行时零变化。
- **C2（`history.derive`）**：维持红钉，**不洗绿、不加例外**。`history` 不是命名空间而是一次性遗留 id，
  加进闭集等于把命名债合法化。改名（候选 `memory.derive`，`history` 在概念层指 RunSessionWriter 投影历史，
  `memory` 域最接近）是 wiring 变更：`factory:` 同名 + `think_subgraph.yaml` 的 `entry_node` 引用 +
  需过 todo-43 的 bundle ports 检查——归 quality lane 或李超动手，tests lane 裁决后同步复验。
- **C3（ADR-0220 正文）**：不改。0220 的 N9 条款与 §14 验收保持原样；本 ADR 是裁决补充，
  不是对 0220 的修订。

## 5. 待拍板（李超）

1. C1：`primitive` 例外是否接受（接受 → tests lane 落地，2 红转绿）。
2. `history.derive` 改名方案（`memory.derive` 候选是否合适）与动手方（quality lane / 李超本人）。
   裁决前 tests lane 保持 3 红钉不变（其中 2 个是 C1 待落地，1 个是 C2 命名债）。

## 6. 交叉引用

- ADR-0220 §0.4 N9（条款）、§3.2/§3.3（层家族命名空间）、§14（N9 验收 grep）
- `tests/business/test_three_tier_graph_dispatch.py`：`ALLOWED_ACTION_DOMAINS`、
  `THREE_TIER_PREFIXES`、`TestNodeIdVocabulary`
- todo-44（提案全文 `hidden_files/todo-44-proposal.md`）、todo-43（bundle ports 检查，C2 改名需过）
- ADR-0256 Task 3 修订先例：fail-soft 优先于 fail-fast（本 ADR 同理：家族命名空间 fail-soft 接受，
  而非把守卫改成对家族前缀 fail-fast）
