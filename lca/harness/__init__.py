"""Harness — profile 装配、声明式阶段图、插件机制骨架、投影与技能。

Session 事件真值层（append / observer / fold / 持久化）归 ``lca.plugins.session``
（ADR-0186）；旧 ``harness.command`` 命令面与 ``harness.agent`` live-agent
registry 面已退役（命令入口归 runs 平面）。

cordis migration complete. Submodules import directly from their respective submodules.
Use cordis.Context directly instead.
"""
