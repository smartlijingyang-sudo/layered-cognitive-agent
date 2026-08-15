# 用 DSH — 对比跑道设计

**日期**: 2026-08-15
**状态**: Canonical（落地中）
**关联**: [2026-08-14-deepseek-harness-integration-analysis.md](./2026-08-14-deepseek-harness-integration-analysis.md)（借鉴全景与优先级）

## 第一性原理

一次 Run 只有一个 **driver**。`用电脑` / `云沙箱` 选磁盘；`用 DSH` 选谁当 agent。DSH 不是第三种 plane。

整题转发，不拆工具。事件分两层：Journal 投影给 LobeHub；原始 DSH JSONL 留给对照。

模型 / 密钥只读 ``lca.layer0_infra.llm.config``（``LLM_MODEL`` / ``LLM_API_KEY``）。DSH 走 ``OPENAI_COMPAT`` 面（``LLM_OPENAI_BASE_URL``）。`DSH_*` 只剩进程参数。`provider=deepseek-official` 是 DSH 适配器路由名。

## 模块

| 单元 | 职责 |
|---|---|
| `dsh/routing.py` | `execution_target == dsh` |
| `dsh/settings.py` | pydantic-settings + Qwen 回落 |
| `dsh/models.py` | 通知 / 结果 |
| `DshRuntime` | 子进程端口 |
| `SdkDshRuntime` | SDK 适配器 |
| `DshJournalProjector` | session.event → Journal |
| `JsonlEventArchive` | 原始通知 |
| `DshTurnDriver` | 一轮编排 |
| `gateway/runs/dsh_execute.py` | 接到 RunSession |
| 输入栏「用 DSH」 | `execution_target: dsh` |

## 数据流

```
chip 用 DSH → POST /runs {execution_target:dsh}
  → execute_run 跳过 Agent/Team
  → DshTurnDriver + Qwen 兼容口
  → Journal SSE → 现成卡片
  → {run_id}.dsh.jsonl
```
