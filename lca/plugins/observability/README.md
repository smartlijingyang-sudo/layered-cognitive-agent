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

## 3. 输入

Session / spine 事件流（fold 输入）、OTel / Langfuse 的导出配置与凭据（经 profile
注入，不在插件内读 `os.environ`）、sink 目标（目录 / S3 前缀）。

## 4. 输出

投影 DTO（trace 树、span/attribute 映射、fact reader 视图）与导出副作用载体
（export batch、落盘对象）。事实不在本层产生：本层只派生与外发。

## 5. 允许依赖

`lca.contracts`、`lca.infrastructure`、`lca.harness`、`lca.plugins`、
`lca_kernel.events`，第三方 `opentelemetry.sdk` / `langfuse` / `ulid`。
（现状计数 278 / 73 / 63 / 12 / 2。）

## 6. 禁止依赖

`lca.agent`、`lca.application`、`lca.cognition`、`lca.loop`、`lca.runtime`、
`lca.session`、`lca.nodes`（当前零 import）。禁止新增第二事实源
（`events/publishers/spine_reflector_*` → 走 FactGateway）。

## 8. 失败语义

按源码 `raise` 统计：`ValueError` 2、`KeyError` 1、`_S3SinkNotImplementedError` 1
——薄得反常，因为绝大多数失败走 contained 路径：deriver / exporter 异常被记录并
跳过该批次，不回滚已 commit 的 append。未配置的 S3 sink 明确抛
`_S3SinkNotImplementedError`，不静默丢数据。

## 9. 公共入口

包门面不重导出符号（__all__ 为空）。按家族取用：`deriver/`（Session → 投影）、
`exporter/`（OTel / Langfuse / SSE）、`sink/`（落盘 / S3）、
`provider/<seam>/`（seam 标准 provider）。
