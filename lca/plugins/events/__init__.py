"""事件 plugin 统一目录（ADR-0180）。

按 pub/sub 区分：

- ``publishers/`` —— 业务方 producer plugin（如 delegation_cache）
- ``sinks/`` —— sink plugin（如 journal sink，把事件写盘）
- ``subscribers/`` —— 业务方 consumer plugin（如 console_projector）

机制本体在 :mod:`lca_kernel.events`（kernel 元层，不在此）。
"""
