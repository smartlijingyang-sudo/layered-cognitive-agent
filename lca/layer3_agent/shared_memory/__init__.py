"""团队共享记忆子包 —— Tool 访问路径（ADR-0016）。

L3 层职责：
    将 SharedMemoryStore 包装为标准 Tool，使团队成员
    在单体认知循环内通过 use_tool 访问共享存储，
    与调用 calculator 等工具无区别，不改 Body / Runtime 协议。
"""

from lca.layer3_agent.shared_memory.shared_memory_tool import SharedMemoryTool

__all__ = ["SharedMemoryTool"]
