# ADR-0102 followup: Tool args 顺序约束 —— 让 Inspector header chip 不与 Render body 重复

## 状态

**Accepted — 2026-09-01。** 实现见 `deploy/lobehub/patches/runtime/LcaRunDriver.ts` 的 `pickArgs` 重构（单文件 +41 / −19）。

承接 ADR-0102（Tool Render Contract）。本 followup 解决 ADR-0102 没明确的**最后一个边缘问题**：`LcaRunDriver` 在生成 tool message 的 `plugin.arguments` JSON 时，把 long-text 字段（`code` / `command` / `content` / `script` 等）排到了 JSON 顶层 keys 的第一项，导致前端 `ToolTitle` 的 header chip 把同一段 long-text **画了一遍**（在折叠头），紧接着 `ExecuteCodeRender` / `RunCommandRender` 在折叠 body 里又把同一段 long-text **画了第二遍**（在代码块 / terminal output）。

> **核心决策：LCA `LcaRunDriver.pickArgs` 把 long-text args key 推到 `JSON.stringify` 顺序的末尾。** 前端 `ToolTitle.tsx:91` 用 `Object.entries(args).slice(0, MAX_PARAMS)` 取第一项，决定 chip 显示哪个字段 —— 推到末尾后 chip 自然选中 short 字段（`description` / `path` / `language`）。body 渲染不依赖 key 顺序（key-based lookup），仍能正常取 `args.code` 渲染完整代码块。**绝对不动 LobeHub 原生前端组件**（`ToolTitle` / `ExecuteCodeRender` / `Inspectors` 等）。

---

## 1. 现象（2026-08-29 复盘，2026-09-01 dev run 实测）

dev DB 的话题 `tpc_a9K1KmwD8o5U`（"分析"）+ `tpc_EqCa2BcHq9XA`（"App 个人信息保护合规自查表内容咨询"，用户原始截图）跑 executeCode 调 openpyxl 时，前端 LobeHub ToolMessage 渲染出两类视觉噪声：

| # | 症状 | 根因 |
|---|---|---|
| 1 | 折叠卡头部 chip 显示 `code: import openpyxl\n\nwb = openpyxl.load_workbook('/mnt/data/2025年度工作计划表-李超_金融科技.xls...`（前 50 字符截断） | `LcaRunDriver.pickArgs` 把 `code` 排到 args 第一项；前端 `ToolTitle.tsx:91` 取 `Object.entries(args)[0]` 作为 chip 内容 |
| 2 | 折叠打开后 body 又渲染完整代码块（`<Highlighter>{args.code}</Highlighter>`，语法高亮） | LobeHub 原生 `ExecuteCodeRender` 用 `args.code` 渲染代码块，与 chip 是同一段 |
| 视觉叠加 | 同一段 `import openpyxl...` 在头部（截断）+ body（完整）画了**两遍**，看起来"折叠打开后多出一段代码" | 症状 1 + 2 同时发生 |

`traces/runs/run_c38532761cfb/journal.jsonl` 实测：

```json
{
  "descriptor": {"type": "ToolInvoked"},
  "data": {
    "tool_name": "executeCode",
    "arguments": {"code": "\nimport openpyxl\n\nwb = openpyxl.load_workbook(...)", "description": "...", "language": "python"},
    "output_text": "Sheet names: ['Sheet1']..."
  }
}
```

注意 `arguments` 的 key 顺序是 `code / description / language` —— `code` 排第一。LCA 后端这条没问题（参考 ADR-0101 §5.4），但前端 chip 选第一项就把 `code` 当 chip 内容。

## 2. 第一性原理

LobeHub 的 `ToolTitle.tsx` 设计是把 args 第一项当作"工具在做什么的简短摘要"显示在 header chip，目的是让用户在**还没展开**时就能看到工具当前在做什么。对于 long-text 字段（`code` / `command` / `script`）—— **这一项目的本身就跟 body 渲染重复**：

- chip = `code: import openpyxl...(50字符)` 是**截断**
- body = `<Highlighter>{args.code}</Highlighter>` 是**完整**
- 信息冗余，且视觉上"展开后多出一段"

LCA 这边**能控制的最小干预点**是 `LcaRunDriver.ts` 生成 args JSON 的顺序。前端那套 `Object.entries(args).slice(0, MAX_PARAMS)` 取第一项的逻辑是 LobeHub 原生实现，**不能动**。所以 LCA 必须保证：**args 第一项是 short-value 字段**。

### 2.1 关键约束

| 约束 | 来源 |
|---|---|
| 前端 chip = `Object.entries(args)[0]` | LobeHub `ToolTitle.tsx:91`（不动） |
| 前端 Render body = `args.code` / `args.command` | LobeHub `ExecuteCodeRender` / `RunCommandRender`（不动） |
| LCA args 来源 = `LcaRunDriver.pickArgs` 后 `JSON.stringify` | 我们的修改点 |
| JSON 顶层 keys 顺序 = `JSON.stringify` 对象属性插入顺序 | JavaScript 规范 |

**lcaRunDriver 这边通过控制 args dict 的 key 插入顺序**就能影响前端 chip 显示，**不动 LobeHub 原生前端**。

## 3. 一次性方案

### 3.1 ARG_KEYS 二段划分

```ts
const ARG_KEYS_SHORT: readonly string[] = [
  'path', 'description', 'language', 'skill_id', 'query',
  'directoryPath', 'directory_path', 'timeout', 'timeout_s',
  'background', 'run_in_background', 'createDirectories', 'create_directories',
  'file_path', 'pattern', 'glob', 'scope', 'replace_all',
];

const ARG_KEYS_LONG: readonly string[] = [
  'content', 'command', 'code', 'search', 'replace',
  'old_string', 'new_string', 'old_str', 'new_str',
];

const ARG_KEYS: ReadonlySet<string> = new Set([...ARG_KEYS_SHORT, ...ARG_KEYS_LONG]);
```

### 3.2 pickArgs 二段写入

```ts
function pickArgs(state: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!state) return {};
  const args: Record<string, unknown> = {};
  for (const key of ARG_KEYS_SHORT) {
    if (state[key] !== undefined) args[key] = state[key];
  }
  for (const key of ARG_KEYS_LONG) {
    if (state[key] !== undefined) args[key] = state[key];
  }
  return args;
}
```

`mergeInvocationArgs`（streaming 增量合并）通过 `{...prior, ...pickArgs(state)}` 自动保持 short→long 顺序：ToolStarted 第一次生成时奠定 short→long，后续 ToolCallStreaming 增量的新 key 也按 short→long 追加。

### 3.3 单元测试

`lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.test.ts` 加 6 个断言：

| 场景 | 期望 keys 顺序 |
|---|---|
| executeCode（code + description + language） | `[description, language, code]` |
| runCommand（command + description） | `[description, command]` |
| readFile（path + content） | `[path, content]` |
| 未知 key | 被丢弃（白名单不变） |
| empty / undefined | `{}` |
| undefined value | 该 key 被丢弃 |

`__test__` export 仅用于 vitest，runtime 不消费。

## 4. 行为差异

| 场景 | 改前 | 改后 |
|---|---|---|
| executeCode header chip | `code: import openpyxl...(50字符截断)` | `description: Read Excel file structure and content` |
| runCommand header chip | `command: cd /tmp && ls -la` (截断) | `description: Inspect git log` |
| readFile header chip | `content: <blob>` (截断) | `path: /mnt/data/x.xlsx` |
| ExecuteCodeRender body | 渲染 `args.code` 完整代码块 | **不变** |
| RunCommandRender body | 渲染 `args.command` 完整命令 | **不变** |

## 5. 与既有 ADR 的关系

| ADR | 关系 |
|---|---|
| ADR-0101 tool-facts-and-evidence-only | 不变。本 ADR 不改 journal 字段、不改 evidence 路径 |
| ADR-0102 tool-render-contract | **承接**。本 ADR 解决 ADR-0102 §3.3 "Frontend 单一投影" 没明确的 args key 顺序约束 |
| ADR-0073 runsession-sole-session-path | 不变 |
| ADR-0119 webserver-as-plugin | 不变 |
| deploy/lobehub/CUSTOMIZATIONS.md 铁律 "不要再给 StreamingHandler / ClientLLMTransport / GeneralChatAgent / Reasoning.tsx 打补丁" | **遵守**。本 ADR 不修改任何 LobeHub 原生前端组件 |

## 6. 不变量

| # | 规则 |
|---|---|
| 1 | ARG_KEYS 白名单本身不变（`ARG_KEYS = ARG_KEYS_SHORT ∪ ARG_KEYS_LONG` 元素之和等于原 ARG_KEYS 元素之和）—— 没有新增 key，没有删除 key |
| 2 | pickArgs 返回的 dict 元素数量不变 —— 同 state 输入下，keys 集合与原版完全一致，仅顺序不同 |
| 3 | JSON.stringify 结果可被前端 `JSON.parse` 完整还原 —— 对象属性顺序不影响 parse 语义 |
| 4 | `mergeInvocationArgs` 在 streaming 增量合并时保持 short→long 顺序 —— 由 JS spread 保留 prior 顺序 + 新 key 按 pickArgs 顺序追加的语义保证 |
| 5 | 前端 Render body 通过 key-based lookup（`args.code`）取值，不依赖顺序 —— 修复对 body 渲染零影响 |

## 7. 验收规约

```sh
# 单元（lobehub-ui 前端）
cd lobehub-ui && pnpm vitest run src/store/chat/agents/transports/LcaRunDriver.test.ts
# 期望 6 passed

# transports 全部测试
cd lobehub-ui && pnpm vitest run src/store/chat/agents/transports/
# 期望 52 passed / 10 files (含本 ADR 新加的 6 个)

# patch 引擎同步
uv run python -m deploy.lobehub.patch_lobehub verify
# 期望 19 ok, 0 broken/missing

# LCA 后端 baseline（确认未回归）
uv run pytest --no-cov tests/tools/ tests/test_run_live_ui_sse.py tests/test_tool_event_facts.py -q
# 期望 125 passed + 34 skipped + 77 subtests passed
```

## 8. 后续 Task

| Task | 内容 |
|---|---|
| **Task A** | 等 LobeHub 升级 Inspectors 把 chip 第一项改为按 type-aware 优先级（path > command > code）后，**这个 LCA 顺序约束可以退役**。届时本 ADR 标注 Superseded |
| **Task B** | LCA RenderContract (`lca/infrastructure/tools/contract/`) 给每个 tool 加 `chip_priority: tuple[str, ...]` 字段（按 tool 自定义），pickArgs 直接消费这个 priority。当前是按全局 short/long 划分，已足够；待 RenderContract schema 升级时合并 |

## 9. 元数据

- 作者：LCA 架构
- 日期：2026-09-01
- 状态：**Accepted**
- 关联 ADR：0101 / 0102
- 关联 patch：`deploy/lobehub/patches/runtime/LcaRunDriver.ts`
- 关联 patch source：`deploy/lobehub/patches/runtime/lca_run_driver.py`（whole-file copy，同步到 `lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts`）
- 关联测试：`lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.test.ts`（gitignored，作为 dev infrastructure）
- 关联 spec：`docs/specs/run-live.md` §4 "Tool message wire"（待补 chip 顺序约束）
