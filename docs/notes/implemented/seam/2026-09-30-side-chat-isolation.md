# Agent Note: Side Chat 分支记忆隔离与隐私防火墙

Status: implemented

## Problem

分支会话没有独立的记忆。分支里产生的结论会写进主 `MEMORY.md`，污染主记忆；检索也没有跨分支的概念。

## Decision

每个 side chat 拥有 `side-chats/<id>/MEMORY.md`。`memory_add` 带 `branch` 参数时，事实写入该分支文件，主记忆完全不变。`memory_search` 带 `branch` 时检索主结构化记忆与该分支文件，但主记忆里的私人内容（作息、病史、住址、凭证）不会进入工具结果。系统提示新增 `privacy_firewall` 段落，渲染「检索到不等于可透露」条款。目录名、分支文件名来自 `layout.toml`。写入带读-改-写守卫：文件在读取后、替换前发生变化会拒绝写入。

## Alternatives considered

### 为什么分支事实不进 semantic.json？

ADR-0247 的记录库是主记忆真值。分支结论是未定决议，写进主记录库会让下一次检索把它当成跨会话事实。

### 为什么不用一个独立的 side-chat 记录库？

分支记忆要能直接打开和手改。Markdown 文件满足这个要求，检索通过解析和全文索引实现。

## Verification

`tests/infrastructure/memory/test_side_chat.py` 覆盖分支写入不改变主 `MEMORY.md`、跨主分支检索、隐私防火墙段落渲染。`tests/scenario/memory/test_adr0254_conformance_evals.py` 的 EVAL-SIDE-CHAT-PRIVACY 覆盖分支机密不泄露到主记忆。