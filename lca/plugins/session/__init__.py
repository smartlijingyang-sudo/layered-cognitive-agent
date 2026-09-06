"""Session 域 plugin 目录（ADR-0195 迁移中）。

事实平面（append / catalog / fold / bind / repair / checkpoint / recovery）
已提升到 :mod:`lca.session`；本目录保留 runtime 装配、投影、遥测与 checkpoint
policy plugin（``bundles/session-runtime.yaml`` 仍引用）。

# COMPAT(owner: ADR-0195 P5-02, from: plugins/session 单体 runtime,
# to: lca.session + 薄 plugin 壳,
# delete_when: bundles/session-runtime.yaml 无 lca.plugins.session.runtime 条目
#   AND rg "from lca.plugins.session.runtime.(session|event_catalog|repair|bind|recovery|fold|checkpoint) import" lca/ tests/ = 0
#   AND rg "from lca.plugins.session.runtime.(bus.bus_facade|log.log_reader|cursor.cursor_port|spine.spine_hook|spine.spine_event_projection|resume.resume_point) import" lca/ tests/ = 0,
# forbidden_new_usage: 新事实平面代码 import lca.plugins.session.runtime.{session,repair,bind,...})

契约面在 :mod:`lca_kernel.events.session`（kernel 元层，不在此）。
"""
