# Agent Note: 常驻文件的变更以差异进入下一次装配

Status: implemented

## Problem

常驻文件块会在下一次装配时换成磁盘上的新正文。模型看到的是整份新文件，看不到哪一行变了。监听如果在历史装配节点里写快照，会让只读节点改助理主目录。

## Decision

`StandingCursor` 记住上一份 `SOUL.md`、`USER.md`、`MEMORY.md`、`AGENTS.md`、`TOOLS.md`。第一次轮询只建立基线。之后的轮询用统一差异描述变化，并发布 `StandingChanged`。读失败时保留上一份正文，不把故障报成删除。`think.history.assemble` 通过进程内的 `poll_standing_home` 取差异，附在系统提示后面。游标不写入主目录。

## Alternatives considered

### 为什么不用 Inotify 线程？

活跃会话的注入点是下一次历史装配。进程内游标在这一步就能给出差异。Inotify 可以以后换成同一个差异文本，不必先改节点。

### 为什么不把上一份副本写进主目录？

历史装配声明不改状态。副本留在进程里，重启后的第一次装配重新建立基线。

## Verification

`tests/infrastructure/memory/test_standing_watch.py` 覆盖首次沉默、第二次差异、读失败不报删除。`tests/unit/plugins/think/test_history_assemble_plugin.py` 覆盖第二次装配把差异附进系统提示。
