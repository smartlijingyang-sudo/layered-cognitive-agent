# 架构设计：无状态长期记忆投影与编辑回写机制（一源一镜，镜无状态）

> **状态**：Approved  
> **日期**：2026-10-04  
> **责任边界**：`lca/infrastructure/memory/contextfiles/`、`lca/infrastructure/memory/assistant_memory.py`、`lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py`  
> **Autopilot 级别**：`DRAFT` (AP-05)  
> **对应核心契约**：AGENTS.md §2.2（投影不得反向写事实、事实与投影分离）、ADR-0246/0247（记忆分层与结构化记录）、ADR-0266（Standing 文件写权限矩阵）

---

## 1. 背景与根因剖析

### 1.1 现状与痛点
在现有 LCA 架构中，长期记忆在逻辑上存在两个存在形态：
1. 底层持久化存储：`memory/semantic.json`（结构化 `MemoryRecord` 记录列表）。
2. 面向人类与模型的常驻展示文件：`MEMORY.md`。

过去实现中，由于将 `MEMORY.md` 投影当成了有状态的同步对象，产生了一系列系统性痛点：
* **骨架吞噬（Skeleton Collapse）**：当用户录入 `identity` 类信息（如性别、家庭成员）后，`semantic.json` 写入成功，但因为没有纯 `fact` / `preference` 记录，底层投影器 `_sections()` 在空条目时直接 `continue` 跳过，导致 `## Preferences` 和 `## Facts` 二级标题从 `MEMORY.md` 中彻底消失，仅剩孤立的系统头部声明。
* **分流认知撕裂**：用户通过对话明确告知的偏好与事实，由于 `category="identity"` 被硬编码分流到了 `USER.md`，而在 `MEMORY.md` 中完全不可见，用户误以为记忆没有生效或丢失。
* **直接编辑单向覆盖**：在 Web 界面或通过 `PUT /v1/assistants/{id}/standing-files/MEMORY.md` 修改 `MEMORY.md` 时，后端仅执行了磁盘原子写（`write_text`），完全未与 `semantic.json` 对齐。一旦后台或下次会话再次触发 `_project_curated`，用户的编辑修改就会被直接抹去并发生数据丢失。

### 1.2 架构破局：一源，一镜，镜无状态
**核心公理**：
* `memory/semantic.json`：**唯一真理源（Single Source of Truth, SSOT）**。所有记忆事实由其唯一掌控。
* `MEMORY.md`：**纯函数投影（Pure Functional Projection）**。
  $$\text{render\_memory\_markdown}(\text{records}) \to \text{markdown\_str}$$
  它不拥有任何独立状态，磁盘上的 `.md` 仅为只读导出缓存。
* **编辑即输入事件（Edit as Input Event）**：对 `MEMORY.md` 的编辑提交，绝对不视为“保存一个文件”，而是视作向底层 `semantic.json` 发送的结构化增删改操作流。

---

## 2. 负向边界声明（Does NOT Own - AP-01）

为防止范围蔓延（AP-01），本设计严格限定边界：
1. **不拥有**：`USER.md` 的解析回写逻辑（`USER.md` 仍由 `ProfileBackfillService` 单向从 `identity` 记录回填生成）。
2. **不拥有**：非 memory 类型的其他 standing 文件（如 `SOUL.md`、`CONSTITUTION.md`、`TOOLS.md` 等维持 ProfileCatalog 原有路径）。
3. **不拥有**：`MemoryRecord` 底层存储格式的重构（保持字段与现有 ADR-0246/0247/0254 完全兼容，无需数据迁移）。

---

## 3. 详细设计与核心组件

### 3.1 纯函数投影器（Pure Functional Projector）
投影器收敛为一个独立、无副作用、易于 Golden Test 的纯函数：
* **模块位置**：`lca/infrastructure/memory/contextfiles/domain/curated.py`
* **函数签名**：
  ```python
  def render_curated_memory_markdown(
      records: Sequence[MemoryRecord],
      *,
      char_budget: int = 12_000,
  ) -> str
  ```
* **输出规范**：
  * **标准头**：固定包含 `# 长期记忆` 及系统声明；
  * **骨架保底**：`## Preferences` 与 `## Facts` 永远保留，即使列表为空也输出占位符（如 `- _（暂无偏好记录）_`），绝不允许吞噬标题；
  * **Embedded ID 锚点**：每个渲染的 Bullet 行尾嵌入轻量 HTML 注释 `<!-- id:mem_xxx -->`。在前端与常规 Markdown 渲染时不可见，在编辑回写时提供确定性唯一索引。
* **分流逻辑**：
  * `category == MemoryCategory.PREFERENCE` $\to$ `## Preferences`；
  * `category == MemoryCategory.FACT` $\to$ `## Facts`；
  * `category == MemoryCategory.IDENTITY` $\to$ 忽略（保留给 `USER.md`）。

### 3.2 编辑事件解析器（Markdown Edit Intent Parser）
当用户修改并提交 `MEMORY.md` 文本时，由专门的领域服务解析变更：
* **模块位置**：`lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py`
* **服务类**：`MemoryEditSyncService`
* **处理流程**：
  1. 解析提交的 Markdown 文本，提取 `## Preferences` 与 `## Facts` 下的 Bullet 列表与嵌入的 `<!-- id:xxx -->`；
  2. 加载当前活跃的 `MemoryRecord` 集合；
  3. 执行比对计算三类原子操作：
     * **新增（ADD）**：用户手工新增的行（无嵌入 ID），创建新的 `MemoryRecord`（`source="user_edit"`）；
     * **修改（SUPERSEDE）**：行文本发生变动但携带有现有 ID，调用 `memory.supersede(old_id, new_record)` 建立版本血缘；
     * **删除（DELETE）**：原存在于 `semantic.json` 的 active ID 在提交的 Markdown 中消失，调用 `memory.remove(old_id)` 标记软删除；
  4. 提交变更落库至 `memory/semantic.json`；
  5. 重新调用 `render_curated_memory_markdown` 刷新磁盘 `MEMORY.md` 缓存，返回最新生成的文本与版本标识。

### 3.3 写入窄门收敛（Execution Gate Enforcement）
彻底消灭直接写盘路径：
* **路由拦截**：在 `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py` 的 `update_standing_file` 中：
  * 拦截 `filename == "MEMORY.md"`；
  * 严禁调用 `file_path.write_text(new_content)`；
  * 改为交由 `MemoryEditSyncService.apply_markdown_edit(assistant_id, new_content)` 统一处理。

### 3.4 Prompt 实时装配保证
* `MEMORY.md` 作为 `layout.toml` 中的核心常驻文件，已在 `persona_from_home` 中组装至模型的 `backstory`。
* 纯函数投影刷新文件后，下一轮 Prompt 渲染自动重读最新磁盘物化副本，实现热更新。

---

## 4. 测试不变量与断言矩阵（Invariants & Test Matrix - AP-02）

所有架构不变量必须由自动化测试保障：

| 不变量编号 | 核心要求 | 验证方式 |
|---|---|---|
| **INV-MEM-01** | **纯函数等价性**：相同输入记录必定产生相同 Markdown，无隐藏环境副作用 | Golden Test 严格比对输出文本 |
| **INV-MEM-02** | **骨架永不坍塌**：空记录或只有 identity 记录时，`## Preferences` 与 `## Facts` 依然完好保留 | 空记录及边界测试断言标题存在 |
| **INV-MEM-03** | **分类隔离**：`identity` 记录绝对不渗入 `MEMORY.md` 投影 | 注入各种分类断言输出小节的纯洁性 |
| **INV-MEM-04** | **编辑回写三态精确性**：无 ID 行触发 ADD，改动文本触发 SUPERSEDE，缺失行触发 DELETE | 单元与集成测试验证 `semantic.json` 状态转移 |
| **INV-MEM-05** | **无损往返重构（Roundtrip）**：原样提交投影内容，不产生多余的修订或记录变更 | 往返测试断言前后记录列表完全一致 |
| **INV-MEM-06** | **写入窄门收敛**：通过 `PUT` 端点更新 `MEMORY.md` 必须产生 `semantic.json` 的更新事件与版本递增 | 路由级集成测试断言 |

---

## 5. 迁移与兼容性考虑

1. **旧文件兼容**：对已经存在但缺少 `<!-- id:xxx -->` 注释的老 `MEMORY.md`，首次运行纯函数投影时自动补齐注释，或在编辑解析时退水为内容指纹哈希匹配。
2. **零数据库迁移**：直接复用已有 `AssistantMemory`、`MemoryRecord`、`semantic.json` 架构，无破坏性变更。
