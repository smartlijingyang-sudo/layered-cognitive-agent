# Muse 动态栏与任务详情双栏高保真对齐设计规范

> **文档版本**: 1.0.0  
> **创建日期**: 2026-10-03  
> **状态**: Approved (已获用户逐节审批确认)  
> **自治等级 (Autopilot Level)**: DRAFT (涉及关键观测面 UI 补丁与意图解构契约，严格 TDD 验证)  
> **对照基准**: Meta Muse 生产实机截图（`activity-drawer-today.png`, `activity-task-detail-coldstart.png`, `activity-task-detail-grep.png`）  

---

## 1. 背景与对齐目标

在 LCA 现有右侧抽屉「动态」面板与详情弹窗中，存在机械拆解（将一次工具调用生硬切割为“思考/调用/回执”套话）、硬编码技术标签（如 `COMMAND`、`TOOL` 等 badge）、以及默认回退为 `"Running command"` 的死板文案问题，与真实 Muse 产品的工程沉浸感存在显著差距。

根据用户提供的 3 张 Muse 生产环境实机截图，本次设计的核心目标是**端到端全量对齐**：
1. **抽屉动态列表**：彻底消灭 `COMMAND` 等底层技术徽标，还原为极简高雅的纯中文自然语言信息流（深色圆角勾选框 + 人读动作标题 + 结果摘要 + 易读时间）；
2. **任务详情双栏弹窗**：
   - 顶部还原浅绿底深绿字胶囊药丸（`已完成`）+ 任务大标题；
   - 左栏还原真实**动作步骤树**（首节点为 `已开始` 锚点，后续按执行时序排列真实子任务，如“读取 activity_projector.py 的 seed_from_traces 方法”、“在LCA代码中检索...”等）；
   - 右栏还原**5 大高保真证据板块**（动作说明、`执行的命令::` bash 语法高亮代码块、执行元数据、代码高亮证据/检索结果、加粗「验证结论」）。
3. **弹性双轨架构（拒绝硬编码）**：唯一真值来自底层 Spine/Journal 事实，基于通用工程动词语义解构器（自动解析 git/grep/sed/pytest/文件读写等参数）+ 认知直出与异步轻量小模型提炼，确保对任何工程场景自适应泛化，绝无硬编码死字符串。

---

## 2. 架构边界与职责守则

### 2.1 明确边界 (Owns & Does NOT Own, AP-01)
* **Owns（本次构建）**：
  1. **动态意图解构与证据生成引擎**：升级 [`ActivityIntentNamer`](file:///home/lichao/layered-cognitive-agent/lca/contracts/models/observability/activity.py)，基于通用语义模式动态解构命令（文件名、行号、关键词、分支等），支持从 Thinking/Reflect 中无缝提取自然语言动作；
  2. **结构化证据契约（`StepEvidence`）**：定义包含 `command`、`exit_code`、`duration_ms`、`code_evidence`、`conclusion` 的标准化步骤证据结构；
  3. **前端高保真双栏组件补丁**：重构 [`AssistantStatusDrawer.tsx`](file:///home/lichao/layered-cognitive-agent/deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx)，实现抽屉无徽标自然语言流、顶部状态药丸、左侧步骤树与右侧 5 要素证据面板；
  4. **全套自动化测试套件**：编写单元测试、补丁测试与端到端场景测试，刚性守卫 INV-01 至 INV-06。
* **Does NOT Own（严格禁止越权修改）**：
  1. 严禁改动执行窄门与沙箱机制（C10 执行窄门，不触碰 `SafeExecutor` / `Sandbox`）；
  2. 严禁修改五相认知循环语义（C1 认知闭集，不修改 Perceive $\to$ Think $\to$ Act $\to$ Reflect $\to$ Remember 核心时钟）；
  3. 严禁在观测路径引入控制面写副作用（C7 控制与观察严格分离）；
  4. 严禁将任何非 LCA 框架宿主机资产提交至本仓库。

---

## 3. 动态意图与结构化证据生成架构

### 3.1 唯一事实源 (SSOT)
所有展示数据严格溯源自底层真实记录：
- 实时流：Spine 事件（`step.tool_call.record`、`phase.tool.call.start`、`body.tool.execute.*`）；
- 历史回填与详情：[`traces/runs/{run_id}/journal.json`](file:///home/lichao/layered-cognitive-agent/traces/runs/run_00ec7ac9247d/journal.json) 中的完整 steps、thinking、tool_calls 与 tool_results。

### 3.2 三层递进意图提炼机制
```text
                         ToolCall & Arguments
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
▼                                 ▼                                 ▼
【第一层：认知直出】              【第二层：通用工程语义解构】         【第三层：语义兜底与小模型】
Thinking 提取意图首句             解析命令行首动词与参数               基于工具名+主参数生成
如 "李超要求...我需要先检索..."   • git worktree/branch → 创建工作树  如 "执行 memory_search"
→ "在LCA代码中检索相关函数"       • sed/cat/read_file → 读取指定文件   (绝无 "Running command")
                                  • grep/rg → 检索关键词
                                  • pytest/python → 执行测试验证
                                  • write/touch → 创建脚本文件
```

### 3.3 结构化证据契约 (`StepEvidence`)
每个步骤派生为右侧 5 大要素模型：
```typescript
interface StepEvidence {
  id: string;
  step_title: string;          // 步骤意图大标题
  narrative: string;           // 流畅的自然语言动作叙述
  command?: string;            // 真实执行的命令行 (语言: bash)
  exit_code?: number;          // 退出码 (例如: 0)
  duration_ms?: number;        // 执行耗时 (例如: 3841ms)
  truncated_boundary?: string; // 截取标记 (例如: "ZZSTART / ZZEND")
  code_snippets?: Array<{      // 提取的代码证据 (带行号标注与代码块)
    label: string;             // 例如: "第88-100行: ActivityProjector.__init__ ..."
    code: string;
    language: string;
  }>;
  search_results?: Array<{     // grep 等结构化检索结果
    index: number;
    location: string;          // 例如: "standing.py:56"
    match: string;
  }>;
  conclusion?: string;         // 自然语言验证结论
}
```

---

## 4. 前端 UI 高保真还原规范

### 4.1 抽屉列表还原规范（对照 `activity-drawer-today.png`）
1. **顶栏**：
   - 大圆形头像，右下角深色浮动圆形编辑铅笔按钮；
   - 助手名称标题，下方绿色闪电图标 + `已连接` 状态；
   - 4 个等宽 Tab 图标（列表、审批、即将到来、指纹/身份）置于深色药丸分段器中。
2. **列表条目 (Activity Row)**：
   - 左侧：深色圆角矩形方框容器，内嵌圆形勾选图标（完成态白勾，运行态圆环，失败态红叉）；
   - 中间：
     - 行 1（Title）：加粗白色自然语言标题（如 `验证Activity重启与事件完整性`）；
     - 行 2（Summary）：浅灰色一句话关键结果摘要（如 `验证重启后36个活动完整恢复`）；
     - 行 3（Time）：友好时间戳（如 `4:39 pm`）；
   - **徽章清洗**：彻底清除 `COMMAND`、`TOOL`、`SUBAGENT` 等技术标签。

### 4.2 任务详情双栏弹窗还原规范（对照 `activity-task-detail-*.png`）
1. **Header**：
   - 左上角：浅绿底深绿字圆角状态胶囊药丸 `已完成`（运行中蓝色 `进行中`，失败红色 `执行失败`）；
   - 下方：任务大标题（`验证Activity重启与事件完整性`）；
   - 右上角：关闭按钮 `✕`。
2. **左栏步骤树 (Timeline Step Tree)**：
   - 纵向时间轴贯穿线；
   - 首节点：灰色小实心圆点 + `已开始`；
   - 中间节点：圆形状态图标（`✓`、文档 `📄`、终端等）+ 自然语言意图标题；
   - 选中态：深色半透明圆角矩形背景高亮。
3. **右栏证据面板 (Evidence & Output Pane)**：
   - 结构化分为 5 大卡片/区块：
     1. 大字二级标题 + 动作叙述；
     2. `执行的命令::` 语法高亮代码块（顶部带 `bash` 标签、复制与下载按钮）；
     3. 运行元数据点标（`· 退出码: 0, 耗时: 3841ms`，边界截取说明）；
     4. 代码内容卡片（行号标注 + 语法高亮代码段）或结构化检索匹配列表；
     5. 加粗「验证结论」小标题 + 自然语言评估段落。

---

## 5. 架构不变量与自动化测试矩阵 (AP-02)

| 不变量 ID | 不变量描述 | 验证方式与测试用例 |
|---|---|---|
| **INV-01** | **动态意图零硬编码**：`ActivityIntentNamer` 严禁输出 `"Running command"` 等死板占位符，必须动态解构出精准中文意图短语。 | `test_activity_contract.py`：对 10+ 类常见工程命令参数化断言，0 命中 `"Running command"`。 |
| **INV-02** | **执行证据真实溯源**：弹窗右侧展示的命令、耗时、退出码与代码片段必须严格源自底层真实记录，严禁捏造。 | `test_status_screen_invariants.py`：注入真实 run journal，断言提取结果与底层事实 byte-level 一致。 |
| **INV-03** | **抽屉列表纯净自然语言**：动态栏条目绝不渲染 `COMMAND`、`TOOL` 等底层技术徽标。 | `test_assistant_status_drawer.py`：断言抽屉列表项中不再出现技术徽标节点。 |
| **INV-04** | **步骤时间轴拓扑完整性**：左侧时间轴首节点必为 `已开始`，后续按真实动作时序排列，并保持选中高亮。 | `test_assistant_status_drawer.py`：断言生成的 steps 数组以首节点为起点并按真实动作映射。 |
| **INV-05** | **右侧证据 5 要素结构化闭环**：代码提取与命令步骤必须结构化生成叙述、命令块、元数据、证据块、验证结论 5 大要素。 | `test_activity_contract.py`：验证证据提取模型 5 要素完整性。 |
| **INV-06** | **只读观测隔离**：整个动态栏与详情弹窗查询与展示为纯只读投影，绝不触发写副作用（遵守 C7）。 | `test_status_screen_invariants.py`：验证多次查询前后底层事实库与 State 零变化。 |
