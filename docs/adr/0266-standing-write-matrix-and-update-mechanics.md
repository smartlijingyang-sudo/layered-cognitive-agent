# ADR-0266：Standing 文件写权限矩阵与更新机制契约

## 状态

**Proposed — 2026-10-02**

> **一句话**：把"谁可以改 standing 文件、改之前要不要先读、后台改了怎么办"从约定俗成升为契约——写权限矩阵 + 在线写 read-before-write + 离线写冲突消解 + 读取新鲜度语义。ADR-0255 §2.11（读写权限矩阵）/§2.12（更新机制）的 LCA 落地提案；也是 0255 全线对齐的最后一块——§2.11/§2.12 是 0255 全线中从未被 ADR 评估过的章节（§1.1→0265、§2.11/2.12→本提案、§4.2/§4.3→0260、§4.5→0258、§4.6→0257、§4.7→0259、§4.8→0261、§4.9→0262、§5→不落盘）。

## 0. 背景：生产 Muse 的 §2.11/§2.12

0255 §2.11 定义了逐文件四列矩阵（agent 读/写、用户直接改、后台任务写）：`ALIGNMENT_SYNTHESIS.md` agent 只读（nightly job 写）；`memory/bank/` + `memory/index/` agent 只读不写（runtime 私有）；其余 agent 可写、用户可直接改、`MEMORY.md` 后台做梦管线可写（冲突原地修正）。

0255 §2.12 定义更新机制四要素：**在线写**（turn 内 edit，写 MEMORY.md 前先读当前版、用精确替换）、**离线写**（nightly job 重写对齐综述、relationships loop 维护人物/群组页、做梦管线固化 daily 偏好）、**读盘注入**（每 turn 从磁盘重读、无缓存=热更新）、**版本化**（git 可审计可回滚）。

## 1. LCA 现状（实证，2026-10-02）

### 1.1 写面：工具齐全，矩阵缺失

`lca/infrastructure/tools/assistant/self_manage_tools.py` 共 11 个工具类：**9 写**（`DeleteAssistantSkillTool` / `EditAssistantSkillTool` / `UpdateAssistantSoulTool` / `UpdateAssistantProfileTool` / `UpdateAssistantGrantsTool` / `UpdateAssistantUserTool` / `CreateAssistantToolTool` / `UpdateAssistantToolTool` / `DeleteAssistantToolTool`）+ **2 读**（`ListAssistantSkillsTool` / `ListAssistantToolsTool`）。没有任何文档声明"谁可以写谁"——ADR-0254 v2 只裁决了 SSOT（Markdown=记录真值、bank/index=派生），没回答写权限问题。

### 1.2 写者域划分（G1，已裁决：ADR-0254 v3，d98ec0870）

- ADR-0254 v3 明确"SSOT 按写者域划分"（非反转，是澄清）：
  - **用户域**（USER.md / SOUL.md / TOOLS.md / IDENTITY.md / MEMORY.md 精选版 / people/ / groups/ / daily）：**Markdown 是 SSOT**，v2 在此域成立。系统不得从 JSON 重建这些文件。
  - **Agent 域**（`semantic.json` 及语义管线）：**JSON 是主存储**，v2 的"派生、只读"措辞在此域收回。理由是信息论的不是偏好的：精选投影是 lossy 的，有损投影不可能作为重建源——"索引损坏不丢真值"在 lossy 投影下不成立。当前 JSON-first 写路径（`_append_semantic`，`:454`：先写 `semantic.json`，再精选投影 `MEMORY.md`，投影失败回滚 JSON）是 sound 的，**不动**。
- `assistant_memory.py:1-20` docstring（"The JSON file remains the record store"）与**当前代码行为一致**，是事实陈述不是错误；随迁移更新，不先改（先改=撒谎）。
- 跨域交接点：精选投影（`_project_curated`，含 budget 省略 + `contains_secret` 凭证过滤）是用户域与 agent 域的**定义同步点**——用户写 MD，agent 写 JSON，各自域内单一真值。
- 遗留张力（转 quality lane 实证，不在本 ADR 裁决）：`refresh_user_profile`（`:550`→`:574`）从活跃记录**全量重建 USER.md**——若用户直接改过 USER.md 而系统覆盖，属于"系统重建用户域文件"，按 v3 是 bug。需实证确认是否丢用户编辑。

### 1.3 乐观并发：只覆盖了 semantic 层

`_save`（`:189`）的 `base_text` CAS 校验（`:198-200`）只在 `layer is MemoryLayer.SEMANTIC` 且传入 `base_text` 时生效——即只有 `semantic.json` 写有乐观并发。USER.md 全量重建、SOUL.md 的 Update 系工具写，无 CAS。

### 1.4 热更新：轮询+diff，不是每 turn 读盘（实证缺口 G2）

0255 §2.12 说"每次 turn 重新从磁盘读取，没有缓存层"。LCA 实际是**三层新鲜度语义**，从未成文：

1. **watcher 路径**：`RealTimeStandingWatcher`（`lca/infrastructure/memory/contextfiles/adapters/realtime.py`）后台线程每 **0.5s**（`_DEFAULT_INTERVAL_S = 0.5`，`:30`）轮询一个 home 的 standing 文件，检测时捕获 unified diff，下次装配直接用——变更最快 0.5s 可见，但不是"每 turn 重读"。
2. **poll fallback**：无 watcher 注册时 `poll_standing_home` 同步 diff（`adapters/polling.py:45`，`interval_s: float = 0.5`）。
3. **读盘**：`disk.py:36 read_text` 直接读盘；`FileSnapshot`（`:87`）带 `st_mtime_ns` 新鲜度跟踪。

纠正一条旧记录：`@lru_cache` 只在 `packaged_layout()`（`domain/layout.py:125`，打包默认布局，缓存正确），`layout_for_home()`（`:132`）每次读盘合并 home 覆盖——**无缓存，不破热更新**（backlog 旧记"layout_for_home 有 lru_cache"为误判，本轮实证纠正）。

另：0265 审计发现的节点级 `_refresh_standing` / `_append_standing_diff` 追加管线，与模板装配的带序组合亦未声明（属 G2 的一部分）。

### 1.5 在线写 read-before-write：不存在（实证缺口 G3）

0255 §2.12 要求写 MEMORY.md 前先读当前版（后台可能已改）。`self_manage_tools.py` 的 9 个写类里**无任何 read-before-write 纪律**——全文件唯一的 `read_text` 是工具 yaml 加载（`:449`），Update 系工具写前不读当前版。与做梦管线写 MEMORY.md 的三方写冲突无消解契约。

### 1.6 已有保护（可复用为契约条目）

- `disk.py:53 _refuse_trail_overwrite`：trail 文件拒绝非严格追加写（新文本必须以现有内容为前缀）——daily trail 的写保护已有。
- 凭证过滤：`_append_semantic` 内 `contains_secret` 拒绝凭证形内容进投影（日志留痕 `memory projection rejected credential-shaped content`）。

## 2. 实证缺口

- **G1（写者域划分，已裁决）**：ADR-0254 v3（d98ec0870）——用户域 Markdown SSOT（v2 在此域成立），agent 域 `semantic.json` 是主存储（v2"派生只读"措辞收回）；JSON-first 写路径 sound 不动；docstring 与代码行为一致，随迁移更新。
- **G2（热更新无契约）**：三层新鲜度语义（watcher 0.5s / poll fallback / 读盘）从未成文；节点级追加管线与模板带序组合未声明。
- **G3（在线写无 read-before-write）**：写工具无读后写纪律；与做梦管线/relationships loop 的写冲突无消解契约。
- **G4（矩阵缺失）**：无任何"谁可写谁"文档；9 写类 + 用户直接改 + 做梦管线三方写 MEMORY.md 无契约。

## 3. 契约（草稿）

### C1 写权限矩阵

对照 0255 §2.11，映射 LCA 实际文件与工具；❌=不许，⚠️=受限。**矩阵覆盖 peer 委派**（已裁决）：矩阵管的是"谁能写什么"，peer 只要是 writer 就在表内，不另开旁路——委派不改变写者身份，只改变调用链，权限看最终写者（0257 脱敏信封是调用链约束，不是写权限豁免）。

| 文件 | agent 写通道 | 用户直接改 | 后台写 | 备注 |
|---|---|---|---|---|
| SOUL.md | `UpdateAssistantSoulTool`（0261 C2 fail-closed 守卫） | ✅ | — | 改后必须告知用户 |
| USER.md | `UpdateAssistantUserTool` / `refresh_user_profile` 全量重建 | ✅ | — | 不许脑补未告知字段 |
| MEMORY.md | `memory_add`→`_append_semantic`→投影（精选+凭证过滤） | ✅ | ✅ 做梦管线 | 冲突原地修正（沿用 0255） |
| people/ + groups/ 页 | 事实更新（工具/提示） | — | ✅ relationships loop | 一人/一群一页 |
| TOOLS.md | ✅（教训沉淀） | — | — | 本机 quirks |
| IDENTITY.md | onboarding 工具 | ✅ | — | 经改名流程 |
| `{home}/memory/YYYY-MM-DD.md` | ✅（0260 当场写） | — | — | `_refuse_trail_overwrite` 只许严格追加 |
| `memory/bank/` + `memory/index/`（用户域投影） | ❌（检索只读） | — | ✅ runtime 私有 | 0254 v3：用户域的派生索引，只读、可重建 |
| `memory/semantic.json`（agent 域主存储） | ❌（检索只读） | — | ✅ 语义管线写入口 | 0254 v3：agent 域主存储，不是派生；JSON-first 写路径 sound 不动 |
| ALIGNMENT_SYNTHESIS.md | ❌ | — | ✅（nightly/对齐综述 job） | agent 只读 |

### C2 在线写 read-before-write + 精确替换

写 standing 文件前必须读当前版；用精确替换（非全量重写）保持其他部分不动；写成功后才可向用户确认"记下了"（与 0260 C1 写盘确认门衔接）。

### C3 离线写冲突消解（已裁决：字段级合并、真冲突 fail-closed）

做梦管线 / relationships loop / nightly 与在线写的写冲突：
- **不同字段**的离线/在线写 → **合并**（无实质冲突）；
- **同一 key 不同值** → **fail-closed**，不静默覆盖、不静默合并（静默丢数据且无人知晓）。
muse 思想：可精确判定的地方（字段是否相同）fail-closed，不可判定的不硬拦。MEMORY.md 的精选投影交接点冲突同样适用。

### C4 读取新鲜度语义契约

三层语义成文：watcher 注册时 0.5s diff 事件驱动（新鲜度上限）、无 watcher 时 poll 同步 diff、layout 每次读盘。声明"无缓存"的精确含义：standing 内容无进程级缓存（`packaged_layout` 的 `lru_cache` 仅限打包默认布局，不在热更新路径上）。

### C5 写者域边界（ADR-0254 v3 澄清条目引用）

本 ADR 不重复裁决 G1，引用 ADR-0254 v3（d98ec0870）为权威：
- 用户域 Markdown SSOT；agent 域 `semantic.json` 主存储；精选投影是跨域定义的同步点；
- docstring 与代码行为一致的部分是事实陈述，随迁移更新，不先行"修正"；
- `refresh_user_profile` 全量重建 USER.md 的用户编辑丢失风险，转 quality lane 实证（§1.2 遗留张力）。

## 4. 验收

- **T1**：矩阵表每行有对应机制/测试锚点（C1 每行标注实现位置）。
- **T2**：写者域边界实证——(a) agent 域：semantic write 仍是 JSON-first 写路径（主存储实证，断言 `_append_semantic` 先写 `semantic.json` 再投影）；(b) 用户域：`refresh_user_profile` 不丢用户直接编辑（quality lane 实证，USER.md 全量重建的用户编辑丢失风险）。

## 待拍板（本草稿三项已裁决，无新增待拍板）

原三项待拍板均已由李超授权 Athena 按 muse 思想裁决（2026-10-02），结论已并入正文：
1. G1 修法方向 → 见 C5 / ADR-0254 v3（d98ec0870）：写者域划分，不二选一。
2. C3 冲突消解 → 字段级合并、真冲突 fail-closed（见 C3）。
3. 写矩阵是否覆盖 peer 委派 → 覆盖（见 C1）。

## 决策记录

- 2026-10-02（李超授权 Athena 裁决）：① G1 不做"修 v2 或反转代码"二选一，ADR-0254 出 v3 澄清"SSOT 按写者域划分"（用户域 Markdown SSOT / agent 域 JSON 主存储 / lossy 投影不可重建）；② C3 冲突=字段级合并、真冲突 fail-closed；③ 写矩阵覆盖 peer 委派（权限看最终写者）。
- 草稿修订：2026-10-02 18:09 iter-arch 只读轮按上述裁决重写 §1.2 / §2 G1 / C1 矩阵 bank+index 行拆分 / C3 / C5 / T2 / 待拍板节。
