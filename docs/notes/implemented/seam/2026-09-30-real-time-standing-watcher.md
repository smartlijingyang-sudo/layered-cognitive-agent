# Agent Note: 常驻文件变更由实时监听捕获并注入下一次装配

Status: implemented

## Problem

常驻文件的差异只在历史装配时才同步计算。文件在两次装配之间变了多次，下一次装配只看到最后一次差异；会话空闲时磁盘变更不会产生任何观测事件。ADR 原本规划 Inotify 秒级监听。

## Decision

新增 `RealTimeStandingWatcher`：一个后台线程按可配置间隔轮询助理主目录的常驻文件，在检测到变更时立即捕获统一 diff 并存入进程内待发送队列。`think.history.assemble` 在下一次装配时消费该队列。监听故障被包含：轮询抛错记录 `WATCHER_FAULT` 诊断（日志、`watcher.faults`、可选 `WatcherFault` 事件），待发送队列保持原样，会话照常装配。没有注册监听器时，同步 `StandingCursor` 仍是回退路径。生产运行通过每轮 capability bindings 的 `home_path` 启动监听。轮询线程等效实现 Inotify 的实时语义，1 秒 SLA 记为目标而非门禁。

## Alternatives considered

### 为什么不用 Inotify 线程？

Inotify 是平台相关的，且 ADR 明确不复制 Muse 的 sub-second watcher 内部实现。轮询线程在同一 FileStore 端口上工作，测试可以注入故障，行为确定。

### 为什么不在历史装配节点里写快照？

历史装配声明不改状态。差异副本留在进程内，重启后第一次装配重新建立基线。

## Verification

`tests/runtime/test_fs_watcher_diff_dispatch.py` 启动监听器，编辑常驻文件后断言下一次装配在监听间隔内收到统一 diff。`tests/runtime/test_fs_watcher_fault_tolerance.py` 用 `FaultInjectingWatcher` 断言故障不阻断装配。