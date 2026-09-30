# Agent Note: 一条记忆可以展开八个审计字段

Status: implemented

## Problem

投影文件只有一句带出来源的话。人要追这条事实被谁说过、有多确定、取代了哪一版时，只能去翻 `semantic.json`。

## Decision

`memory_explain` 按记录编号返回 `claim`、`kind`、`salience`、`attribution`、`quote`、`timeline`、`confidence`、`supersession_chain`。展开规则在 `contextfiles` 领域里，入参是 `ExplainableRecord`。`AssistantMemory.explain` 把语义层记录译过去，包含已经退役的旧版本。链条在记录集合之外的链接处停止。

## Alternatives considered

### 为什么不从 MEMORY.md 的句子里解析这八个字段？

句子是投影。置信度和取代链在记录里，不在句子里。

## Verification

`tests/infrastructure/memory/test_explain_claim.py` 覆盖缺链接停止、取代链、以及工具返回这八个字段。
