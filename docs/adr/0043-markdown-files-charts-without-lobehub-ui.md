# ADR-0043: Markdown 渲染扩展、生成文件产物展示与图表能力；不引入 @lobehub/ui 作为运行时依赖

## 状态

Accepted

## 背景

以下几点为本次代码库核实事实（对照 2026-08 快照）：

1. **`web/package.json` 当前运行时依赖**：`react`/`react-dom`、
   `@radix-ui/react-{dialog,switch,tabs}`、`react-markdown` + `remark-gfm`、
   `mermaid`、`lucide-react`、`zustand`、`idb-keyval`、`tailwindcss`。**没有
   antd、没有 `@lobehub/ui`、没有任何 motion/framer-motion 类动效库。**

2. **`docs/proposals/0001-frontend-productization.md` 已经就「是否引入完整
   组件库」做过明确决定，且尚未被推翻**：
   - §4.4：「无头组件库 + 自有令牌：Radix UI primitives ... 配色/间距/圆角
     完全走自定义 CSS 变量令牌，不锁进某个预制皮肤（如 MUI）」
   - §5.3：「不引入：完整组件库（MUI/AntD 类）——与 4.1 的视觉立场冲突，
     会强绑定预制皮肤」
   - §4.1 视觉立场明确要求避开「与本产品无关的通用聊天壳雷同」

3. **`docs/proposals/0002-lobehub-parity-polish.md` §3 已经明确排除动效
   库**：「不引入 `framer-motion` 等动效库」；`web/src/tokens/design-tokens
   .css` 也印证了这一点——`--motion-fast: 180ms` 是纯 CSS 变量方案，没有 JS
   动效运行时。

4. **`@lobehub/ui` 的 `ConfigProvider` 要求传入一个 motion 组件**（本次
   调研已核实），无论走 legacy antd 路径还是新 `/base-ui` 路径都不能豁免
   这一要求。这与上一条已生效的决定直接冲突。

5. **`@lobehub/ui/base-ui` 路径仍处于迁移期**（本次调研已核实）：并非所有
   组件都已从 antd 迁移完成，需要逐组件查文档确认是否标记 Deprecated。在
   这个状态下把它当作新代码的基础依赖，等于把「哪些组件其实还在用 antd」
   这个不确定性直接吃进项目。

6. **`web/.dependency-cruiser.cjs` 已经把五层分层的精神带进前端**：
   `components/` 禁止直接依赖 `transport/`（须经 `api/`）、`domain/` 禁止
   依赖 `renderers/components/shell`、核心层禁止依赖 React。任何新组件/新
   依赖都要落在这套现有边界里，不能绕过。

7. **`web/src/components/shared/MarkdownContent.tsx` 不是一个可以整体替换
   的叶子组件**：渲染前必经两道领域相关的预处理——`sanitizeAssistant
   DisplayText`（从 Decision JSON 里剥离用户可见正文，对齐 `lca
   /layer1_cognitive/brain/decision_parser.py`，与 ADR-0041 的
   answer-delta 归属判定同源）与 `normalizeChatMarkdown`（streaming/final
   两态的 LLM 输出清洗）。任何「迁移 Markdown 渲染」的方案，如果意味着
   删除这个文件整体换成外部库组件，就会连带丢掉这两步与后端契约对齐的
   预处理。

8. **SSE 渲染管道已经是这个项目投入最深、ADR 覆盖最完整的部分**：
   `transport/fetch-sse-transport.ts`（手写帧解析 + Last-Event-ID 断线
   续传）→ `contracts/stamped.ts`（Python 单一事实源生成）→
   `projectors/chat-projector.ts` / `trace-projector.ts`
   （journal-as-truth 归约，ADR-0037）。ADR-0038 定义了 provider-neutral
   流式事件契约，ADR-0041 定义了「终态归属交给前端投影层判定」的具体归约
   规则（缓冲 `StepTextDelta` 直到 `DecisionMade`/`*Finished`）。这套语义
   （团队委派、决策、洞察事件的可见性分层）是团队协作产品特有的，通用
   单 Agent 聊天 SSE 库不具备。

9. **图表能力已经存在，且不经过任何 UI 组件库**：`TraceAccordion.tsx`
   直接调用 `mermaid` 包渲染协作时序图（`domain/sequence-diagram.ts`
   产出 Mermaid 语法字符串）。缺口只有一处——助手回答正文里的 ```mermaid
   代码块，`MarkdownContent.tsx` 目前把它当普通代码块渲染成纯文本，没有
   接到已经安装的 `mermaid` 渲染路径上。

10. **文件上传/生成文件在后端完全不存在，不只是前端缺失**：
    `gateway/app.py` 现有路由为 `/runs`、`/runs/{id}/cancel`、
    `/runs/{id}/events`、`/health`、`/conversations*`，没有任何文件相关
    端点；`lca/layer0_infra/tools/` 只有 `calculator_tool.py`/
    `weather_tool.py`，没有文件生成类工具。唯一已经存在、结构上贴近
    「文件产物」的现成通道是 `lca/layer0_infra/transport/a2a_transport
    .py`——它已经在解析 A2A 协议的 `artifacts[].parts[]`，但当前实现只取
    `part.kind == "text"`，file/data 类型的 part 会被直接丢弃。

## 决定

### 一、Markdown 渲染扩展：在现有 `MarkdownContent.tsx` 管道内原地增强，不替换为 `@lobehub/ui` 的 `Markdown` 组件

新增能力（KaTeX 数学公式、回答正文内的 Mermaid 图表、代码块语法高亮）全部
作为 `ReactMarkdown` 的插件/`components` 覆盖项接入现有文件，
`sanitizeAssistantDisplayText` → `normalizeChatMarkdown` → `ReactMarkdown`
这条既定顺序不变。语法高亮沿用 `docs/proposals/0002-lobehub-parity-polish
.md` §2.4 已经给出的方向（`shiki` 或等价方案 + 懒加载），本 ADR 视为该
待办的正式拍板，而非另开一条路。

### 二、生成文件产物展示：新增自建 `GeneratedFileCard`，不引入 `DownloadButton`/`FileTypeIcon`/`HtmlPreview`/`CodeEditor`

用现有 `lucide-react` 图标集 + 原生 `<a download>`/`<iframe sandbox>`
（HTML 预览场景）实现，字段形状对齐 A2A `artifact.parts[]` 里 file part
的既有结构（`name`/`mimeType`/字节或 URI 二选一），而不是发明一套无关的
ad hoc 结构——为背景 #10 提到的、当前被丢弃的 A2A file part 预留一条对齐
路径。

### 三、文件上传：新增自建组件，走 `api/` 层，不引入 antd `Upload`

原生 `<input type="file">` + drop 事件，附件预览复用 `lucide-react` 图标
（而非库的 `FileTypeIcon`）。落点是 `Composer.tsx` 新增一块附件区（效果上
等价于 `ChatInputArea` 的 `topAddons` 插槽，但不引入该组件本身）。任何
网络请求必须经过新建的 `api/files.ts`，不得在 `components/` 里直接
`fetch`——这是 `.dependency-cruiser.cjs` 现有 `components-no-transport`
规则的自然延伸，`api/files.ts` 与 `api/runs.ts`/`api/conversations.ts`
同构。

### 四、SSE 渲染管道维持现状，不做任何迁移

`FetchSseTransport`、`contracts/stamped.ts`、`chat-projector.ts`、
`trace-projector.ts`，以及 ADR-0037/0038/0041 定义的归约语义全部不变。
新增的文件产物/附件信息作为新的 journal 事件类型（后端待定）或 `Turn`
领域字段接入现有归约器，不新建一条平行的流式通道。

### 五、视觉上继续对齐 LobeHub 观感，但走「自有令牌 + Radix + Tailwind」路线，不引入 `@lobehub/ui` 的 `ConfigProvider`/主题系统

「像 LobeHub」这件事本身不是新目标——`docs/proposals/0001-frontend
-productization.md` §4 的设计系统、`docs/proposals/0002-lobehub-parity
-polish.md` 的收尾走查已经在做，且明确选择了「参考其模式、不锁定其皮肤」
的路线（`ChatMain.tsx` 注释「LobeHub 式布局」即是证据）。本 ADR 不改变
这个路线，只是把它显式应用到 Markdown/文件/图表这三块新能力上。

## 放弃的方案

1. **引入完整 `@lobehub/ui`（经典 antd 路径）** —— 与背景 #2 已生效的
   「不引入完整组件库」决定直接冲突；antd 路径本身在上游也已经进入被库
   作者标记 Deprecated 的过渡期，现在绑定等于绑定一个正在被放弃的路径。

2. **引入 `@lobehub/ui/base-ui`（新路径）** —— 表面上摆脱了 antd 运行时，
   但仍然：(a) 通过 `ConfigProvider` 强制要求 motion 组件，与背景 #3 已
   生效的「不引入动效库」决定冲突；(b) 处于逐组件迁移期（背景 #5），把
   哪些组件已经/尚未迁移到 base-ui 这一不确定性带入项目；(c) 与已经采用
   并调好令牌的 Radix primitives 语义重叠（Dialog/Tabs/Switch 均已有），
   双跑一套无头组件库没有净收益。

3. **只单独引入 `@lobehub/ui` 的 `Markdown` 组件，其余不装** —— 常见的
   「只取最值的那一件」折中，予以否决：(a) 背景 #7 已说明它不能直接替换
   `MarkdownContent.tsx`，只能包在预处理管道之后，即便只用这一个组件也
   要处理这层适配；(b) 该组件内部的 shiki/katex 打包方式与版本不受我们
   控制，一旦升级即被动跟随；(c) 决定一/二给出的原生实现（`remark-math`/
   `rehype-katex`/`shiki` 懒加载 + 复用已装的 `mermaid`）在工程量上与
   「装一个包再适配」相差不大，但依赖面完全可控。单独装一个包，正是
   「不引入重量级依赖」这条既有决定本来要防的口子。

4. **文件上传直接用 antd 的 `Upload`**（本次调研已提出并自行否决，本 ADR
   认可该结论）—— 重新把 antd 运行时带回来，与放弃方案 2 同理。

5. **把 SSE 渲染迁移到 lobehub-ui 风格的通用聊天流式处理** —— 背景 #8 已
   说明现有管道的语义（团队委派/决策/洞察的分层可见性、journal-as-truth
   归约）是通用单 Agent 聊天库不具备的；迁移不是「对齐」而是倒退，且会
   连带影响 ADR-0037/0038/0041 三篇已 Accepted/Proposed 的既定契约，
   改动面远超本 ADR 范围。

## 后果

### 正面

- 顺带拍板并关闭 `docs/proposals/0002-lobehub-parity-polish.md` §2.4
  （代码块语法高亮）这项已经待了一轮的 PR 债务。
- 新增数学公式渲染、回答正文内 Mermaid 图表两项目前完全没有的能力，且
  Mermaid 部分零新依赖（复用已装的 `mermaid`）。
- 新增依赖面窄且可枚举（`remark-math`/`rehype-katex`/`katex` 样式 + 语法
  高亮方案），不引入 antd、base-ui、任何 motion 库；`web/package.json`
  的「极简运行时依赖」传统（`docs/proposals/0001` §8 语）得以延续而非
  被打破。
- `GeneratedFileCard` 的字段形状提前对齐 A2A `artifact.parts[]`，后端
  一旦补上文件生成能力，前端契约不需要返工。
- 五层依赖边界（`dependency-cruiser`）、journal 事件语义、既有 ADR 契约
  全部不受影响，评审面被限制在「新增什么、不新增什么」，不波及已
  Accepted 的架构决定。

### 负面

- 团队拿不到「装一个包全部搞定」的捷径，需要真实工程投入把 KaTeX/
  Mermaid-in-answer/语法高亮接进现有管道，以及手写上传区与文件卡片
  组件——工作量高于「整体迁移」给人的第一印象。
- 放弃了跟随 LobeHub 上游持续迭代这些叶子渲染器 bug 修复/新特性的
  「免费红利」，相关维护成本转移到本项目自己承担。
- 生成文件卡片、上传组件在后端能力（背景 #10）补齐之前只是「渲染
  就绪」，无法端到端可用；如果产品侧误以为这是一个可以马上演示的完整
  功能，需要在这一点上提前对齐预期。

## 明确排除

- 不在本 ADR 内设计/实现后端文件生成工具、文件存储、上传接收端点——这是
  独立的、更大的能力缺口（背景 #10），需要单独的后端提案，可能涉及 A2A
  file part 的落地方案。
- 不逐像素复刻 LobeHub/LobeChat 的主页视觉皮肤——`docs/proposals/0001
  -frontend-productization.md` §4.1 已经明确选择差异化视觉语言，字面
  意义上的「皮肤搬运」与该决定冲突；本 ADR 只在「实现模式/能力对齐」层面
  参考 LobeHub，不在「品牌视觉」层面。
- 不在本 ADR 内评估 `@lobehub/ui` 之外的其他现成 Markdown/上传组件库
  （如通用拖拽库、`shiki` 以外的高亮方案选型）等具体选型细节，留给
  `docs/proposals/0003-markdown-files-charts-lobehub-reference.md`
  （本 ADR 的执行方案）。

## 相关

- **Extends:** ADR-0004（Protocol-First 可插拔设计）—— 本 ADR 是该原则
  在前端第三方 UI 依赖选型上的具体应用：能力可插拔，不代表要绑定某一个
  供应商的整套运行时。
- **Keeps:** ADR-0037（Journal-as-Truth）、ADR-0038（LLMAdapter 流式
  事件契约）、ADR-0040（协作模式契约生成）、ADR-0041（answer-delta 归属
  前端投影）—— 本 ADR 不改变这几篇已定的事件流与渲染归约语义。
- **呼应:** `docs/proposals/0001-frontend-productization.md` §4.1/§4.4/
  §5.3（拒绝完整组件库的既有先例）、`docs/proposals/0002-lobehub-parity
  -polish.md` §2.4（语法高亮待办）、§3（拒绝动效库的既有先例）。
- **落地:** `docs/proposals/0003-markdown-files-charts-lobehub-reference
  .md`（本 ADR 的执行方案与分阶段路线图）。
