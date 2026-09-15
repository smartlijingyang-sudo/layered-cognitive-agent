# plugins/observability — 观测链插件（fold / export）

Seam 树：**observability/** · 仅 deriver、exporter、sink、provider；**不写第二事实源**。

| 子组 | 职责 | Legacy |
|---|---|---|
| `deriver/<id>/` | Session → 投影 DTO | infra+plugins 双份 deriver |
| `exporter/<id>/` | OTel / Langfuse / SSE | `*_provider.py` 根目录 |
| `sink/<id>/` | 落盘 / S3 | `events/sinks/` |
| `provider/<seam>/<id>/` | seam 标准 provider | `plugins/observability/*_provider.py` |

**禁止新增** `events/publishers/spine_reflector_*`（→ FactGateway，ADR-0195 P2）。

Registry SSOT：`lca_kernel/events/config/`。
## 1. 职责

观测链插件：Session → 投影 deriver、OTel / Langfuse / SSE exporter、落盘与 S3
sink、以及各 seam 的标准 provider。事实源仍是 `Session`，本目录只派生与外发。

## 2. 不负责

- 写第二事实源（禁止新增 `events/publishers/spine_reflector_*`，改走 FactGateway，ADR-0195 P2）
- 事件词表与 catalog 定义（SSOT 在 `lca_kernel/events/config/`）
- 控制面决策与 State 单写

## 7. 副作用

| 家族 | 对外后果 |
|---|---|
| `sink/` | 写文件对象与远端存储（spine sink 落 `<run_id>.spine.jsonl`，S3 sink 上传） |
| `exporter/` | 外发到 OTel / Langfuse collector；带界队列的 exporter 在队列满时丢弃本批（`telemetry_otel` 的 `queue.Full` 分支），不回压事实写入 |
| `deriver/` | 纯派生：读 Session 事件产出投影 DTO，不写回事实（C4/C7） |
| `provider/` | 装配期向 capability registry 注册自己 |
