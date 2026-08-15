# 第一性原理架构分析：run_ce9d5cfff1c9 零交付问题

> 生成时间: 2026-08-15
> 分析对象: traces/runs/run_ce9d5cfff1c9.jsonl (571 事件)
> 用户意图: "生成pdf版本" (上传 .md 文件)
> 结果: 8 步执行完毕, status=completed, output_text="", PDF 未生成

---

## 一、全链路数据流追踪

```
用户上传文件 (.md)
  │
  ▼
① LobeHub → gateway/openai_shim.py (OpenAI compat layer)
  │  messages[] 携带 <file> 标签，含文件内容
  │
  ▼
② ingress.py → prepare_run_from_messages()
  │  ├─ parse_messages() → 提取 user_text + file_refs
  │  ├─ ingest_file_refs() → 文件存入 FileStore
  │  └─ compose_run_question() → FileStoreAttachmentIdentity.compose_question()
  │        ─ FilesInfoDocument.render() → html.escape(content) → <files_info>
  │
  ▼
③ execute.py → create_run_session() → schedule_run()
  │  question = "生成pdf版本\n\n<!-- SYSTEM CONTEXT -->...<files_info>...<file>...{html escaped content}...</file>..."
  │
  ▼
④ runtime_loop.py → CognitiveRuntime._loop()
  │  for step in range(max_steps):
  │    think() → Reasoner.generate_thoughts() → execute_llm_turn()
  │    act() → body.act(decision) → 工具执行
  │    reflect() → brain.reflect()
  │    StopRule.decide() → 是否终止
  │
  ▼
⑤ 8 步后的结果
  ├─ Step 1: writeFile → generate_pdf.py (含中文引号 → Python SyntaxError)
  ├─ Step 2: runCommand ×2 → mkdir + pip install reportlab
  ├─ Step 3: readFile → 读取 markdown 源文件
  ├─ Step 4: writeFile (137.8s LLM) → 尝试修复: "Chinese quotation marks..."
  ├─ Step 5: runCommand → 执行脚本 (大概率 SyntaxError)
  ├─ Step 6: readFile → 读取结果
  ├─ Step 7: runCommand (119.1s LLM) → 再次尝试: "Chinese curly quotation marks..."
  ─ AgentRunFinished: status=completed, output_text=""
```

---

## 二、五个断裂点的根因分析

### 断裂点 1：内容注入层 —— Unicode 字符未归一化

**文件**: `lca/layer0_infra/attachment/files_info.py` 第 43 行

```python
def to_xml(self) -> str:
    # ...
    if self.content:
        return f"<file {attrs}>{html.escape(self.content)}</file>"
```

**问题**: `html.escape()` 只处理 5 个 XML 特殊字符 (`< > & ' "`)。
中文引号 `"\u201c"` / `"\u201d"` 等 Unicode 字符**直接透传**。

**链路效应**:
- markdown 文件中的 `""` → 注入 prompt → LLM 生成 Python 脚本时直接复制这些字符
- Python 不识别 `"\u201c...\u201d"` 作为字符串定界符 → `SyntaxError`
- Agent 进入 "写脚本 → 语法错误 → 再写 → 仍错误" 循环

**第一性原理**: 内容注入是**用户不可见内容**（system context），系统有责任保证其**编码安全**。
当前 `html.escape` 是 XML 注入防护，不是内容安全归一化。
这两者目的不同，不应混为一谈。

**正确做法**: 注入层应做 **text normalization**，将 Unicode 引号、破折号等
映射为 ASCII 等价物（或者保留原文但在注入时附加编码提示）。

---

### 断裂点 2：多工具循环检测缺失

**文件**: `lca/layer1_cognitive/brain/decision_gates/tool_loop_breaker.py`

```python
@staticmethod
def _consecutive_failures(state: AgentState, tool_name: str) -> int:
    # 只检查连续相同工具名的失败
```

**问题**: 本例的循环模式是 **跨工具协作循环**:
```
writeFile → runCommand → (失败) → readFile → writeFile → runCommand → (失败) → ...
```

`ToolLoopBreakerGate` 只检测**同一工具**连续失败。
当 Agent 交替使用多个工具时（这是正常的多步工作流），**循环检测失效**。

**第一性原理**: 循环检测应关注**任务进展**，而非工具名称重复。
如果连续 N 步都没有产生有价值的输出（final_output 为空），就应该触发干预。

**正确做法**: 引入 **progress-based loop detection**:
- 如果最近 N 步的 `observation.success` 全部为 False 或 None
- 且 `state.final_output` 仍为空
- 强制 Agent 换策略或直接 respond 收口

---

### 断裂点 3：零输出 = 完成的默认假设

**文件**: `lca/layer2_runtime/runtime_loop.py` 第 206-213 行

```python
@staticmethod
def _apply_artifact_closure(state: AgentState) -> None:
    closure = synthesize_artifact_closure()
    if not closure:
        return  # ← 无产物时直接跳过
    # ...
    if state.status == TaskStatus.WORKING:
        state.status = TaskStatus.COMPLETED  # ← 无产物也标记完成
```

以及 `contracts/models/core/result.py` 第 80 行:

```python
status = TaskStatus.COMPLETED if state.status == TaskStatus.WORKING else state.status
```

**问题**: 当 `output_text=""` 且 `error=""` 且 `status=completed` 时，
系统认为这是**正常完成**。但实际上 Agent **什么都没交付**。

**第一性原理**: `completed` 语义应为"任务已完成且有产出"，不是"循环已结束"。
零输出的 completed 是**隐性失败**，应该标记为 `failed` 或 `no_output`。

**正确做法**: 
- 在 `Result.from_state()` 中，如果 `output=""` 且 `error=""` 且 `status=COMPLETED`，
  应视为 `FAILED` 或 `INCOMPLETE`，并生成诊断信息。

---

### 断裂点 4：Doctor 只检查管道，不检查业务

**文件**: `gateway/runs/doctor.py`

Doctor 检查的 H1-H5:
- H1: run 是否被接受 → ✅
- H2: journal 是否有事件 → ✅ (571 事件)
- H3: live tail 是否正常关闭 → ✅
- H4/H5: 浏览器/前端可见性 → N/A

**问题**: Doctor 验证的是**数据管道完整性**，不是**业务结果正确性**。
一个零交付的 run 可以拿到 "ok" 的诊断结果。

**第一性原理**: 健康检查应同时验证**结构完整性**和**业务有效性**。
当前 Doctor 只做前者。

**正确做法**: 
- H2 检查增加: `AgentRunFinished.output_text` 非空验证
- 新增 H6: 业务产出验证 — 如果有附件/文件上传，是否有对应的下载产出？

---

### 断裂点 5：Machine 模式无原生代码执行

**文件**: `lca/layer0_infra/computer/machine.py`

Machine 模式只有: `writeFile`, `readFile`, `runCommand`, `listFiles`...
**没有 `executeCode`** (sandbox 模式有)。

**问题**: 当 Agent 需要执行 Python 脚本时:
- Sandbox 模式: `executeCode(language="python", code=...)` → 一步完成
- Machine 模式: `writeFile(path="script.py")` + `runCommand(command="python3 script.py")` → 两步，且脚本中的编码问题会暴露

**第一性原理**: Machine 模式缺少代码执行能力是**架构缺口**，不是 bug。
当 Agent 的工作流涉及"生成代码 → 执行"时，两步分离增加了失败面。

**正确做法**: 
- 为 Machine 模式添加 `executeCode` API（通过 transport 转发到设备执行）
- 或者在 `writeFile` 后自动提供执行建议

---

## 三、架构重构方案

### 3.1 内容注入层: TextNormalizationService

```
位置: lca/layer0_infra/attachment/normalizer.py (新增)
职责: 注入前归一化文本内容

规则:
1. Unicode 引号映射: \u201c\u201d → ""  \u2018\u2019 → ''
2. Unicode 破折号: \u2014 → --  \u2013 → -
3. Unicode 省略号: \u2026 → ...
4. 零宽字符去除: \u200b\u200c\u200d\uFEFF → ""
5. 保留原始内容在 FileStore 中，归一化只用于 prompt 注入

设计原则:
- 归一化是纯函数，不影响原始文件存储
- 可配置: 哪些映射开启/关闭
- 可测试: 输入/输出对比表
```

### 3.2 循环检测: ProgressBasedLoopDetector

```
位置: lca/layer1_cognitive/brain/decision_gates/progress_loop_detector.py (新增)

规则:
1. 连续 N 步无有效产出 (observation.success=False or None)
   → 注入 progress_warning 到 working_memory
2. 连续 M 步后仍无产出 (M > N)
   → 强制 Agent respond，附带已尝试的工具和错误信息
3. 多工具循环检测: 最近 K 步的工具组合模式重复
   → 检测跨工具循环 (writeFile→runCommand→...→writeFile→runCommand)

与现有 ToolLoopBreakerGate 的关系:
- ToolLoopBreakerGate: 单工具连续失败 → 阻断该工具
- ProgressLoopDetector: 多工具协作无进展 → 强制换策略
- 两者互补，同时注册到 ChainedDecisionGate
```

### 3.3 结果验证: OutputValidationGate

```
位置: lca/layer2_runtime/completion/output_validation.py (新增)

规则:
1. status=COMPLETED 但 output_text="" → 降级为 FAILED
   错误信息: "Agent 运行结束但未产生任何输出。可能原因: 工具循环失败、
   代码执行错误、模型未响应。"
2. status=COMPLETED 但无附件产出（当有输入附件时）→ 记录 warning
3. budget 耗尽但无产出 → FAILED (现有逻辑已有，加强)

集成点:
- DefaultStopOutcomePolicy.resolve() 增加 output 验证
- Result.from_state() 增加 output 非空检查
```

### 3.4 Doctor 增强: BusinessOutcomeCheck

```
位置: gateway/runs/doctor.py (增强)

新增 H6 (business_outcome):
- 检查 AgentRunFinished.output_text 是否非空
- 检查是否有附件产出（如果有输入附件）
- 检查是否所有 StepCompleted 都有 status != "working"

新增 H7 (tool_effectiveness):
- 工具调用成功率 (success / total)
- 最长连续失败数
- 是否存在跨工具循环模式
```

### 3.5 Machine 代码执行: executeCode via Transport

```
位置: lca/layer0_infra/computer/machine.py (增强)

新增 API:
async def execute_code(self, *, code: str, language: str = "python") -> ComputerOpResult:
    """通过 transport 在设备上执行代码。
    
    实现:
    1. 生成临时文件路径: .lca/exec_<run_id>_<nonce>.py
    2. 写入代码内容
    3. 执行 python3 临时文件
    4. 捕获 stdout/stderr/exit_code
    5. 清理临时文件
    6. 返回 ComputerOpResult
    
    优势:
    - 与 writeFile + runCommand 相比，减少一步
    - 脚本内容在 transport 层统一编码处理
    - 错误信息结构化返回
    """
```

---

## 四、优先级排序

| 优先级 | 改进项 | 消除的问题 | 实施复杂度 |
|---|---|---|---|
| P0 | OutputValidationGate | 零输出=完成的虚假状态 | 低 |
| P1 | TextNormalizationService | Unicode 字符导致的语法错误 | 低 |
| P2 | ProgressBasedLoopDetector | 多工具循环检测缺失 | 中 |
| P3 | Doctor 增强 H6/H7 | 业务结果不可见 | 中 |
| P4 | Machine executeCode | 代码执行能力缺口 | 高 |

---

## 五、验证指标

修复后，同类场景应满足:

1. **零输出不再标记为 completed**: `output_text=""` → `status=failed`
2. **中文引号不再导致语法错误**: markdown → prompt → Python 脚本 → 执行成功
3. **多工具循环在 5 步内被检测并中断**: 而非等 8 步预算耗尽
4. **Doctor 报告能区分"管道 ok 但业务失败"**: H6 检查 output_text
5. **Machine 模式可直接执行代码**: 不需要 writeFile + runCommand 两步

---

## 六、与 LobeHub 原生架构的对齐

LobeHub 原生 `GeneralChatAgent` 的处理方式:

1. **内容注入**: LobeHub 将文件内容作为 `user` role 的 content 发送，不做 XML 包装。
   LCA 的 `<files_info>` 是额外的结构层，需要额外的编码处理。

2. **工具调用**: LobeHub 的 tool call 结果直接进入 `role=tool` 的历史，
   模型看到执行结果后自然决定是否继续。LCA 的 ToolLoopBreakerGate
   是额外的安全网，但只覆盖单工具场景。

3. **终止判定**: LobeHub 使用 `forceFinish` 机制 — 当模型连续生成空响应时
   强制终止。LCA 的 DefaultStopOutcomePolicy 已有类似逻辑（_FALSE_COMPLETION_WINDOW），
   但只在 RESPOND 动作时检查，不检查 USE_TOOL 动作的无效产出。

对齐建议:
- 将 `_FALSE_COMPLETION_WINDOW` 逻辑扩展到 USE_TOOL 动作（无进展检测）
- 内容注入层增加与 LobeHub 对齐的 Unicode 处理（LobeHub 前端有 text normalization）
- Doctor 增加与 LobeHub `run_doctor` 对齐的业务产出检查
