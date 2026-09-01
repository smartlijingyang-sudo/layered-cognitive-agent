"""stream subpackage —— ADR-0164 Phase 7 已裁剪。

- ``NarrativeSidecar`` 已删除 (由 ``StepNarrativeWriter`` 接管)
- ``FactStreamProjector`` 已删除 (v2 stream envelope 不再主用)

仅保留 ``SidecarHook`` Protocol + ``LiveTail``(SSE 推流用)。
"""
