# Agent Note: 折叠系统提示里的常驻文件跟磁盘

Status: implemented

## Problem

`think.reason.render` 每轮从磁盘重读常驻文件。`think.history.assemble` 在折叠出的系统提示非空时采用那份旧提示，本轮渲染到不了模型。第二轮之后，人改过的 `MEMORY.md` 仍停在上一轮的副本里。

## Decision

折叠提示继续负责规则和历史骨架。提示里已经有注入标记时，`preserve_standing_sections` 按 `FileStore` 重读 `SOUL.md`、`USER.md`、`MEMORY.md`、`AGENTS.md`、`TOOLS.md`，只替换这些块。正文不摘要、不截断。没有注入标记的历史提示保持原样。替换发生时发布 `StandingPreserved`。

## Alternatives considered

### 为什么不改成永远采用本轮渲染？

折叠提示是回放时的系统提示来源。整段换成最新渲染会把规则和时钟一起换成当前磁盘，回放不再对应当时发出的请求。

### 为什么不在压缩时把常驻文件放进摘要？

常驻文件是当前副本。摘要只应该缩短对话历史。

## Verification

`tests/infrastructure/memory/test_standing_preservation.py` 覆盖替换、不截断、无标记不变、重复调用不叠加说明。`tests/unit/plugins/think/test_history_assemble_plugin.py` 覆盖折叠提示保留规则并换上磁盘上的记忆。
