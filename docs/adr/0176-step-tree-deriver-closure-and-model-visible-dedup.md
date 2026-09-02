# ADR-0176: StepTreeAccumulator 闭环 + Model-Visible 去重重构 + Prompt Section 真值化

- Status: Accepted
- Date: 2026-09-03
- Supersedes: none
- Depends on:
  - ADR-0167 D1 / D11 (SSOT + 五面矩阵 I-PLUG1–6)
  - ADR-0167.1 D2 / D3 (deriver per-run 装配、StepTreeAccumulator 唯一写 journal.json)
  - ADR-0169 D8–D10 (LoopCursor 观测装配)
  - ADR-0175 D1 / D2 / D6 (`PromptTrace` + 真 brain prompt 落盘 + spine EP payload)
  - AGENTS.md §1 工程思维 (第一性原理、契约改动闭环、离开前卫生)
- Scope:
  - `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py`
  - `lca/infrastructure/observability/loop_cursor/{reasoner_prompt_capture,model_visible_capture}.py`
  - `lca/contracts/observability/{writable_matrix,writable_matrix_facade}.py`
  - `lca/runtime/journal_setup.py` + 三个 transport binding 点
  - `lca/infrastructure/observability/writable_matrix/{coordinator,registry,defaults}.py`
  - `lca/plugins/transport/webserver/handlers/runs/doctor/{doctor,step_check}.py`
  - tests: deriver / journal / doctor / model-visible / prompt capture
- 在 PR 描述里写一句结论:**让 `events.jsonl` 真成为 SSOT,让 `journal.json` 由 deriver 一条路径写,让 model_visible 收口到一个 writer,让 prompt section 真值化。**

## 0. 背景与现状痛点(用最新一次 run `run_4ad3407f56fb` 物理事实)

最近的 completed / backend / solo 三步 ReAct run(`traces/runs/run_4ad3407f56fb`)暴露四个**结构性问题**——同一份**第一性原理**的不同面:**

| # | 物理事实 | 根因 |
|---|---|---|
| **P1 journal 空** | `journal.json`(580 B)中 `steps: []` `phases: []`;doctor H2/H6 误报 `0 steps 0 tools`;sister-run `run_046515e96ac7` 同样结构 | `StepTreeAccumulatorDeriver._apply` 只认 `writable.step.start/end` 与四类 phase fold,但 backend ReAct 路径**根本不产生 `writable.step.*`**,只有 `phase.*.fold` + `step.tool_call.record` + `llm.call.end`;并且 `phase.think.fold` / `phase.act.fold` 只在 PHASE_FOLD_EPS 表里登记、`_apply` 没有对应分支。Adr-0167.1 D2 重写后,**依然没人补这一段**。 |
| **P2 prompt section 数字无内容** | `model_visible/step-001/system_prompt_sections.json` 13 个 section 各 `text_chars=0`,只看到数字 | `_write_model_visible` 直接调 `SectionTrace.text_chars` 序列化,而脑回路送来的是 `SectionTrace`(`name / kind / optional / used_fallback / skipped_empty / text_chars`,**没有 `text` 字段**);Assembler 端 `PromptTrace.section_traces` 只携带 `text_chars`,**全文落在 `system_prompt_text` 里**,section 级正文从来没被保留,replay 也无法重建 section 内容 |
| **P3 prompt 重复落盘** | 同 step 下同时存在 `system.json` + `system_prompt.json` + `system_prompt_sections.json` + `messages.json` | 两套 writer 并存:`StdModelVisibleCapture`(model_visible_capture.py)+ `_write_model_visible` 内的 legacy 兜底再写一遍,且 `_write_model_visible` 还要写 `system-prompt.legacy.md` 占位 |
| **P4 deriver 与 SSOT 脱钩** | deriver 把事件"顺便"再做一次 model_visible 写盘 | 违反 ADR-0167 D11 **I-PLUG5:不影响 SSOT** 与 D13 **B7:一 plugin 一目录** —— deriver 把副作用(写盘)与投影职责耦合 |

## 1. 第一性原理(根本机制,不是补丁)

**机制是什么**:Agent 只表达**意图**,SPINE 上报的"events"才是真值,deriver 是把真值**投影**到物化视图的纯消费者,不产生副作用(view-only)。`model_visible/step_NN/` 是 ReplayCursor 的**输入缓存**,只能由一个 writer 在 LLM 调用那一刻写一次,然后 immutable。

**最干净的形态**:
- **SSOT** = `events.jsonl`(RoutingFileSink,无第二条落盘面)。
- **唯一 service 化写** = `StepCoordinator` + `ModelVisibleRecorder`(五面矩阵里两节,各自 Protocol + 默认实现 + registry 解引用)。
- **唯一 journal 写** = `StepTreeAccumulatorDeriver.flush()`;**它不写 model_visible**,**它不写 events.jsonl**,**它不绑 ContextVar**。
- **Model-visible** 由 `ModelVisibleRecorder` 一次性写一份;**谁也没资格第二份写**;写完 immutable。
- **Prompt 真值** = `PromptTrace` + `SectionTrace`(扩字段加 `text`),落 `system_prompt.json`;**section 内容由 PromptAssembler 生成时透传**,而不是事后手动拼。

**判别准则(回到 I-PLUG1 / I-PLUG3 / D13 B7)**:
1. Agent / Brain / Body **不直接** import `EventSpine` / `_write_model_visible` / `FileSink`;
2. `deriver` **不调用**任何 `Path.write_text`;
3. `ModelVisibleRecorder` **只** 由 `ModelVisibleLLMAdapter` 触发,不在 deriver 中再写;
4. `StepCoordinator` 唯一写路径:同条 EP 同时让 5 个 face 收到(`emitter → driver → coalescer → serializer → storage`);
5. `journal.json` 落盘的 `flush()` 若没累积到 step → **fail-loud + H-xref** (而不是写空 document 当没事)。

## 2. 决策

### D1. 一条事实链(覆盖 P1)
**`StepTreeAccumulatorDeriver._apply` 必须能从 backend ReAct 路径累积 step/segment/phase**——而不只是依赖 `writable.step.*`。三段修复同 PR:

1. **扩 PHASE_FOLD_EPS(EP → kind 映射)**:把 `phase.think.fold`、`phase.act.fold` 与 `phase.act.fold.start/end` 全部在 `_apply` 里走对应分支(`_record_phase`),"PHASE_FOLD_EPS 表里有 ≠ _apply 处理了"是已暴露缺陷。
2. **加 fallback step 边界**(满足 I-PLUG5 且不改 vocabulary):
   - **进入** `brain.think.start` 时若没有 open_step → 隐式 `_begin_step(phase="think")`;
   - **离开** `brain.think.end` 时若有 open_step → `_close_step(outcome)`;
   - 同样包络对 `critic.eval.start/end`(主营 `record_phase("reflect")`,对 `open_step=act` 时闭合);
   - **包络优先级**:`writable.step.start/end` 永远大于 fallback(显式 > 隐式);
   - 加 `record_phase(...)` 累计到 `_open_step` 的 `segments` 当 `kind in {"think","act"}`。
3. **`llm.call.end` 与 `step.tool_call.record / body.tool.execute.start/end` 在有 `open_step` 时绑定 thinking/tool_call/tool_result**(当前条件命中 "无 open_step 直接跳过")——逻辑已经写,只是前置 open_step 起不来。

`flush()` 时:
- 若 `_open_step is None` **且** `_phases` 也空 → `structlog.error("step_tree_deriver.flush.empty", run_id=...)`,manifest 写 `extra.flush_errors += [{operation: "step_tree.flush.empty", error_message: "no step and no phase captured"}]`,doctor 走 `H-xref` broken。
- `_resolve_outcome()` 三路优先级保持(terminal 事件 > 已 closed+有 phases > 兜底),见 ADR-0167.1 D2。

> 不要新增 `writable.step.*` 发射器,因为它会反向影响 vocabulary 闭集(C1)。

### D2. Model-Visible 单一writer,deriver 完全不落盘(覆盖 P3, P4)
- **`StepTreeAccumulatorDeriver` 删除整段 `_write_model_visible`(含 5 件套 + `system-prompt.legacy.md` 兜底 + `messages.json` 占位)。**
- `ModelVisibleRecorder` 升级成**五面矩阵的 `model_visible_recorder` 面**(ADR-0167 D11.1 已列,本 ADR 落实 registry + 默认实现 `FilesystemRecorder` + 兜底 `NullRecorder`)。
- transport 在 `RunSessionBuilder.build` 阶段 `run_hub` 组装时**调用一次** `registry.register("model_visible_recorder", FilesystemRecorder(run_dir, ...))`;**writable_matrix.defaults.SpineEmitter 不再携带 file path**。
- `StepTreeAccumulatorDeriver` 不再订阅 model_visible 路径,只读 `step_id` 做 phase 累计。

### D3. Prompt Section 真值化(覆盖 P2)
1. `contracts/models/cognition/prompt_assembly.py` 的 `SectionTrace` 增加 **`text: str`** 字段(默认 `""`,frozen slots);`PromptTrace` 已有 `system_prompt_text`,不动。
2. `cognition/brain/sections/assembler.py::render_template` 在生成 `SectionTrace` 时**实际写入该 section 渲染后的正文**(`SectionOutput.text` → `SectionTrace.text`),`text_chars` 同步 = `len(text)`。
3. `contracts/observability/reasoner_prompt_capture.py` 的 `ReasonerPromptArtifact` 增加 `sections_path` 已存在;`StdReasonerPromptCapture` 写入 **已含 text** 的 section trace(rev 字段)。
4. `system_prompt_sections.json` 持久化结构升级:`sections: [...{name, kind, optional, used_fallback, skipped_empty, text_chars, text, content_digest}]`;
   - `content_digest = sha256(text)`(`text != ""` 时写,空段不写,便于跳过无意义 hash)。
5. `brain/reasoner.py` `section_outputs` 在 EP payload 里同样带 `text`(沿 ADR-0175 D6 spine EP payload 增字段约定);spine reflector(`lca/plugins/observability/spine/reflectors/cognition.py`) 同步更新 whitelist。
6. **回归锁**:tests/observability/spine/cognition_reflector 加 `assert system_prompt_sections.sections[*].text == 当时 assembler 渲染的正文`。

### D4. Prompt 文件族收敛到 3 个 + reuse-by-inherit(覆盖 P3 重复落盘)
| 当前 | 收敛后 | 来源 |
|---|---|---|
| `system.json` (13465 B) | **合并到 `system_prompt.json`** §"messages 总览" 区段由 `messages.json` 唯一;`system.json` 删除 | `StdModelVisibleCapture._write_messages_payload` 已经写 `system` 字段到 `messages.json`,重复 |
| `system_prompt.json` (13369 B) | 保留,结构新增 `messages_overview` 字段 | `StdReasonerPromptCapture` |
| `system_prompt_sections.json` (2516 B) | 保留,见 D3 §4 | `StdReasonerPromptCapture` |
| `tools.json` (7085 B) | 保留 | `StdModelVisibleCapture` |
| `messages.json` (13251 B) | **改名为 `messages.json` 不变**,但字段命名统一(同时 `StdModelVisibleCapture` 写 `system` 字段变成 `messages_overview.system`) | `StdModelVisibleCapture` |
| `system-prompt.legacy.md` (占位) | **删除**(ADR-0175 D6 COMPAT 解除条件:实际已写 `system_prompt.json`,占位没意义) | `StepTreeAccumulatorDeriver._write_model_visible` |
| `request-header.json` (361 B) | 保留 | `StepTreeAccumulatorDeriver` |
| `manifest.json` (361 B) | 保留;**字段 `body.reasoner_template_id` 与 `system_prompt_sections.template_id` 不重复**——保留 manifest 的 step 级 share,删除**重复写**的 template_id 字段即可 | `StepTreeAccumulatorDeriver` |

**最终 `<run_dir>/model_visible/step_<NN>/` 6 个文件**(per step):
1. `manifest.json` — step 元数据 + share 信息(都从 ADR-0167 D4 `RequestHeader` 派生)
2. `system_prompt.json` — 全文 + 各 section 摘要
3. `system_prompt_sections.json` — section 级 trace(含正文,**真值**)
4. `tools.json` — tool schema 列表
5. `messages.json` — 真实送入 LLM 的 messages[]
6. `request-header.json` — digests + rel paths

**复用策略**:在 `StdModelVisibleCapture` 每次写盘之前,根据 manifest 的 `inherited_from_step` 跳过已 unchanged 的 file(只更新 `request-header.json` 指到旧文件);D4 不实现 file dedup 逻辑但**保留扩展点**(`if unchanged: symlink/hardlink` 在 followup ADR 实现)。

### D5. Doctor 新增 H-xref:journal ⇄ spine 一致性 hop

#### D5.1 hop `H-xref`(broken-when)
对每个 run directory:

```text
H-xref.broken when
  (count(spine.body.tool.execute.start) > 0
   and len(journal.steps[*].tool_call) == 0)                 → "no tool recorded"
  or (count(spine.llm.call.end) > 0
       and journal.totals.steps == 0)                        → "no step recorded"
  or (count(spine.phase.*.fold) > 0
       and journal.totals.phases == 0)                       → "no phase recorded"
  or (count(spine.kernel.run.start) > 0 and not events.jsonl.exists()) → "no events ledger"
```

#### D5.2 DoctorReport H-xref 字段
- `doctor_report.hops["H-xref"] = {ok: bool, detail: "<reason>", ...}`
- `doctor_report.broken_hop` 优先返回 `H-xref`,则 `manifest.extra.doctor_report.broken = "H-xref"`。
- CLI `lca-ops debug-run` 8 段输出新增 "xref" 一节(在 [7/8] suggested_action 后;[8/8] 之前)。

### D6. StepCoordinator 不再被 facade 偷偷调用:重新严格收敛入口(配合 ADR-0167.1 D4)
- **保持 ADR-0167.1 D4 已删 7 个 facade 转发方法**——AGENTS.md C7 控制/观察分离;
- 业务 cognition(L0)继续**不直接 import** `WritableFaceRegistry`(I-PLUG1)。
- 加一条 `tests/test_architecture_imports.py` 守卫:**`lca/cognition/**` 不得 import `lca/infrastructure/observability/writable_matrix.coordinator`**,失败即 fail-fast。

### D7. 删死 / 兼容收缩

| 删除/收紧 | 跟踪 |
|---|---|
| `_write_model_visible`(deriver 整套副作用) | 本 ADR D2 |
| `system-prompt.legacy.md` 占位文件 | ADR-0175 D6 COMPAT 解除(实际真值已落 `system_prompt.json`,删除占位无风险) |
| `system.json` 重复文件(并入 `system_prompt.json` `messages_overview` 区) | 本 ADR D4 |
| `system_prompt_sections.sections[*].text_chars=0` 旧 heuristic(只在 sections 为空时退化) | 本 ADR D3 |
| `(pattern) "writing from deriver"` 任何新增路径必须被 `scripts/check_writable_matrix_boundaries.py` 钩住 | 本 ADR D8(新增 1 条) |

**写一条 COMPAT**:
```python
# COMPAT(delete-when: 0 引用,tracking: ADR-0176 D7)
# 现状:StdModelVisibleCapture 仍写 system 字段到 messages.json;
# 1 个 PR 后改名为 messages_overview.system;bindings 同步更新。
```

## 3. 一次性合题(SSOT / 五面矩阵 / DRY)

### 3.1 落盘路径

```
Agent / Brain / Body / Perceive (L0 cognition)
  │
  ▼  唯一可见入口
StepCoordinator.bind_run(...) → record_* / begin_* / end_*       (唯一写)
  │   5 个 record_* / 3 个 begin_* / 3 个 end_*
  ▼
WritableFaceRegistry 解引用:
  emitter          → SpineEmitter  → EventSpine.append → RoutingFileSink → events.jsonl (SSOT)
  driver           → StandardDriver → segment/phase split
  coalescer        → LineCoalescer  → per-EP buffer
  serializer       → NdjsonSerializer → dataclasses.asdict
  storage          → RoutingFileSink → events.jsonl (同上,同一 emitter)
  + model_visible_recorder → FilesystemRecorder     # 由 ModelVisibleLLMAdapter only 触发
  + replay_cursor           → StandardCursor
                       │
                       ▼ subscribe(每 run transport 装配)
                  StepTreeAccumulatorDeriver  (纯订阅 + 物化:仅入 journal.json)
                  NarrativeDeriver           (人读轨迹 markdown)
                  GraphDeriver               (Mermaid 交互)
                  LiveTail / Anomaly / OTel   (只读投影)
```

不变量 I-PLUG1–6 + I-MV1–4 + I-VIEW1–3 同时生效。deriver **不再写 model_visible**;`ModelVisibleRecorder` **只** 由 Model-visible LLM adapter 单点触发。

### 3.2 Prompt section → journal 链路

```
PromptSectionRegistry.resolve  →  SectionOutput(text=...)  → render_template
  │
  ▼
PromptTrace = (sections=[SectionTrace(name, kind, optional, used_fallback,
                                     skipped_empty, text_chars, text=...), ...],
               system_prompt_text = joined, total_chars)
  │
  ▼ 注入 EP payload(section_outputs) + StdReasonerPromptCapture
two writes (immutable):
  model_visible/step_NN/system_prompt.json         (full text + section brief)
  model_visible/step_NN/system_prompt_sections.json (sections with text + content_digest)
```

`text_chars` 与 `text` 同步;不再"只剩数字"。

## 4. 后果

### 4.1 正面

- **journal.json 不再是空 document**:backend ReAct run 落 3 step / 多 phase;doctor H2 / H-xref 同时看到一致;
- **prompt section 有真值**:section text + content_digest 落盘,replay 可从 sections 文件重建;
- **model_visible 不再被两套 writer 反复写**:`_write_model_visible` 删除后,`<run_dir>/model_visible/` 的写入总次数下降;
- **deriver 纯投影**:只负责 `events.jsonl → journal.json`,副作用迁移到 `ModelVisibleRecorder`;
- **scripts/check_writable_matrix_boundaries.py** 新加一条护栏,**回归锁死** deriver 写盘新通道;
- **deprecation 是有条件的**:`StdModelVisibleCapture.system` 字段改名有 COMPAT 块,空 fallback 可被工具链识别。

### 4.2 负面 / 风险

- doctor H-xref 一旦命中,会让"已完成"的 run 报 broken——属于"先让红绿灯说真话",docs/run-debug-guide §5 加一段"看到 H-xref 时怎么修";
- `system.json` 删除会让一段老 viewer 失效,但 model_visible ADR-0167 D3 已说"viewer 应改读 system_prompt.json"——一起改;
- `StdReasonerPromptCapture` 写入文件大小上扬(每段 section 多一段正文),正常 privacy 策略(脱敏 key)已生效。

### 4.3 不做的事

- 不动 `WritableFaceRegistry` Protocol 形态;
- 不动 `events.jsonl` SSOT(用户已经在运行 trace flow);
- 不实现 file-level dedup(`inherited_from_step` 现已可写,follow-up ADR 单独);
- 不动 `WritableFaceRegistry.register("emitter",...)` API;
- 不让 deriver 接收 sidecar 写盘指令;
- 不为 `phase.think.fold / phase.act.fold` 新增 EP(走 `_apply` 已有分支);
- 不为这一 PR 动 `kernel` 顶层包(K1–K8 保持冻结)。
- **不向上调整 SSOT**:仍以 `events.jsonl` 为 SSOT。

## 5. 验收

### 5.1 运行验收(必跑)

```bash
# 1. 写 ADR + 走 PR-lint,不进 ADR-0176 自身 schema 校验
uv run ruff check --fix lca/infrastructure/observability tests/observability
uv run ruff format lca/infrastructure/observability tests/observability

# 2. 单测 —— deriver / capture / section trace / doctor
uv run pytest tests/observability/spine/derivers/test_step_tree_accumulator.py \
              tests/observability/loop_cursor/test_reasoner_prompt_capture.py \
              tests/cognition/brain/test_sections.py \
              tests/observability/loop_cursor/test_model_visible_capture.py \
              tests/lca_plugins/transport/webserver/handlers/runs/doctor/ \
              -q

# 3. 接住最新一次 backend ReAct 的 case：跑一次 webstandard backend solo，再读 journal.json
./scripts/lca-ops kernel-restart
# trigger via whatever UI / API your profile exposes for backend solo
LATEST=$(jq -r .run_id traces/latest.json)
# 拿到 4 件:
test "$(jq -r '.steps|length' traces/runs/$LATEST/journal.json)" -ge 1  # P1 修复
test "$(jq -r '.phases|length' traces/runs/$LATEST/journal.json)" -ge 3  # P1 修复
jq -r '.sections[0].text_chars' traces/runs/$LATEST/model_visible/step-001/system_prompt_sections.json
# > 真实 section text_chars (> 0)  # P2 修复
test ! -f traces/runs/$LATEST/model_visible/step-001/system.json                       # P3 修复
test ! -f traces/runs/$LATEST/model_visible/step-001/system-prompt.legacy.md           # P3 修复
./scripts/lca-ops debug-run "$LATEST" | grep -E 'xref|broken'                          # D5

# 4. 架构测试守护
uv run pytest tests/test_architecture_imports.py -q
uv run lint-imports
uv run mypy lca
uv run vulture lca --min-confidence 80
uv run scripts/check_writable_matrix_boundaries.py
```

### 5.2 契约验收(必查)

- `journal.json`: `steps.len ≥ 1`、`phases.len ≥ 3`(每 think 至少有 think + reflect(若)= phase);
- `system_prompt_sections.json`: `sections[*].text_chars > 0`、`sections[*].text != ""`(allowed_empty=true 段除外);
- `model_visible/step_*/*.md` 数量从 7 缩到 6;
- `events.jsonl` 与 `journal.json` 的 total_steps 比例 ≤ 4×(走完"`steps ⇄ 相邻 LLM calls`"概念)。

### 5.3 不变量验收

- I-PLUG1:`rg "lca.cognition.*event_spine\b" lca/cognition` → 0 hit;
- I-PLUG5:同一 `events.jsonl` → `replay(deriver).totals` 与 live `flush().totals` 一致;
- I-MV1:每个 LLM call 都有可解析的 `RequestHeader`(跑 `tests/observability/loop_cursor/test_request_header_round_trip.py`);
- I-MV2:模型可见正文没有平行 `messages[]` 复制(`StdModelVisibleCapture.system` 字段改名 `messages_overview` 后只剩一处)。

## 6. 实施分期(2 个 PR,每个可独立 merge)

| PR | 内容 | 验收 |
|---|---|---|
| **PR-1** (D1+D5) | StepTreeAccumulator `_apply` 扩 PHASE_FOLD_EPS + 加 brain.think.start/end fallback step 包络 + `flush()` 空写 fail-loud + doctor H-xref + tests | P1 修;sister-run 同样空 journal 即被 H-xref 报 broken。 |
| **PR-2** (D2+D3+D4+D7+D8) | deriver 删除 `_write_model_visible` + `ModelVisibleRecorder` registry 落地 + `StdModelVisibleCapture.system` 改名 + `SectionTrace.text` 字段 + `system.json` 与 `system-prompt.legacy.md` 删除 + `scripts/check_writable_matrix_boundaries.py` 新增 deriver 写盘护栏 | P2/P3/P4 同时修;回归 5.1 / 5.2。 |

### 6.1 PR 描述模板(给 reviewer 一行)

> 重构 journal 空文档与 model_visible 重复落盘:ADR-0176 D1(d)把 StepTreeAccumulator 改成能从 backend ReAct 累积 step / phase,flush 空写时 fail-loud;D5(里)H-xref 让 doctor 看到 journal ⇄ spine 不一致;D2/D3/D4(还)deriver 删写盘 / SectionTrace.text / system.json 合并;**driven by 一次 backend solo 实际跑出来的现象**。

## 7. 附录:从 ADR-0167 / 0167.1 / 0175 承接的特定条款

| 旧条款 | 本 ADR 落点 |
|---|---|
| ADR-0167 D11 I-PLUG3(链上任一面可替换) | D2 `ModelVisibleRecorder` 进 registry |
| ADR-0167 D11 I-PLUG5(不影响 SSOT) | D1 §1(扩 EP 视图不动 vocabulary)+ D2(deriver 删副作用) |
| ADR-0167 D13 B7(一 plugin 一目录) | D2 deriver 单一职责 |
| ADR-0175 D2(`SectionTrace.text_chars`) | D3 升级 `SectionTrace.text` |
| ADR-0175 D6(legacy `system-prompt.legacy.md` COMAPT) | D7 解除占位 |
| ADR-0167.1 D3(journal.json 唯一写) | D1 不变;D2 守住同一原则的对侧(d-m-v) |
| ADR-0169 L10 / L16(env white-list + projection plugin) | 不动 |

## 8. 工程记录

- AGENTS.md §1"工程思维 · 第一性原理 + 职责单一 + 离开前卫生清单"全部沿用;
- 不写 `try/except Exception: pass`;
- 不留没有 ADR 的 TODO;
- 不为"先让 CI 绿"吞掉 fail-loud;
- 离开前跑 `git diff --check`、`ruff check --fix`、`uv run pytest`;
- 改动 closure 表(AGENTS.md §1):
  - Protocol / 公共签名(`StepCoordinator` 不变、`StepTreeAccumulator._apply` 的 EP 分支扩;`SectionTrace` 增 `text` 字段):
    - 同时改 Profile / Bundle / 测试 / ADR-0175 / ADR-0169;
  - EP / 词表:`brain.think.start/end` 兜底 step 边界不改 vocabulary,只作为"前已有 EP 的语义强化";`step.tool_call.record` 不变;新增 0 EP;
  - Schema / Journal:`JournalStep.sections[*]` 数据形不变(还是 `SectionTrace`),只是 `SectionTrace` 多字段;
  - 注册表:`writable_matrix.registry` 加 `model_visible_recorder` 槽已存在,Profiles 同步注册。

## 9. 参考

- **ADR-0167**(Spine 唯一耐久真值 + Step 物化 + 五面矩阵) — D11 / D13
- **ADR-0167.1**(Step-Tree deriver wiring + run layout) — D2–D7
- **ADR-0169**(LoopCursor 控制面) — D8–D10
- **ADR-0175**(prompt trace 落 model_visible / spine EP payload 扩字段)
- **AGENTS.md §1** — 工程思维·第一性原理 + 离开前卫生
- **样本 run**:`traces/runs/run_4ad3407f56fb/`(510 行 spine / 390 KB events / 0 journal steps)
- **sister-run**:`traces/runs/run_046515e96ac7/`(同现象,说明 backend ReAct 系统性缺陷)
