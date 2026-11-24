# Agent Note: 文件服务上传接缝（POST /files）

Status: proposed

## Problem

Mangli 企业集成场景下，用户需要把本地文件交给 agent 使用，但当前没有可用的入口。

三件事同时成立：

1. 前端不能直接对接公司文件服务。文件服务用 `appId` + `pwd` 做授权（`http://10.36.0.185:9094`），凭据只允许存在于服务端，浏览器不能持有。
2. 文件服务落盘后只返回**授权链接**才可读，而授权链接有效期 1 小时；原链接（`source`）不带凭据，长期有效但不能直接访问。
3. LCA 现有的文件入口只认"已经可达的 URL"：`GET /files/{attachment_id}` 是下载，`/api/device/files/upload` 是往配对设备写盘，`POST /runs` 的 `files[]` 只做 URL 拉取（`FileRef.url`）。没有任何一个能承接"浏览器上传的字节"。

结果是：用户拿不到把本地文件交给 agent 的路径，只能依赖外部 LobeHub 先把文件放到对象存储再给 URL。

## 部署形态

一条后端、两条前端编排路径：

```
LobeHub（内部测试前端） ──┐
                          ├──> 同一个 LCA 后端 ──> 文件服务 ──> OSS
公司统一 gateway ─────────┘        （单一 profile）
        ↑
   公司前端（自行编排接口调用）
```

LCA 不感知调用方是哪个前端，只按请求契约工作；身份与租户归属都由现有中间件的双轨鉴权给出（网关密文或本地 Bearer），不新增第二套鉴权。

接口按归属分三类：

| 类别 | 例子 | 变化 |
|---|---|---|
| LobeHub 已依赖 | `POST /runs`、`WS /v1/runs/{id}/ws`、`GET /files/{id}`、`/files/{id}/meta`、`/v1/*` | **冻结**，请求与响应都不变 |
| 新增（加法） | `POST /files`（多文件上传） | 新增方法与路由，不与既有方法冲突 |
| 共享消费 | `files[]` 的 `/files/{id}` 引用、attachment_ids、沙箱 staging | 只被新入口产生的新引用使用，行为不变 |

## Proposal

新增一个上传入口 `POST /files`，采用**上传即落地**（eager）语义：浏览器字节在 LCA 侧被持久化为 FileStore 的 `attachment_id`，文件服务只作为归档副本。

请求：

```
POST /files                     multipart/form-data
files=@a.log
files=@b.txt                    ← 同名字段重复，支持多文件
```

处理顺序（单请求内 all-or-nothing）：

1. 解析 multipart，逐文件检查单文件 ≤ 100MB（`MAX_INGEST_FILE_BYTES`）、单请求 ≤ 50 个（`SANDBOX_INIT_MAX_FILES`）。
2. 用 `validate_file_integrity` 复核声明 MIME 与 magic bytes；HTML 兜底页按既有规则处理。
3. **一次**调用文件服务 `POST /upload?appId=&pwd=&needView=0`，multipart 重复字段 `files`。
4. 严格校验响应：`code == "200"`、`data.files` 是字符串数组、长度等于本次上传数；任一不符即失败。
5. 逐文件 `store.put(data=bytes, name=原始文件名, mime_type=..., origin="upload", source_url=<返回的 source>)`。
6. 按原始顺序返回结果数组。

不做内容去重：`FileStore` 与 `FileIndexRegistry` 都没有 content hash 列，按内容去重需要扫全部 `meta.json` 或新增哈希索引，超出本变更范围。每次上传产生新 `attachment_id` 与新远端对象，重复提交不会产生错误语义，只多一个附件与一个 OSS 对象。

响应：

```json
{
  "files": [
    {"attachment_id": "file_ab12", "url": "/files/file_ab12", "name": "2.log",
     "size_bytes": 1234, "mime_type": "text/plain",
     "source": "https://kltb-common.oss-cn-shenzhen.aliyuncs.com/test/2026/11/18/20261118164531_2.log"}
  ]
}
```

运行期不再依赖文件服务：前端在 `POST /runs` 里用 `files: [{"url": "/files/file_ab12", "name": "2.log"}]`，命中 `try_resolve_local_file` 的本地分支，不发起任何网络请求。

### 文件服务契约（已对齐）

| 项 | 值 |
|---|---|
| 上传 | `POST http://10.36.0.185:9094/upload?appId=<key>&pwd=<secret>&needView=0`，multipart 重复字段 `files` |
| 上传响应（needView=0） | `{"code":"200","msg":"成功","data":{"files":["<source>", ...]}}` —— **字符串数组** |
| 上传响应（needView=1） | `data.files` 变成 `[{"valid":..., "source":...}]` —— **对象数组**，LCA 不使用 |
| 授权 | `GET http://10.36.0.185:9094/url?appId=&pwd=&url=<source>`，返回授权后的链接 |
| `code` 类型 | **字符串** `"200"`，不是整数 |

`needView` 让同一个字段承载两种类型，这是本契约的已知隐患。LCA 的处理是：**只调 `needView=0`**，DTO 按字符串数组严格校验，拿到对象即 `fileservice_contract_violation`，不做兼容猜测。需要可分享链接时调 `/url` 现取现用，不引入 `needView=1`。

### 事实与投影

| 内容 | 类别 | 归属 |
|---|---|---|
| 上传的原始字节 | 运行期事实 | `FileStore`（`workspace/user/` + `{attachment_id}` 镜像） |
| `source`（OSS 原链接） | 事实（长期、无签名） | `StoredFile.source_url` |
| `valid`（授权链接） | 投影（1 小时过期、可重建） | 不落库、不跨请求缓存 |
| `/files/{id}` 下载 URL | 投影 | 由 `attachment_id` 派生 |

`valid` 里含 `OSSAccessKeyId` 与 `Signature`，落库等于把可下载凭据写进磁盘，因此永不持久化。

### 失败语义

| 情况 | 返回 | 本地副作用 |
|---|---|---|
| 文件服务不可达 / 超时 | `502 fileservice_unavailable` | 无（不回滚已存在的 attachment） |
| 上游 `code != "200"` | `502 fileservice_error` + 透传上游 `code`/`msg` | 无 |
| `data.files` 形态或数量不符 | `502 fileservice_contract_violation` | 无 |
| 单文件超限 / magic bytes 不符 | `400 invalid_file` | 无 |
| 单请求超数量 | `400 too_many_files` | 无 |

整请求失败即不写任何本地文件，避免"远端有副本、本地没有"或反之的半截状态。

### 配置

凭据经 serving profile 的 `patch:` 段以 `{from_env: ...}` 注入，插件不直读 `os.environ`：

```yaml
patch:
  - id: lca-gateway-routes-company-files
    config:
      base_url: {from_env: LCA_FILESERVICE_BASE_URL, required: false}
      app_id: {from_env: LCA_FILESERVICE_APP_ID, required: false}
      pwd: {from_env: LCA_FILESERVICE_PWD, required: false}
```

`required` 必须为 false：plugin 挂在公共 bundle 上，若声明为必需，所有不含凭据的 profile 会在启动期失败。缺配置时路由仍注册，请求返回 `503 fileservice_unconfigured`。

所有日志对 query 脱敏，`pwd` 不进入任何日志或持久化字段；`pwd` 是不透明字符串（非 MD5 派生），原样透传、不做任何转换。

## Alternatives considered

**让前端直连文件服务。** 前端拿 `valid` 后直接塞进 `POST /runs` 的 `files[]`，后端零改动。否决原因：`appId`/`pwd` 必须下发到浏览器，等于把文件服务的授权能力交给任何能打开控制台的人；而且 `valid` 只有 1 小时，跨小时恢复的会话会静默丢文件。代价是省下一个路由和一次本地副本，换来的是一整套前端凭据管理和过期兜底。

**只登记不落地（lazy）。** 上传时只保存 `source`，run 时再调 `/url` 换签下载。好处是 LCA 不占磁盘。否决原因：把 1 小时有效期引入运行期，每次 run 和每次 HIL 恢复都依赖文件服务在线且凭据有效，还要处理 403 与过期的区分、重试、时钟偏移。代价是把一个上传接口的问题扩散成一条运行期外部依赖链。

**复用 `/api/device/files/upload`。** 已有同名语义的 POST 路由。否决原因：它调用配对设备的 `writeFiles` 工具，把文件写到那台机器的磁盘，既不进 FileStore 也不产生 attachment，与需求无关。

**`needView=1` 拿 `valid` 再回下载。** 想让"远端副本可用"被验证。否决原因：原始字节在浏览器 → LCA 时就已持有，回下载是纯冗余传输；而且会让 `valid` 进入代码路径和持久化视野，破坏"投影不落库"的划分。

**什么都不做（baseline）。** 由调用方保证文件已在对象存储并给 URL。这是当前事实状态，也是 LobeHub 的既有路径。否决原因：Mangli 场景没有 LobeHub 前置，前端也没有直连对象存储的凭据，用户实际上无法交付文件。

## 零触碰约束

LobeHub 是内部测试前端，已在用这套网关；公司统一 gateway 是新增的第二条前端编排路径。两者最终由同一个 LCA 后端处理，因此本变更的硬约束是：

**LobeHub 依赖的任何接口，其请求契约与响应字节都必须保持不变。**

为此采用三条结构性做法，而不是"小心一点"：

1. **新增独立 plugin，不改共享 plugin。** 新路由放进新的 `lca-gateway-routes-company-files`，`routes_openai_compat_files.py` 保持字节不变。这样现有断言（路由 6 个、effects 6 个）零改动通过，反向证明 LobeHub 的路由面没有被碰。
2. **`/files/{id}/meta` 响应不变。** 该 handler 是显式字段字典（不是 `asdict`），因此 `StoredFile.source_url` 只是内部字段，不会泄漏到 HTTP 响应。
3. **`effects="network"` 只落在新 plugin 上**，共享 plugin 继续声明 `none`。

被冻结的契约面：

| 接口 | 状态 |
|---|---|
| `POST /runs`（含 `files[]` 的 URL ingest） | 冻结 |
| `WS /v1/runs/{id}/ws`（auth → resume → agent_event） | 冻结 |
| `GET /files/{id}` | 冻结 |
| `GET /files/{id}/meta` 响应字段 | 冻结（不新增键） |
| `/v1/*` OpenAI 兼容面 | 冻结 |

### 路由按 path 分流，不做来源隔离

两个 plugin 同时存在于同一 profile，各自注册不同的路径：

| plugin | 路径 | 语义 |
|---|---|---|
| `lca-gateway-routes-openai-compat-files`（既有） | `/files/{attachment_id}`、`/files/{attachment_id}/meta`、`/v1/models`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` | 读 |
| `lca-gateway-routes-company-files`（新增） | `/files`（`POST`、`OPTIONS`） | 写 |

分流依据是 **HTTP 路径**，不是调用来源。注册表以 path 为键，重复路径在 boot 阶段直接 `ValueError`（`router.py:112-113`），因此两条路径不重叠是装配可启动的前提。

LobeHub 与公司 gateway 的差异只体现在鉴权中间件（`X-Mangli-User` 密文 vs `Authorization: Bearer`），解完身份后汇入同一张路由表。**拆分 plugin 带来的是能力分离与准确的 effects 声明，不构成来源隔离**；若将来需要限制"只有网关来源可上传"，应在中间件按路径授权，而不是用 plugin 拆分表达。

## Change surface

| 文件 | 类型 | 内容 |
|---|---|---|
| `lca/infrastructure/fileservice/client.py` | 新增 | `upload()` 薄客户端 + 响应 DTO + query 脱敏 |
| `lca/plugins/transport/webserver/handlers/files/upload.py` | 新增 | multipart 解析、校验、去重、编排 |
| `lca/plugins/transport/webserver/routes_company_files.py` | 新增 | `RouteSpec("/files", upload_file, ("POST","OPTIONS"))`，`effects="network"` |
| `lca/infrastructure/file/store.py` | 改（仅内部） | `StoredFile.source_url: str = ""`，`put()` 入参 + `meta.json` 往返；HTTP 响应不变 |
| `bundles/web-app.yaml` | 改 | 新 plugin 入列（三个候选 serving profile 的公共成员） |
| `lca/plugins/transport/webserver/static/mangli_playground.html` | 改 | 附件区（点击/拖拽）、`/files` 与 `/runs` 共用 `buildAuthHeaders()`、附件以 `files[]` 提交 |
| `profiles/mangli-enterprise.yaml` | 改 | `{from_env: ...}` 注入凭据 |
| `tests/plugins/transport/test_company_file_upload.py` | 新增 | 见验收 |
| `tests/lca_plugins/transport/webserver/test_openai_compat_files.py` | **不改** | 必须原样通过，作为"未触碰"的证据 |

`StoredFile` 是跨实现的数据契约，改它需要同 PR 闭环：全部实现、`meta.json` 读写、`/files/{id}/meta` 消费者确认、测试。默认空串保证旧记录可读；新键只写不读（不对外暴露）。

新 plugin 的 `network` effect 与既有 `bundles/session-runtime.yaml` 中的 `telemetry_otel` 重叠，`compile_effect_policy` 按去重集合投影，因此含 `session-runtime` 的 profile 的 `effect_policy` 不变；不含的最小 profile 会新增 `network`，需在落地时用 `plan compile` 前后 diff 确认。

## Acceptance criteria

- 上传单个文件返回 `attachment_id`；随后 `POST /runs` 携带 `files:[{"url":"/files/<id>","name":...}]`，运行期 `attachment_ids` 非空，且**不发起任何出站请求**（可用 monkeypatch 断言）。
- 同一请求内的多个文件只触发一次远端调用；重复提交同一文件产生新的 `attachment_id`（不去重是有意选择，见 Proposal）。
- 文件服务不可达时返回 `502 fileservice_unavailable`，且 `workspace/user/` 下没有新增文件。
- 构造 `data.files` 为对象数组的响应，返回 `502 fileservice_contract_violation`。
- `data.files` 数量与上传数不一致时同样 `502 fileservice_contract_violation`。
- 无 `X-Mangli-User` 且无合法 `Bearer` 时 `POST /files` 返回 401（鉴权中间件默认保护除 `/playground*`、`/health`、`/favicon.ico` 之外的所有路径）。
- 日志中不出现 `pwd` 明文。
- **LobeHub 零触碰**：`tests/lca_plugins/transport/webserver/test_openai_compat_files.py` 不做任何修改仍通过；`GET /files/{id}/meta` 响应键集合与本变更前逐字节一致；`routes_openai_compat_files.py` 的 diff 为空。

## Risks

- **两份副本的一致性。** 本地 FileStore 与远端 OSS 各自独立演进：本地软删除不影响远端，远端对象被清理也不会通知 LCA。当前以本地为准，`source` 仅作溯源与归档入口。
- **内存峰值。** 单文件 100MB 会在解析和转发时各驻留一份，并发上传会叠加。若后期出现大文件诉求，需要改成流式转发 + 临时文件，属于接缝重写而非参数调整。
- **顺序对应假设。** `data.files` 是纯字符串数组，只能按发送顺序映射回文件。数量校验能挡住结构性变化，但若服务端对同名同扩展名的两个文件换序，名字会错配且无法察觉。文件名仅用于展示，不影响字节正确性。
- **磁盘增长。** 本地副本没有 TTL 清理，`FileStore.delete` 只有软删除。需要在运维层面约定清理策略。
- **凭据在 query string。** 内网可达性被视为边界（已确认接受），但 `pwd` 仍需避免进入日志、异常堆栈与 APM 的 URL 采样。

## Delete-when

文件服务若支持前端直传（预签名 PUT 或直传凭证），`POST /files` 与 `FileServiceClient` 整体删除，前端回到"直传后带 URL"的模型；届时本 Note 的 `source`/`valid` 划分仍可复用于 ingest 侧。
