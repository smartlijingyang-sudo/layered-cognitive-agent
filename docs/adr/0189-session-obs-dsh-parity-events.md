# ADR-0189 — Session 观察面 DSH 对齐：信封扩展与 fork/derive/feedback 词表

## 状态

Proposed(2026-09-05)。延伸 ADR-0186(Session SSOT)与 `PLAN-dsh-obs-parity.md`。

## 决策

1. **`SessionEvent` 信封扩展**：可选字段 `ignorable`、`surface_op`、`source_event_seqs`；
   旧记录缺字段按 `ignorable=False` 读；读路径 unknown 且非 ignorable → fail-closed。
2. **新 Session 词表**：`session.end_seed.v1`(fork 边界)、`feedback.record.v1`(遥测 FEEDBACK_ONLY 门控)。
3. **操作面**：`SessionStore.fork` + `derive_messages` / `export_transcript`（纯 fold，无旁路 messages 缓存）。
4. **Token 计量**：`TokenUsageUnit` 投影 + `HeuristicTokenMeter` seam（观察面，非控制面）。
5. **Doctor/model-visible 读路径**：`fold_model_visible` 为唯一 SSOT；`<run_dir>/model_visible/` sidecar 读路径删除。

## 不做什么

- 不新建 `dsh_obs` 平行包；能力落在既有 Session / fold / projection / telemetry seam。
- 不实现 DSH 上传水位、session.vN 代际、迁移链（DSH 当前代码亦无）。
- 不一次性补齐 DSH 全 catalog 斜杠词表；LCA 保留 `.v1` 命名，语义对齐即可。

## 验证

- `tests/observability/session/test_known_types_fail_closed.py`
- `tests/plugins/session/test_messages_and_fork.py`
- `tests/plugins/session/test_telemetry_feedback_gate.py`
- `tests/plugins/session/test_token_usage.py`
- `tests/scenarios/test_recording_loop.py`
- `tests/transport/test_doctor_fold_sidecar.py`
