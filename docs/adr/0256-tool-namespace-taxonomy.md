# ADR-0256 — 工具命名空间划分规范：决策粒度 × 加载粒度 × 审批粒度三合一

## 状态

**Proposed — 2026-10-01**

> **一句话**：终结"单工具 namespace"的退化现状——namespace 归属改为工具 factory 的声明式元数据，按 8 域划分（core/file/shell/memory/skill/web/agent/ext），让模型决策粒度、defer 加载粒度、审批边界三者同粒度，并给出可直接落地的 6 处代码改动 + 验收标准。

**Extends**：
- [ADR-0255](0255-muse-production-runtime-full-reference.md)（Muse 生产运行时全量参考）：本 ADR 是 0255 §L1 defer 落地的**划分规范**——0255 记录了"defer 按 namespace 延迟加载"这一机制，本 ADR 回答"namespace 具体怎么切、切几块、每块装什么"；
- 承接 0255 §3 的 36 工具命名空间函数清单：切分原则（§2）直接来自对该清单的归纳。

**实证来源**：2026-10-01 三个 run 的 traces 复盘——`run_56ee6564e3ea`（单工具 namespace 下模型把同一 find 发射 21 次）、`run_28aa7eb3261b` / `run_ab78aeb6eabf`（defer 协议跑通：`tool_search(namespace='listFiles')` → `listFiles`），以及 `lca/infrastructure/tool_defer/session.py` 的 `update_turn` 实现审计。

---

## 0. 接任务前 7 问

1. **问题是什么？** `ToolDeferSession.update_turn` 中 `namespaces.get(tool.name, tool.name)` 让未登记的工具自动退化成"以自己名字命名的单工具 namespace"（如 `listFiles`、`writeFile` 各自成域）。目录行退化成 `"1 tools: listFiles"`，对模型零信息量；`tool_search` 一次往返只换回一个 schema，defer 的批量加载优势被吃掉一半。
2. **受影响的事实或契约是什么？** `ToolNamespace` 的划分契约、`DeferPolicy` 的 eager/目录描述配置、`ToolsService.tool_namespaces` 中央映射表、`tool_search` 的加载协议、wire gate 的可见性判定、`shell` 类高危工具的审批边界。
3. **唯一真值在哪里？** 工具的真实家底：`lca/infrastructure/tools/`、`lca/infrastructure/tool/` 下 20+ 个工具（§3 表格为 2026-10-01 快照）；namespace 划分的真值：本 ADR §3（factory 声明为准，代码即文档）。
4. **改变哪个边界？**
   - 契约层：`Tool` 新增 `namespace: str` 声明字段；`DeferPolicy` 新增 `namespace_approval`；
   - 注册层：删除 `ToolsService.tool_namespaces` 中央映射表，SSOT 下移到各 factory；
   - 运行时层：`update_turn` 分组键改为 `tool.namespace`，漏声明直接抛错（fail-fast）。
5. **现有 Protocol / ADR 能否表达？** 不能。ADR-0255 只记录了 defer 机制本身，未规定 namespace 的划分标准；`DeferMode` 只有 EAGER/DEFERRED 两档，没有"按什么切"的规范。
6. **失败、重试、恢复和幂等语义是什么？**
   - 注册期：`tool.namespace` 为空 → 启动即抛错，不许静默上线（fail-fast）；
   - 运行期：模型调用未加载域的工具 → wire gate 拒掉并提示先 `tool_search`（fail-closed，错误抛回模型重试，不杀 run）；
   - `load_namespace` 保持幂等（已实现，保留）。
7. **如何验证？** §9 的 8 条验收用例，含一次真实 run 的 traces 断言。

---

## 1. 诊断：病灶在 `update_turn` 的 fallback

```python
# lca/infrastructure/tool_defer/session.py — 改前
grouped.setdefault(namespaces.get(tool.name, tool.name), []).append(tool.name)
#                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# 映射表漏登记 → 工具名自己变成 namespace 名 → 单工具 namespace
```

连锁反应：
- `_describe` 的默认实现 `"1 tools: listFiles"`——模型看到目录行，无法推断该域还有什么；
- 模型被迫在没看到 schema 之前就精确到具体工具名（`tool_search(namespace='listFiles')`），决策前置；
- 更深层：namespace 归属是**中央映射表**，与 factory 分离——加工具要改两处，漏了就静默退化。

## 2. 设计总则

1. **namespace 是工具的声明式元数据**，写在 factory 注册处，与工具同生死。中央映射表删除。
2. **一个 namespace = 一次模型决策 = 一次 defer 加载 = 一个审批边界**，三者同粒度。凡是"按域挂审批""按域做可见性判定"的需求，都自然落到 namespace 上。
3. **漏声明的工具不许悄悄上线**——注册期 fail-fast，不做运行期 fallback。
4. **写不出一句话目录描述的 namespace 不配存在**——`namespace_descriptions` 必填化是天然的粒度校验器。

## 3. Namespace 划分总表（2026-10-01 工具快照）

| namespace | mode | 目录一句话（给模型看） | 工具 |
|---|---|---|---|
| `core` | EAGER | 推理原语：按需加载工具目录 | `tool_search` `listEnvironments` `cordisControl` `profile_apply` `profile_diff` |
| `file` | DEFERRED | 文件系统：列出、读取、写入、编辑、移动、搜索文件内容 | `listFiles` `readFile` `writeFile` `editFile` `moveFiles` `globFiles` `searchFiles` `grepContent` `exportFile` `fileWrite` |
| `shell` | DEFERRED | 执行 shell 命令与脚本；危险操作会先请示你 | `runCommand` `execScript` `executeCode` `getCommandOutput` `killCommand` `bashRun` |
| `memory` | DEFERRED | 搜索与写入长期记忆 | `memory_search` `memory_add` `memory_get` |
| `skill` | DEFERRED | 技能的发现、安装与调用 | `search_skill` `activate_skill` `import_skill` `read_skill_reference_once` `run_skill_script` `readReference` |
| `web` | DEFERRED | 联网搜索与网页抓取 | `search` |
| `agent` | DEFERRED | 助理管理、派发子任务、向用户提问 | `delegate_tool` `askUserQuestion` `send_message` `request_box_help` `create_assistant` `list_role_cards` `create_assistant_skill` `list_assistant_skills` `delete_assistant_skill` `edit_assistant_skill` `update_assistant_soul` `update_assistant_profile` `update_assistant_grants` `update_assistant_user` `list_assistant_tools` `create_assistant_tool` `update_assistant_tool` `delete_assistant_tool` |
| `ext` | DEFERRED | 第三方集成：连接与刷新外部服务 | `composioConnect` `composioRefresh` 各 `mcp__<server>__<tool>` |

取舍说明：
- `core` 放 loader 与平面无关的 LCA 内置原语：`tool_search`（loader 必须在 wire 上，session.py 已有注释：目录指向不存在的 loader 是死锁）、`listEnvironments`（默认工具集无条件注入、schema 极小，保持 eager 不改变既有可见性）、`cordisControl` / `profile_apply` / `profile_diff`（Creator 控制面与 profile 管理，仅 creator 模式出现）。其余工具按域 defer。
- `agent` 域在 ADR-0255 清单基础上补入 assistant 自管理工具族（ADR-0242 D6）：`create_assistant` / `list_role_cards` / `create_assistant_skill` / `list_assistant_skills` 等。它们不是每 turn 都用，归入 DEFERRED，模型经 `tool_search(namespace='agent')` 按需加载。
- `ext` 域除 `composioConnect` / `composioRefresh` 外，所有 MCP 工具（`mcp__<server>__<tool>`）归入 `ext`：它们是第三方服务适配，与 `composio` 同语义。
- `memory` 保持 DEFERRED：2026-10-01 run 实证模型已学会 `tool_search(namespace='memory')`，协议可 cover，不必破例。
- `shell` 独立成域且目录行自带"危险"字样——描述即行为约束。
- `skill` 域的 snake/camel "双拼"（`activate_skill`/`activateSkill` 等）是**故意设计的双层命名**，不是 slop，不做 canonicalize：内部名（模型可见）用 snake_case，`api_name`/`ToolApi(name=...)`（前端契约：LobeHub/computer companion/wechat 展示）用 camelCase，两者在 `RenderContract` 里显式配对声明。wire gate 的 `_name_forms` 容错保留（前端 camelCase 名字在 wire 上还活着）。【2026-10-01 修正：此前版本误判为 slop 并要求收敛，已纠正；验收用例 A4 同步修正为只扫描内部注册名】另注：`runCommand`/`listFiles` 等工具内部名本身就是 camelCase（computer companion 的 dispatch 依赖），说明内部命名约定 snake+camel 并存——这是值得未来统一的一致性问题，但超出本 ADR 范围。

## 4. 契约层改动

- `Tool` 新增 `namespace: str`（必填）：factory 注册时声明；
- `ToolNamespace` 不动（已是 pure data，符合"契约层无行为"）；
- `DeferPolicy` 新增：
  - `namespace_descriptions: dict[str, str]` 改为**必填**（删 `_describe` 的 `"N tools: …"` 默认实现）；
  - `namespace_approval: dict[str, ApprovalLevel]`（§7）。

## 5. 注册侧改动

```python
# 各 factory 声明归属，示例
ToolFactory(name="writeFile", namespace="file", ...)
```

删除 `ToolsService.tool_namespaces`。SSOT 从中央表下移到 factory——加工具只改一处，漏声明在启动期暴露。

## 6. Defer 协议改动（`session.py`）

```python
# update_turn 改后：分组键用声明，空值直接抛错
for tool in tools:
    if not tool.namespace:
        raise ValueError(f"tool {tool.name} declares no namespace")
    grouped.setdefault(tool.namespace, []).append(tool.name)
```

- `tool_search` 支持批量加载：`namespaces: list[str]`（`load_namespace` 已幂等，批量即循环调用；模型"查文件顺便搜记忆"时省一次往返）。
- 目录渲染格式（跟 prompt 语言走，中文版）：

```
可用工具目录（需要时用 tool_search 加载整个域）：
- file：文件系统：列出、读取、写入、编辑、移动、搜索文件内容
- shell：执行 shell 命令与脚本；危险操作会先请示你
- memory：搜索与写入长期记忆
- skill：技能的发现、安装与调用
- web：联网搜索与网页抓取
- agent：派发子任务、向用户提问
- ext：第三方集成：连接外部服务
```

## 7. Wire gate 升级：按 namespace 判可见性

在研的 `unexposed_tool_block_observation`（按工具名判）升级为按域判：

```python
# 伪代码
if tool.namespace not in session.loaded_namespaces and tool.namespace not in eager_namespaces:
    return block_observation(f"先用 tool_search 加载 '{tool.namespace}' 域，再调用 {tool.name}")
```

新工具进入已加载/已声明的域自动被 cover，无需逐个列名。

## 8. 审批模型：挂在 namespace 级

| namespace | 审批策略 |
|---|---|
| `shell` | `REQUIRE_APPROVAL`（`runCommand` 可执行任意 shell；2026-10-01 `run_56ee6564e3ea` 的截断命令执行事件是直接动因） |
| `file` | `AUTO`；`writeFile`/`deleteFile` 预留 `APPROVAL_ON_OVERWRITE` 钩子（本期不实现） |
| 其余 | `AUTO` |

新工具进入 `shell` 自动继承审批——这就是"审批边界与 namespace 同粒度"的价值。

## 9. 落地 checklist（按序）

1. contracts：`Tool.namespace`、`DeferPolicy.namespace_descriptions` 必填化 + `namespace_approval`；
2. 全部 factory 声明 namespace；删 `ToolsService.tool_namespaces`；
3. `update_turn` 改分组键 + fail-fast；`_describe` 删默认实现；
4. 写入 §3 的 8 句目录描述；
5. `tool_search` 加批量参数；
6. wire gate 改按 namespace 判可见性（与在研的 `_TRUNCATED_VALUE` / `arguments.py` fail-closed 改动合批提交）；
7. `shell` 接审批；
8. 全量测试 + 一次真实 run 的 traces 复盘（§10）。

## 10. 验收标准

1. 目录行恰好 8 行，每行一句话可读，无 `"N tools:"`  fallback 文本；
2. `tool_search(namespace='file')` 一次返回 9 个工具的完整 schema；
3. 注册期漏写 namespace 的工具启动即抛错；
4. 模型调用未加载域的工具被 wire gate 拒掉，错误信息含正确的 `tool_search` 指引，且 run 不死（错误抛回模型重试）；
5. `shell` 域的 `runCommand` 触发用户审批；
6. 批量 `tool_search(namespaces=['file','memory'])` 一次往返返回两域 schema；
7. 验收用例 A4 只扫描 Tool 内部注册名（排除 `api_name`/`ToolApi` 前端契约名），无 snake/camel 重复注册则通过；
8. 真实 run 复盘：首 turn 目录 8 行、模型经 `tool_search` 取数、无单工具 namespace、tool 健康全绿。

---

*实证附录：`traces/runs/run_56ee6564e3ea`（退化现状）、`traces/runs/run_28aa7eb3261b` / `run_ab78aeb6eabf`（defer 协议跑通）。凡与 §3 表格冲突的工具归属，以 factory 声明为准。*
