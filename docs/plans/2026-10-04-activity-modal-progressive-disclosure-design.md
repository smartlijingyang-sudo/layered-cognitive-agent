# 动态详情弹窗渐进式披露与高信息量呈现设计规范 (Design Spec)

## 一、 背景与设计目标

### 1.1 现状与痛点
当前 LobeHub 前端 LCA 助理状态抽屉（`AssistantStatusDrawer.tsx`）的活动详情弹窗存在以下问题：
1. **关键结论被埋没**：原先的“验证结论 / 执行异常”横幅固定被垫在弹窗最底部，用户必须滚到最下方才能看清“事情到底成了没”。
2. **左侧列表单调**：步骤仅显示单行文字，缺乏时序连贯感（Timeline）与多态语义图标，且缺少执行耗时等关键指标。
3. **极长内容缺乏防护**：当模型思考推理（Thinking Reasoning）非常详尽或工具执行了数十上百行的复杂脚本时，页面易被单一部分无限撑高，信息密度失控。
4. **工程深层数据难以查阅**：后端 `GET /runs/{run_id}` 实际上已沉淀了完整的 `model`（如 `qwen3.7-plus`）、`latency_ms`、`prompt_tokens`、`completion_tokens`、`tc.arguments` JSON 与 `tr.stdout_head/stderr`，但在前端弹窗中被省略或未充分呈现。

### 1.2 设计目标
采用 **“默认极简 Muse 风格面 + 按需展开 Devin 级工程深度探测（渐进式披露 / Progressive Disclosure）”**：
- **5 秒一眼定心（Default Surface）**：结论前置（Hero Verdict Card），自然语言叙述，关键命令与退出码。
- **极致工程透明（Collapsible Inspection Zone）**：默认收起折叠面板，一键展开模型 Token 指标、结构化 JSON 参数、原始完整 I/O 与完整思考链溯源。
- **长文本与长脚本防爆仓**：长推理带遮罩展开，长脚本带代码行数统计、视口约束与丝滑滚动。
- **100% 真实数据（Zero Mock Invariant）**：严禁伪造数字，全量指标严格绑定后端事件账本真值。

---

## 二、 架构与模块边界 (AP-01)

### 2.1 负责范围 (Owns)
- `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`：
  - 左侧步骤时间轴样式与组件重构。
  - 右侧主面板顶部 Hero 结论卡布局。
  - 长文本折叠渐隐与代码块视口控制。
  - 底部“深度工程观测与诊断数据”折叠抽屉/面板组件。
- `tests/deploy/test_step_state_machine_purity.py`：
  - 自动化 pytest 契约测试，断言数据转换纯度、字段解析、严格状态机 guard 与零 Mock 数据不变量。
- 热补丁自动化同步：
  - `python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer`。

### 2.2 禁止范围 (Does NOT own)
- 不修改后端 Journal、Session、Spine 账本与存储结构（后端当前 schema 已完全满足需求）。
- 不引入外部未授权库，基于已有的 Ant Design、Lucide 图标与 CSS Modules。
- 不修改与本弹窗无关的前端核心路由或页面。
- 绝不在 LCA 仓库提交宿主机级运维脚本或机器配置。

### 2.3 自主级别 (Autopilot Level)
- **AP-05**：单流执行，每步均通过热补丁应用、语法校验与 pytest 回归套件确定性验证。

---

## 三、 左侧栏：时间轴轨道与多态语义节点

### 3.1 视觉要素与结构
1. **连续垂直时间线（Vertical Timeline Connector）**：
   - 步骤节点左侧带连续细轴线（`#22272e`），首尾节点优雅收口，突出“行动时序流”。
2. **多态语义图标（Semantic Node Icons）**：
   - `●` (浅灰 `#8c8c8c`)：生命周期节点（如 `已开始` / `任务初始化`）。
   - `✔` (荧光青绿 `#c4f042`)：顺利完成的操作（Exit code 0, ok）。
   - `📄` (清爽天蓝 `#60b1ff`)：文件读取、代码检索、切片查看类操作。
   - `✕` (警示绯红 `#f4416c`)：异常或失败步骤（Exit code != 0 或明确 error）。
   - `◐` (呼吸脉动蓝 `#1677ff`)：仅当处于 `running` 状态时呈现微弱呼吸灯脉动动效，非 running 状态严禁动画。
3. **真实耗时徽标（Latency Badge）**：
   - 在步骤标题右侧附带精细微标（如 `14ms`、`1.2s`），全部来自后端真实的 `tr.latency_ms` 或 `ev.duration_ms`。
4. **悬停与选中微交互**：
   - 选中态：`background: rgba(255, 255, 255, 0.06)`，左边缘带高亮竖条指示，点击与右侧内容严格联动。

---

## 四、 右侧正文：渐进式披露面板

### 4.1 首屏默认层 (Default Surface: 5 秒一眼定心)

1. **顶部 Hero 验证结论卡（结论前置）**：
   - 位于步骤大标题紧随其后的首要位置。
   - 成功态：微绿渐变背景（`rgba(196, 240, 66, 0.08)`）+ 翡翠绿文字 + `✓ 验证结论：动作执行完成，符合预期，系统状态与契约保持一致。`
   - 失败态：深红渐变背景（`rgba(244, 65, 108, 0.12)`）+ 绯红文字 + `✕ 执行异常：退出码 N，错误原因...`
2. **步骤大标题与叙述段落（Action Narrative）**：
   - 标题：粗体显示当前步骤名称（如 `检查系统负载状态`）。
   - 叙述：自然语言解释智能体的动作意图与分析。
   - **长文本防爆机制**：超出 120 字时，视口约束为 `maxHeight: 140px`，底部呈现渐变半透明遮罩，并提供 `展开全部思考 (共 N 字) ▾` / `收起 ▴` 切换微按钮。
3. **执行命令与代码切片（Command & Snippets）**：
   - 采用等宽字体与语法高亮。
   - **长脚本防爆机制**：
     - 顶部标注栏：显示代码语言、行数（如 `bash · 86 行`）与一键复制按钮。
     - 视窗高度锁定：默认 `maxHeight: 240px`，超出部分出现丝滑纵向滚动条，支持横向平滑滚动（`overflowX: 'auto'`），避免折行错乱。
4. **元数据信息行（Metadata Bullets）**：
   - 退出码（绿色 `0` / 红色非 0）、耗时（`14ms`）、边界截取标记（`截取提示`）。

---

### 4.2 按需深查区 (Collapsible Inspection Zone: Devin 级工程深度)

默认以优雅的折叠栏收起，标题为：  
`🔍 深度工程观测与诊断数据 (按需展开)`。

展开后包含 4 个结构化观测卡片：
1. **卡片 A: 模型与决策指标 (Model & Token Metrics)**：
   - 调用的模型名称（如 `qwen3.7-plus`）。
   - 思考耗时（`thinking.latency_ms`）。
   - Token 开销真值：`Prompt Tokens: X`，`Completion Tokens: Y`。
   - 决策策略标识：`decision: continue / finish / call_tool`。
2. **卡片 B: 结构化调用参数 (Structured Arguments)**：
   - 将 `tc.arguments` 格式化为整洁对齐的 JSON 树状展示，支持一键复制代码。
3. **卡片 C: 原始终端 I/O (Raw Stdout / Stderr)**：
   - 完整展示工具返回的原始标准输出和标准错误输出。
   - 针对几万字终端输出提供限制视窗（`maxHeight: 300px`）与截断提示。
4. **卡片 D: 完整思考链溯源 (Full Thinking Chain)**：
   - 还原智能体做决策时的完整推理原文（`thinking.reasoning`），支持 Markdown 格式与代码块渲染。

---

## 五、 不变量与契约矩阵 (AP-02)

| 不变量编号 | 规则描述 | 违背判定 |
|---|---|---|
| **INV-MODAL-01 (Zero Mock)** | 任何 Token、耗时、模型名、退出码必须 100% 映射自真实后端事件，严禁硬编码或假数据 | 若在无后端数据时渲染臆造的数字，即视为违规 |
| **INV-MODAL-02 (Strict Error Guard)** | 严禁将 `undefined` 退出码当做错误；仅当 `typeof exit_code === 'number' && exit_code !== 0` 或 `ok === false` 时才判红 | 任务启动节点、交付结果节点绝不能被误判为执行异常 |
| **INV-MODAL-03 (Progressive Boundary)** | 默认表面严禁被未格式化的大 JSON 或全量终端输出撑爆，深层数据必须收敛于折叠区 | 首屏高度异常膨胀或缺少折叠收敛 |
| **INV-MODAL-04 (Timeline Determinism)** | 左侧时间轴节点的激活状态必须与右侧详情 100% 对应；支持点击快速切换 | 切换节点右侧内容未刷新或数据错位 |
| **INV-MODAL-05 (Single-Flow Test Isolation)** | 所有交互变更与字段解析必须由自动化 pytest 套件覆盖，不破坏现有 27 项纯度测试 | `pytest tests/deploy/test_step_state_machine_purity.py` 必须全量通过 |

---

## 六、 实施与验证步骤

1. **测试先行 (TDD)**：
   - 在 `tests/deploy/test_step_state_machine_purity.py` 中补充渐进式数据字段提取测试、长文本截断逻辑测试与零 Mock 纯度测试。
2. **组件升级**：
   - 在 `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx` 中实现左侧时间轴、顶部 Hero 结论卡、长脚本视口保护与按需折叠深查区。
3. **热补丁验证**：
   - 运行 `python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer` 同步至运行环境并确认无语法报错。
4. **自动化回归**：
   - 运行完整测试套件，确认全部测试通过（无新增既有失败）。
