"""layer-top — 统一认知执行体层。

重构 LCA 五层架构的 Agent / Team 双协议为单一 Worker 协议，
Task 作为对象形式参数取代裸字符串，支持递归嵌套组合。

契约层见 ``layer_top.contracts``，实现层见后续模块。
"""

from __future__ import annotations

from layer_top.contracts import Task, Worker

__all__ = ["Task", "Worker"]
