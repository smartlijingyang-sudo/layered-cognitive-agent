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
