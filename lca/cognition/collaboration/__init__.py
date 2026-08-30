"""L1 协作控制面（v3 §11 / PR9b / PR8 / PR9）。

子模块：
- ``blackboard`` —— Blackboard Protocol + read/append/CAS/lease 与内存实现

新原语（黑板 / 团队消息）按 spec §11 顺序落地；本包是 §11 章节的
L1 承载位（不含运行时编排，那是 L2 / L3）。
"""
