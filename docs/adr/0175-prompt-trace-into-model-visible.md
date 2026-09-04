# ADR-0175: 把真 brain prompt 捕获进 model_visible/, 并扩 spine EP payload

> **本文档已被 [ADR-0185](0185-model-visible-event-bus-alignment.md) 取代**;`StdReasonerPromptCapture` 默认实现、`<run_dir>/model_visible/system_prompt.json` 与 `system_prompt_sections.json` 由 ADR-0185 收口(改走 `SpineLlmRequestHeaderPayload.system` 字段)。本文档保留全文作历史。

- Status: proposed(已被 ADR-0185 Superseded)
- Date: 2026-09-02
- Supersedes: none
- Depends on: ADR-0169 §D7, ADR-0165 I8 (EXECUTION_POINTS close-set), ADR-0117 K7 (env白名单)
- Scope: `lca/cognition/brain/`, `lca/infrastructure/observability/loop_cursor/`,
  `lca/infrastructure/observability/spine/reflectors/cognition.py`,
  `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py`,
  `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py`,
  `lca/plugins/prompts/selector.py`

## 背景

现状(基于代码事实,2026-09-02):

1. `lca/contracts/observability/model_visible_capture.py` 把 `model_visible/step_<NN>/` 5 件套
   定为「LLM 边界 SSOT」,但当前**两个并行 writer 都没拿到真的 brain prompt**:

   - `StdModelVisibleCapture` (`lca/infrastructure/observability/loop_cursor/model_visible_capture.py`)
     暴露的 `_derive_capture_inputs` (`lca/infrastructure/observability/adapters/model_visible_llm_adapter.py:130`)
     把 `system` 写为占位 `{"objective":"(see provider prompt catalog)","derived":True}`,
     `messages` 写为单条 user message 派生。

   - `step_tree_accumulator._write_model_visible` (`lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py:389`)
     写 `system-prompt.md`,内容只是 `frame.context_before.objective` 摘要。

2. `reasoner._render_prompt` (`lca/cognition/brain/reasoner.py:239`) 拼出来的**真** system prompt(17 个
   sections)从来没落盘,只传给 `execute_llm_turn`,然后被 LLM provider 吃下。

3. `prompt_assembler.assemble.start` / `.end` 两个 EP 在
   `lca/infrastructure/observability/spine/manifest.py` 白名单里有(ADR-0165 I8),但
   `reasoner._render_prompt` **没调用** `emit_prompt_assembler_*`。
   `tests/observability/` 下也无对应 EXECUTION_POINT_TEST(grep 0 hit)。

4. `TeamAwarenessTemplateSelector.select()` (`lca/plugins/prompts/selector.py:43`) 的决策路径
   (`active_template` / `consult_duty` / `team_awareness` / `profile_default`) **没暴露到** spine,
   只透出最终 `template` 字符串。

5. `lca/cognition/brain/prompts/*.md` + `_loader.py` 是死代码,核心 prompt 装配链全在
   `lca/plugins/prompts/{template_provider,sections,assembler,selector}.py`,
   没看到 `load_builtin_prompt()` 的调用方。

## 问题

- "模型实际看到什么" 与 "模型应该看到什么" 在 `traces/runs/<id>/model_visible/` 不可重建。
- `prompt_assembler.assemble.*` EP 是空头白名单,新增失败类调试时无据可查。
- `step_tree_accumulator` 的 `system-prompt.md` 与 `StdModelVisibleCapture` 的
  `system.json` 同名不同源,**两个 fake**。

## 决策

### D1: 真 brain prompt = `ReasonerPromptCapture` 新接缝

新增 `ModelVisibleReasonerPromptCapture` Protocol + Std 实现,
职责单一:把 `(template_id, sections, activated_skill_ids, selector_decision_path,
tools_count, available_skills_count, system_prompt_text)` 一次性写入
`<run_dir>/model_visible/step_<NN>/{system_prompt.json, system_prompt_sections.json}`,
并返回 `ReasonerPromptArtifact`(类比 `ModelVisibleArtifact`)。
**不**进入 `ModelVisibleCapture` 的 5 件套(职责分离:那 5 件套是「真实发出去的内容」,这是
「内容是怎么拼出来的」)。

### D2: `SectionManifestPromptAssembler.render` 返回结构化信息

扩展返回类型:`str → tuple[str, SectionTrace, PromptTrace]`。
- `SectionTrace`(每段): `{name, kind, text_chars, used_fallback, skipped_empty, optional}`。
- `PromptTrace`(全文): `{template_id, variant, sections: list[SectionTrace],
  total_chars, activated_skill_ids: tuple[str, ...], selector_decision_path: str,
  tools_count: int, available_skills_count: int, system_prompt_text: str}`。
纯函数扩展,不破坏既有调用方(reasoner 拆返回值即可)。

### D3: reasoner 是唯一捕获点

`reasoner._render_prompt` 在拿到 `(prompt, sections, trace)` 后:

1. 通过 `emit_prompt_assembler_start(state_id, template_id, sections=...)` 与
   `emit_prompt_assembler_end(... , section_outputs=...)` 落 spine EP,
   payload 含扩展字段(`sections`, `activated_skills`, `tools_count`,
   `available_skills_count`, `decision_path`, `section_outputs[]`)。
2. 通过 `bind_current_reasoner_prompt(trace)` 把 `system_prompt_text` 注入 ContextVar,
   让同 run 后续 `ModelVisibleLLMAdapter._derive_capture_inputs` 能读到,不用改 adapter signature。
3. 在 `execute_llm_turn(...)` 调用结束后 `reset_current_reasoner_prompt(token)`。

### D4: LLM adapter 读真 system

`_derive_capture_inputs` (`lca/infrastructure/observability/adapters/model_visible_llm_adapter.py:130`)
读 `get_current_reasoner_prompt()`.system_prompt_text,非空则写入 5 件套 `system.json`;
空则保留现有占位(向后兼容,reasoner 没跑也照样能跑)。

### D5: selector 暴露决策路径

`TeamAwarenessTemplateSelector.select()` 返回 `tuple[str, str]` = `(template_id, decision_path)`。
Protocol 扩展在 `lca/contracts/models/cognition/prompt_assembly.py`:
`PromptTemplateSelector.select(*, state) -> tuple[str, str] | str`(Union 兼容旧实现,
旧实现仍可返 `str`,新 helper 把 `str` 当 `(str, "legacy")`)。

`emit_skill_router_route` payload 加 `decision_path: str`。
PR-3.2 reflector (`lca/plugins/observability/spine/reflectors/cognition.py:262`)
扩展关键字参数,默认 `"unknown"`。

### D6: `step_tree_accumulator` 不再写 fake system-prompt.md

`_write_model_visible`:
- 删除 `system-prompt.md` 写入(由 D1 的 `system_prompt.json` 替代)。
- 改为若 `model_visible/step_<NN>/system_prompt.json` 不存在,写**只读 pointer**
  `system-prompt.legacy.md` 含一行 `# see system_prompt.json`(给旧 viewer)。
- 其它文件(`request-header.json` / `tool-schemas.json` / `context-manifest.json` /
  `messages.json`)保留(它们来源独立、不是 brain prompt)。

### D7: 死代码复查

`lca/cognition/brain/prompts/` 下的 `.md` + `_loader.py` **有活跃调用方**:
- `lca/plugins/seams/collaboration/team_casting_prompt_renderer.py`
  调 `load_builtin_prompt("casting_prompt")`;
- `lca/plugins/seams/think/reasoner_template_catalog.py` 同样调用。
- `lca/infrastructure/attachment/system_role_renderer.py` + `sandbox_prompt.py`
  通过 `render_system_role(template_name="cloud_sandbox_system_role")` 走
  同 package 的 loader。

**结论**:本 ADR 不删 `prompts/`,只删"fake system-prompt.md"(
  由 D6 的 `system-prompt.legacy.md` 指针替代)。后续若要做
  `casting_prompt` 全声明化(进 `_builtin_templates`),另起 ADR。

### D8: 不新增 EP

复用现有白名单:
- `prompt_assembler.assemble.start` / `.end` —— payload 字段扩展,不加新 EP。
- `skill_router.route` —— payload 字段扩展,不加新 EP。
- `llm.request.header` —— digest 字符串不变,`system.json` 写的是真 prompt 但 digest 形式同。
符合 ADR-0165 I8 close-set 要求。

## 不变量

- I1(契约闭集):EXECUTION_POINTS 不变。
- I2(SSOT):`system_prompt_text` 的真值只由 `reasoner._render_prompt` 写一次。
- I3(失败不挡业务):新 capture 失败 log + 透传,reasoner 主路径不抛。
- I4(测试覆盖):新增 EXECUTION_POINT_TEST 覆盖 `prompt_assembler.assemble.{start,end}`
  在 capturing spine 中被发射。
- I5(向后兼容):旧 `PromptTemplateSelector` 实现返 `str` 仍可工作。
- I6(dead code):`prompts/*.md` + `_loader.py` 在 PR 内删除。

## 改动清单

| 文件 | 改动 |
|---|---|
| `docs/adr/0175-prompt-trace-into-model-visible.md` | 本 ADR |
| `lca/contracts/models/cognition/prompt_assembly.py` | `PromptTrace`/`SectionTrace`/`ReasonerPromptArtifact`/`ReasonerPromptCapture` Protocol;`PromptTemplateSelector.select` Union 返 |
| `lca/cognition/brain/sections/assembler.py` | `SectionManifestPromptAssembler.render` 返回 `(prompt, prompt_trace)`;`render_template` 同上 |
| `lca/infrastructure/observability/loop_cursor/reasoner_prompt_capture.py` | 新文件:`StdReasonerPromptCapture` |
| `lca/infrastructure/observability/loop_cursor/reasoner_prompt_binding.py` | 新文件:ContextVar 注入 |
| `lca/infrastructure/observability/loop_cursor/__init__.py` | re-export 新符号 |
| `lca/contracts/observability/__init__.py` | re-export `ReasonerPromptArtifact`/`ReasonerPromptCapture` |
| `lca/cognition/brain/reasoner.py` | `_render_prompt` 拆 trace,emit EPs,ContextVar 配对 |
| `lca/plugins/observability/spine/reflectors/cognition.py` | `emit_prompt_assembler_*` payload 扩字段;`emit_skill_router_route` 加 `decision_path` |
| `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py` | `_derive_capture_inputs` 读 `get_current_reasoner_prompt()` |
| `lca/plugins/prompts/selector.py` | `select()` 返回 `(template_id, decision_path)` |
| `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py` | 不再写 `system-prompt.md`;改写 `system-prompt.legacy.md` 指针 |
| `lca/cognition/brain/prompts/*.md` + `_loader.py` | 删除(已 rg=0) |
| `tests/cognition/test_assembler_section_trace.py` | 新测试:trace 结构断言 |
| `tests/observability/test_execution_point_coverage.py` | 新增:在 capturing spine 里调 reasoner 路径,断言 EP 发射 + payload 字段 |
| `tests/observability/test_reasoner_prompt_capture.py` | 新测试:ContextVar 配对 + 文件落盘 |

## 删除条件(COMPAT 块)

```python
# COMPAT(delete-when: PR-25+ 模型可观测固化 14 天,
# tracking: ADR-0175)
# 条件:每个 traces/runs/<id>/model_visible/step_*/system_prompt.json
#       都存在,且 system_prompt.legacy.md 在 ≥95% run 中不再被引用
```

## 验证

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest tests/cognition/test_assembler_section_trace.py tests/observability/ -q
uv run pytest -m "not real_llm" -q
uv run vulture lca --min-confidence 80

./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
test -f traces/runs/"$LATEST"/model_visible/step-001/system_prompt.json \
  && jq -r '.activated_skill_ids' traces/runs/"$LATEST"/model_visible/step-001/system_prompt_sections.json
./scripts/lca-ops journal trace "$LATEST" | grep -E 'prompt_assembler|skill_router'
```