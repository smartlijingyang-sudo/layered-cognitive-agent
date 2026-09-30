# Agent Note: 做梦慢路径消费流水、维护亲近度并产出对齐综述

Status: implemented

## Problem

`lca-ops memory dream` 只消费 episode buffer。每日流水（`memory/YYYY-MM-DD.md`）没有进入固化，人物/群体索引只按名称排序，也没有 ADR 要求的夜间对齐综述。

## Decision

`run_dream` 现在同时读取每日流水与 episode buffer。流水按行解析成 episode fact 参与合并：显式偏好（「偏好」「必须」「记住」等）带用户授权，一次即可固化到 `MEMORY.md`；一次性事件事实留在流水里供检索。关系维护按提及次数给人物/群体页写亲近度分数，索引按亲近度降序重排。合成 `dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`：只收偏好与身份，每条断言携带 `message:<id>` 证据引用，文档注明它是软调参而非硬指令。同一趟还重建 `memory/index` 的 FTS 索引。`think.history.assemble` 在每次装配时读取该综述并追加到系统提示。`DiskFileStore` 对 `memory/YYYY-MM-DD.md` 拒绝非追加写入；`TrailWriter.overwrite` 抛 `NarrowGateViolationError`。

## Alternatives considered

### 为什么让流水参与合并而不是直接写入？

直接写入会让每条流水都成为一条事实。通过 episode 合并语义，只有重复出现或用户明确授权的残差才会固化，流水仍只是证据。

### 为什么对齐综述不用 LLM 生成？

repo 策略默认不跑 `real_llm`。综述从证据确定性生成，引用可审计；后续可以换成 LLM 合成而保持文件格式不变。

## Verification

`tests/infrastructure/memory/test_dream_pipeline.py` 覆盖两次运行幂等、亲近度排序、`MEMORY.md` 整合与综述产出。`tests/scenario/memory/test_adr0254_conformance_evals.py` 的 EVAL-DREAM-ALIGNMENT-SYNTHESIS 断言每条断言都匹配 `message:[a-zA-Z0-9_-]+`。`tests/infrastructure/memory/test_trail_append_only.py` 覆盖流水只追加。