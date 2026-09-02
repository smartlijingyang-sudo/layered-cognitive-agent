"""认知循环 → journal 直接发射(开闭原则,ADR-0037)。

ADR-0169 §D9 删除清单:本模块在 PR-26 阶段清理。

清理内容:
- ``_derive_step_completed`` —— 整段删除(原 ``HookEvent.POST_REFLECT`` 派生;
  业务路径迁移 cursor 后 ``coord.emit_phase('reflect')`` 已下线,不再需要派生)。
- ``make_journal_emitting_hook`` —— 整段删除(hook 范畴错误,ADR-0168.1 L19;
  业务路径只走 ``cursor.advance(phase)`` + ``cursor.record_*(...)``)。
- ``JournalEmitFn`` —— 删除(仅 hook 内部使用)。
- ``_derive_action_degraded`` —— 删除(``make_journal_emitting_hook`` 删除后
  无调用方;ActionDegraded 派生改走 cursor.record_*(...) 路径或由 ProjectionHost
  派生,ADR-0170 阶段处理)。

剩余:模块保留空 shell 以容纳未来 ADR-0167 + ADR-0170 装配落地期间的辅助函数;
新增事件派生走 ProjectionHost.register(def) 入口,不再 emit ``JournalEvent``
直写路径(ADR-0169 D8 五缝职责唯一)。
"""

from __future__ import annotations

# COMPAT(delete-when: ADR-0170 落位后评估整模块是否需要保留, tracking: ADR-0169-task-26)
# 当前为 ADR-0169 §D9 删除后的空壳;保留模块文件避免外部 `from lca.runtime.event_emission`
# 引用断裂。Module 内容已审计,无可派生函数。
