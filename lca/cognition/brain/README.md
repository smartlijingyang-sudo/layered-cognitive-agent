# lca/cognition/brain

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
认知层的 Prompt Reasoner 实现：模板渲染、LLM 调用、流式增量解析、Decision / ToolCall 抽取。把上游的 Decision 候选变为可执行的 tool invocations，并通过 Body dispatch 落入 effect handler。

## 2. 不负责
tool 选型策略、记忆检索、prompt 元数据管理（这些是 memory/ 和 cognition/其他子包的职责）。

## 3. 输入
- 当前包内 `27` 个公开模块 + `112` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：4 个显式 __all__ 条目； 112 个定义符号中，57 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ConcatSynthesizer`
- `ModularBrain`
- `PromptReasoner`
- `SimpleCritic`

**模块清单**:

- `lca/cognition/brain/_loader.py`
- `lca/cognition/brain/artifact_respond_injector.py`
- `lca/cognition/brain/chained.py`
- `lca/cognition/brain/cognitive_pipeline.py`
- `lca/cognition/brain/context_manifest.py`
- `lca/cognition/brain/conversation_prompt.py`
- `lca/cognition/brain/critic.py`
- `lca/cognition/brain/default_factory.py`
- `lca/cognition/brain/executor.py`
- `lca/cognition/brain/leaked_tool_call.py`
- `lca/cognition/brain/mode.py`
- `lca/cognition/brain/modular_brain.py`
- `lca/cognition/brain/must_consult_all.py`
- `lca/cognition/brain/null_critic.py`
- `lca/cognition/brain/null_synthesizer.py`
- `lca/cognition/brain/office_works_sealer.py`
- `lca/cognition/brain/policy.py`
- `lca/cognition/brain/progress_loop_detector.py`
- `lca/cognition/brain/reasoner.py`
- `lca/cognition/brain/repeat_tool_call.py`
- `lca/cognition/brain/sandbox_prompt.py`
- `lca/cognition/brain/skill_router.py`
- `lca/cognition/brain/synthesizer.py`
- `lca/cognition/brain/terminal_respond.py`
- `lca/cognition/brain/tool_call_stream.py`
- `lca/cognition/brain/tool_conversation.py`
- `lca/cognition/brain/tool_loop_breaker.py`
