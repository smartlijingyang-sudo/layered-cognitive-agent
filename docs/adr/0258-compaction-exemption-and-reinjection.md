# ADR-0258 — Compaction 豁免与重注契约：standing 永不进压缩流、摘要带血统、刷新 fail-closed

## 状态

**Proposed — 2026-10-01**

> **一句话**：把"压缩时 standing 文件不丢、摘要不能冒充原文、刷新失败不静默清空"三条已在代码里零散实现的规则，升成显式契约——豁免+重注变不变量、压缩段带 `source=fold-summary` 血统、刷新读失败时保留旧块并打 warning 事件而非静默清空。

**Extends**：
- [ADR-0255](0255-muse-production-runtime-full-reference.md)（Muse 生产运行时全量参考）：本 ADR 是 0255 §4.5（压缩豁免与重注）的 LCA 落地提案——Muse 侧"compaction 只压对话历史、standing 豁免并在新窗口重注"，LCA 侧对应的是折叠后的系统提示头与 standing 注入块；
- [ADR-0254](0254-commercial-context-files-and-continuous-memory-runtime.md)（顶级商用级 Assistant 上下文文件体系）：本 ADR 把 0254 已宣称的"物理隔离 Compaction 防失忆"细化为可验证契约；
- [ADR-0037](0037-...md) 的 journal 真值语义：C2 的血统规则依赖 journal 作为压缩摘要的唯一合法细节恢复路径。

**实证来源**：2026-10-01 iter-arch 轮对当前实现的实证审计——
- 豁免+重注已实现、缺契约：`lca/infrastructure/memory/contextfiles/domain/standing.py::rehydrate_after_compaction`（折叠后丢旧历史、standing 快照从磁盘现读追加，原文重注不摘要）、`lca/infrastructure/memory/contextfiles/service/compaction.py::preserve_standing_sections`（折叠 prompt 复用时刷新并发布 `StandingPreserved` 事件）、历史内旧注入块经 `_strip_injected` 剥离不复用；Agent Note `docs/notes/implemented/seam/2026-09-30-standing-files-survive-folded-header.md`；step-scoped 压缩仍是 `model_context_assembler.py:27` 的预留位；
- 缺口 C3（fail-open，实锤）：`compaction.py:54-57` `_read` 吞 OSError → 返回 `""`，`domain/standing.py:111` `refresh_injected` docstring 明写 "A file that is missing or blank drops its old block"——**一次瞬时读失败（权限抖动、磁盘 busy）= standing 块静默消失**，且 `StandingPreserved(changed=True)` 照常发布（事件名叫 Preserved）；
- 缺口 C2（摘要无血统）：折叠/压缩后的历史没有 provenance 标记区分 summary 与 verbatim；0255 §4.5 第三条（摘要丢细节→走检索链找回、不许把摘要当原文引用）在 LCA 无对应规则。

---

## 0. 接任务前 7 问

1. **问题是什么？** ① standing 的"压缩豁免"只靠实现惯例，无人敢改也不敢断言；② 压缩摘要与原文在 downstream 不可区分，模型可能把折叠摘要当 verbatim 引用；③ 刷新路径是 fail-open 的：读失败 = 块消失，且照常发"已保留"事件。
2. **受影响的事实或契约是什么？** `refresh_injected` 的"missing or blank drops block"语义、`preserve_standing_sections` 的事件契约、`rehydrate_after_compaction` 的重注语义、折叠历史的 provenance 模型。
3. **唯一真值在哪里？** standing 块的真值永远是磁盘上的 standing 文件（现读现用）；折叠历史里"说过什么"的真值是 journal/event spine，不是压缩摘要。
4. **改变哪个边界？** 把"读失败"与"文件被删"两个事件分开：前者是基础设施故障 → 保留旧块 + warning；后者是用户意图 → 落块消失。压缩产物必须自带血统标签。
5. **现有 Protocol / ADR 能否表达？** 不能。ADR-0254 宣称了"防失忆"目标但没写契约；ADR-0037 给了 journal 真值但没写"压缩视图不可引用"。
6. **失败、重试、恢复和幂等语义是什么？** 刷新读失败 → 保留旧块、发布 `StandingRefreshFailed`-style warning 事件、错误抛回调用方重试（fail-closed）；真正的删除（文件从磁盘移除且用户确认）→ 块消失，事件如实标记 `changed=True` 且带 `dropped` 名单。
7. **如何验证？** §4 的 4 条验收用例：T1 刷新事件语义、T2 读失败 fail-closed、T3 真删除落块、T4（future）压缩段 provenance。

---

## 1. 现状：三条规则已实现、两条缺口实锤

### 1.1 已实现的豁免+重注（升为契约 C1 的基础）

| 位置 | 语义 |
|---|---|
| `domain/standing.py::rehydrate_after_compaction` | 折叠后丢弃旧历史；standing 块从磁盘**现读**、**原文追加**，不进摘要流 |
| `service/compaction.py::preserve_standing_sections` | 折叠 prompt 复用时刷新 standing 块，发布 `StandingPreserved(names, changed=True)` |
| 历史旧注入块 | `_strip_injected` 剥离，**不复用**旧注入文本（防止过期块借尸还魂） |

这些语义今天只靠"实现长这样"维持。本 ADR 把它们升为**不变量**：任何未来的压缩策略（包括 `model_context_assembler.py:27` 的 step-scoped 预留位）都必须遵守——**standing 永不进压缩流**。

### 1.2 缺口 C3：刷新 fail-open（实锤）

```python
# lca/infrastructure/memory/contextfiles/service/compaction.py
def _read(store: FileStore, name: str) -> str:
    try:
        return store.read_text(name)
    except OSError:
        return ""          # ← 瞬时读失败 → 空串
```

```python
# lca/infrastructure/memory/contextfiles/domain/standing.py:111
"""... A file that is missing or blank drops its old block. ..."""
```

调用链：`_read` 返回 `""` → `by_name[name] = ""` → `refresh_injected` 里 `body` 为空 → 旧块被丢弃 → `StandingPreserved(changed=True)` 照常发布。**事件名叫 Preserved，实际是 Lost**。读失败 ≠ 文件被删，但今天两者走同一条路径。这是 fail-open。

### 1.3 缺口 C2：压缩摘要无血统

折叠后的历史段没有任何标记说明"这段是模型摘要、不是原文"。0255 §4.5 第三条在 Muse 侧的规则是：摘要必然丢细节，细节的唯一合法恢复路径是回翻原文/走检索链，且**不许把摘要当原文引用**。LCA 侧 journal（ADR-0037）是原文真值，但"压缩视图不可引用"这条规则没有写进任何地方。

---

## 2. 契约

### C1 — 豁免+重注是跨压缩策略的不变量

- 任何压缩/折叠策略（run 级折叠、step-scoped 压缩、prompt 复用）**不得**把 standing 注入块送入摘要器；
- 折叠后 standing 块的唯一合法来源是**磁盘现读原文**（`rehydrate_after_compaction` 语义），历史内的旧注入块一律剥离（`_strip_injected` 语义）；
- 新增压缩策略时必须在 ADR/设计文档里声明"本策略如何满足 C1"。

### C2 — 压缩段带血统，摘要不可引用

- 所有压缩/折叠产物必须携带 provenance 标记 `source=fold-summary`（区别于 `source=verbatim` 的 journal/event 原文）；
- 规则：**压缩视图不可被引用为原文**——模型需要细节时，唯一合法路径是 journal 回放或记忆检索（ADR-0037 的真值链）；
- 血统的落点（事件 descriptor vs 投影字段）见 §5 待拍板。

### C3 — 刷新 fail-closed：读失败 ≠ 删除

- `_read` 吞错改成**区分返回**：读失败（OSError）≠ 空文件；读失败时**保留旧块**，发布 warning 级别事件（如 `StandingRefreshFailed(names, error)`），错误抛回调用方决定重试；
- 只有**文件从磁盘真正移除**（且按删除语义确认）才允许旧块消失；此时事件必须如实携带 `dropped` 名单，不许再叫 Preserved；
- docstring "A file that is missing or blank drops its old block" 按新语义重写：missing（读失败）保留旧块，blank（空文件）与 deleted（已删）落块。

---

## 3. 非目标

- 不改 journal/event spine 的存储格式（C2 的血统只要求"有标记"，不规定存储）；
- 不碰 step-scoped 压缩预留位本身（C1 只要求未来策略声明合规）；
- 不引入新的审批点（这是纯 fail-closed 语义修复）。

---

## 4. 验收用例

- **T1**：`preserve_standing_sections` 刷新后发布的事件语义——真删除场景下事件携带 `dropped` 名单；读失败场景下不发布 `StandingPreserved`；
- **T2**（fail-closed 核心）：`store.read_text` 抛 OSError（模拟磁盘瞬时故障）→ 旧注入块**保留**、warning 事件发布、异常向上传播；回归今天的"静默清空"行为；
- **T3**：文件从磁盘删除 → 旧块消失（确认现有"真删除落块"语义不被 T2 破坏）；
- **T4**（future）：折叠历史段携带 `source=fold-summary` provenance；用例锁定"摘要不可引用"规则（§5 拍板落点后写）。

---

## 5. 待拍板（arch 轮不擅自决定）

1. **C2 血统落点**：`source=fold-summary` 落在事件 descriptor 上（轻量、随流转）还是投影字段上（可查询、但要改 schema）？倾向前者，等确认；
2. **C3 的 `_read` 改法**：把"吞错返回空串"改成**上抛异常**（调用方统一 fail-closed），还是改成返回 `Result`/`Optional` 让调用方区分"读失败/空文件/已删除"三态？倾向三态（语义最精确），等确认；
3. ADR-0254 已宣称"物理隔离 Compaction 防失忆"——本 ADR 落地后，0254 的相关段落是否需要修订引用（0254 状态为 Accepted，修订需走 ADR 修订流程）。

---

## 6. 与 ADR-0255 的对齐表

| 0255 §4.5 条款 | LCA 对应 | 本 ADR |
|---|---|---|
| compaction 只压对话历史，standing 豁免 | `rehydrate_after_compaction` + `_strip_injected` | C1 升不变量 |
| 新窗口重注 standing | `preserve_standing_sections` + 磁盘现读 | C1 升不变量 |
| 摘要丢细节→走检索链找回，不许当原文引用 | journal 真值（ADR-0037），缺规则 | C2 新增 |
| （Muse 隐含）刷新失败不丢配置 | 今天 fail-open，实锤 | C3 修复 |
