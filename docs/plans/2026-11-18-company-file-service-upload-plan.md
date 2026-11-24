# 公司文件服务上传接缝 —— 实施方案

配套决策记录：[2026-11-18-file-service-upload-seam](../notes/proposed/contract/2026-11-18-file-service-upload-seam.md)

## 0. 摘要

| 项 | 结论 |
|---|---|
| 新增 HTTP 接口 | `POST /files`（multipart，多文件） |
| 新增 plugin | `lca-gateway-routes-company-files`（1 条路由，`effects="network"`） |
| 既有 plugin | `lca-gateway-routes-openai-compat-files` **零改动** |
| 分流依据 | HTTP 路径，不区分调用来源 |
| 持久化新增 | `StoredFile.source_url`（仅内部，HTTP 响应不变） |
| 运行期外部依赖 | 仅上传时依赖文件服务；`POST /runs` 之后零依赖 |
| 内容去重 | **不做**（无现成 hash 索引，见 §6.4） |

## 1. 目标与非目标

**目标**

1. 前端（公司统一 gateway 暴露的接口）能把本地文件交给 agent，不需要前端持有文件服务凭据。
2. LobeHub 已在使用的接口，请求契约与响应字节都不变。
3. 文件的 1 小时授权有效期不进入运行期。

**非目标**

- 不做按来源的路径授权（网关轨可用、Bearer 轨不可用）——如需另立变更。
- 不直连 OSS；LCA 只对接文件服务。
- 不改变 `POST /runs` 现有的 URL ingest 路径。

## 2. 拓扑与分流

```
LobeHub ─────────┐
                 ├──> 同一个 LCA 后端 ──> 文件服务(10.36.0.185:9094) ──> OSS
公司统一 gateway ─┘
        ↑ 公司前端自行编排接口调用
```

| plugin | 注册路径 | 语义 |
|---|---|---|
| `lca-gateway-routes-openai-compat-files`（既有，冻结） | `/files/{attachment_id}`、`/files/{attachment_id}/meta`、`/v1/models`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` | 读 |
| `lca-gateway-routes-company-files`（新增） | `/files`（`POST`、`OPTIONS`） | 写 |

注册表以 path 为键、重复即 boot 失败（`lca/plugins/transport/webserver/router/router.py:112`），两条路径不重叠是装配可启动的前提。

`OPTIONS` 预检由 `register_routes` 统一处理，handler 不需要写 CORS 分支：

```213:215:lca/plugins/transport/webserver/route/register.py
            if method == "OPTIONS":
                # CORS 预检必须不经认证直接 2xx，否则浏览器跨域调用被拦。
                return JSONResponse({}, headers=cors_headers())
```

## 3. 对外契约：`POST /files`

请求：

```
POST /files
Content-Type: multipart/form-data
files=@a.log
files=@b.txt        ← 同名字段重复
```

响应 `200`：

```json
{
  "files": [
    {"attachment_id": "file_ab12cd34ef56", "url": "/files/file_ab12cd34ef56",
     "name": "2.log", "size_bytes": 1234, "mime_type": "text/plain",
     "source": "https://kltb-common.oss-cn-shenzhen.aliyuncs.com/test/2026/11/18/20261118164531_2.log"}
  ]
}
```

- 顺序与上传顺序一致。
- `url` 直接可用于 `POST /runs` 的 `files[].url`，命中 `try_resolve_local_file` 的本地分支。
- 多租户归属与既有上传一致：字节落 `workspace/user/`，镜像落 `{attachment_id}/{meta.json,blob}`。

## 4. 依赖契约：文件服务

| 项 | 值 |
|---|---|
| 上传 | `POST {base}/upload?appId=<key>&pwd=<secret>&needView=0`，multipart 重复字段 `files` |
| 响应（`needView=0`） | `{"code":"200","msg":"成功","data":{"files":["<source>", ...]}}` —— 字符串数组 |
| 响应（`needView=1`） | `data.files` 为 `[{"valid","source"}]` 对象数组；**LCA 不使用** |
| 授权 | `GET {base}/url?appId=&pwd=&url=<source>`；本期不实现，仅留接口位 |
| `code` 类型 | 字符串 `"200"` |

只走 `needView=0`：原始字节在浏览器 → LCA 时已持有，`valid` 无用。响应 DTO 按字符串数组严格校验，拿到对象数组即 `fileservice_contract_violation`。

## 5. 数据与持久化

| 内容 | 类别 | 落点 |
|---|---|---|
| 上传原始字节 | 运行期事实 | `workspace/user/<name>` + `{attachment_id}/blob` |
| `source`（OSS 原链接） | 事实（长期、无签名） | `StoredFile.source_url` → `meta.json` |
| `valid`（授权链接） | 投影（1h、可重建） | 不落库、不缓存 |
| `/files/{id}` | 投影 | 由 `attachment_id` 派生 |

`GET /files/{id}/meta` 是显式字段字典（`handlers/files/files.py:58-67`），`source_url` 只写不读，**响应键集合不变**。

## 6. 处理流程

单请求内 all-or-nothing：任一环节失败即整请求失败，且不留下半截本地文件。

1. `form = await request.form()`，`uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]`
2. 数量校验：`0 < len(uploads) <= SANDBOX_INIT_MAX_FILES(50)`
3. 逐文件读取字节，单文件 `<= MAX_INGEST_FILE_BYTES(100MB)`
4. 逐文件 MIME 校验：`declared = content_type or guess_type(name)`，`actual = sniff_mime(data)`，调 `validate_file_integrity`；HTML 兜底页按既有规则处理
5. 一次远端上传：`sources = await client.upload([(name, data, mime), ...])`
6. 严格校验响应（见 §4），长度必须等于本次上传数
7. 逐文件 `store.put(data=..., name=..., mime_type=..., origin="upload", source_url=sources[i])`
8. 按原顺序返回

### 6.4 关于内容去重（明确不做）

`FileStore` / `FileIndexRegistry` 都没有 content hash 列，`meta.json` 也没有哈希字段。要按内容去重只有两条路：扫全部 `meta.json`（O(n)）或新增 `content_hash` 列 + 索引。两者都超出本次变更范围。

因此第一版：**每次上传都产生新 `attachment_id` 与新远端对象**。重复提交的代价是多一个附件和一个 OSS 对象，不会产生错误语义。若日后重复率显著，再单独立项加 `content_hash`。

## 7. 文件级改动清单

### 7.1 新增 `lca/infrastructure/fileservice/client.py`

```python
@dataclass(frozen=True)
class UploadedSource:
    source: str

class FileServiceError(RuntimeError): ...
class FileServiceUnavailable(FileServiceError): ...      # 连不上 / 超时 → 502
class FileServiceContractViolation(FileServiceError): ... # 形态或数量不符 → 502

class FileServiceClient:
    def __init__(self, *, base_url: str, app_id: str, pwd: str, timeout_s: float = 120) -> None: ...
    async def upload(self, files: Sequence[tuple[str, bytes, str]]) -> list[str]:
        """POST {base}/upload?appId&pwd&needView=0；返回 data.files（字符串数组）。"""
```

约束：

- 只记录 `path` 与状态码，query 一律脱敏（`pwd` 不进日志、不进异常栈）。
- `code != "200"` → `FileServiceError`，异常消息带上游 `code`/`msg`。
- 用 `httpx.AsyncClient`，multipart 用重复字段名 `files`。

### 7.2 新增 `lca/plugins/transport/webserver/handlers/files/upload.py`

```python
async def upload_files(request: Request, client: FileServiceClient) -> JSONResponse:
    store = request.app.state.file_store
    ...
```

依赖复用：`sniff_mime` / `validate_file_integrity` 来自 `handlers/runs/ingest/fetcher.py`。同一 transport 层内复用，不复制实现；若日后第三方调用增多，再把这两个函数下沉到 `lca/infrastructure/file/integrity.py`。

### 7.3 新增 `lca/plugins/transport/webserver/routes_company_files.py`

```python
@plugin(
    id="lca-gateway-routes-company-files",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="network",
    description="Register POST /files (company file-service upload).",
    test_suite="tests.lca_plugins.transport.webserver.test_company_file_upload",
    contract=PluginContract(...),   # G9_INTERACTION，与既有 routes plugin 同构
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_company_files_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    client = build_client(config)   # 闭包捕获，不新增 capability
    specs = (RouteSpec("/files", make_handler(client), ("POST", "OPTIONS")),)
    register_routes(registry, ctx, specs, plugin_id="lca-gateway-routes-company-files")
```

### 7.4 修改 `lca/infrastructure/file/store.py`（仅内部）

- `StoredFile.source_url: str = ""`
- `FileStore.put(..., source_url: str = "")`
- `LocalFileStore.put` 写入 `meta.json`；`get` 用 `meta.get("source_url", "")` 读取，旧记录兼容
- **不改** `handlers/files/files.py` 的响应字典

### 7.5 装配

在 `bundles/web-app.yaml` 增加一条 plugin 条目。该 bundle 是 `web-standard`、`web-assistant`、`mangli-enterprise` 三个候选 serving profile 的公共成员，一处登记即可覆盖全部装配形态；放到 `bundles/mangli-enterprise.yaml` 反而不覆盖 `web-assistant`。

凭据经 serving profile 的 `patch:` 段注入（与 `composio-enabled.yaml` 同一写法）：

```yaml
patch:
  - id: lca-gateway-routes-company-files
    config:
      base_url: {from_env: LCA_FILESERVICE_BASE_URL, required: false}
      app_id: {from_env: LCA_FILESERVICE_APP_ID, required: false}
      pwd: {from_env: LCA_FILESERVICE_PWD, required: false}
      timeout_s: {from_env: LCA_FILESERVICE_TIMEOUT_S, required: false}
```

**必须 `required: false`。** plugin 挂在公共 bundle 上，用 `required: true` 会让所有不含凭据的 profile（`web-standard`、测试 profile）启动直接失败。缺配置时的行为是：路由照常注册，请求返回 `503 fileservice_unconfigured` —— 显式失败，而不是启动期崩溃或运行期 500。只有真正要提供上传能力的 profile 才需要这段 patch。

### 7.6 新增测试 `tests/lca_plugins/transport/webserver/test_company_file_upload.py`

见 §10。

### 7.7 修改 `lca/plugins/transport/webserver/static/mangli_playground.html`

后端接缝没有消费者时，用户在控制台上仍然无处可操作。页面需要三个改动：

- 附件区（点击选择 + 拖拽）：选中即 `POST /files`，`FormData` 用重复字段名 `files`；失败按后端 `code` 显示（`fileservice_unconfigured` 提示缺 `LCA_FILESERVICE_*`，其余透传消息）。
- 鉴权头抽成 `buildAuthHeaders()`，`/files` 与 `/runs` 共用同一份双轨逻辑，避免"页面能打开、上传 401"。
- 附件以 `messages[0].files = [{url: "/files/<id>", name, mime_type, size}]` 提交，命中 `try_resolve_local_file` 的本地分支，运行期零出站请求。

上传在途时禁止发起任务，避免漏带附件。回归用例见 `tests/plugins/transport/test_mangli_playground.py::test_playground_supports_file_upload`。

## 8. 错误矩阵

| 情况 | 状态码 | code | 本地副作用 |
|---|---|---|---|
| 未带 `files` 字段 | 400 | `missing_files` | 无 |
| 文件数超 50 | 400 | `too_many_files` | 无 |
| 单文件超 100MB | 400 | `file_too_large` | 无 |
| MIME/magic 不符 | 400 | `invalid_file` | 无 |
| 凭据未配置（serving profile 无 patch） | 503 | `fileservice_unconfigured` | 无 |
| 文件服务连不上/超时 | 502 | `fileservice_unavailable` | 无 |
| 上游 `code != "200"` | 502 | `fileservice_error` | 无 |
| 形态或数量不符 | 502 | `fileservice_contract_violation` | 无 |
| 本地落盘失败 | 500 | `store_write_failed` | 已写部分不删除（见风险） |

## 9. 鉴权与多租户

- 鉴权中间件默认保护除 `/playground*`、`/health`、`/favicon.ico` 之外的全部路径，`POST /files` 自动落在双轨之内：网关密文 `X-Mangli-User` 或本地 `Authorization: Bearer`。
- 不新增鉴权机制，不做来源隔离。
- 多租户归属沿用 `_assistant_home_of` / `assistant_workspace_root` 的既有规则；`store.put` 写 `workspace/user/`，与 LobeHub 附件同一归属口径。

## 10. 测试计划

| # | 用例 | 断言 |
|---|---|---|
| 1 | 单文件上传 | 200；remote 被调用 1 次；query 含 `needView=0`；multipart 字段名 `files` |
| 2 | 多文件上传 | 返回顺序与上传顺序一致，长度相等 |
| 3 | 远端 500 / 超时 | 502 `fileservice_unavailable`；`workspace/user/` 无新增文件 |
| 4 | 远端 `code="500"` | 502 `fileservice_error`，消息含上游 code |
| 5 | `data.files` 为对象数组 | 502 `fileservice_contract_violation` |
| 6 | `data.files` 数量不符 | 502 `fileservice_contract_violation` |
| 7 | 超 50 个 / 超 100MB | 400，未调用远端 |
| 8 | 无鉴权 | 401 |
| 9 | 上传后 `POST /runs` 用 `/files/{id}` | `attachment_ids` 非空，且运行期零出站请求 |
| 10 | `GET /files/{id}/meta` 回归 | 键集合与变更前逐字节一致 |
| 11 | LobeHub 路由冻结 | `test_openai_compat_files.py` 不修改仍通过 |

命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/lca_plugins/transport/webserver/test_company_file_upload.py -q
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/lca_plugins/transport/webserver/test_openai_compat_files.py -q
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/plugins/transport -q
```

## 11. 落地顺序

| 步 | 内容 | 可独立验证 |
|---|---|---|
| 1 | `FileServiceClient` + DTO + 脱敏 + 单测（httpx mock） | 两种响应形态、错误映射 |
| 2 | `StoredFile.source_url` + `put()` + `meta.json` 往返 | 旧记录可读；`/meta` 响应不变 |
| 3 | `upload.py` handler + 路由 plugin + 装配 | 用例 1–8 |
| 4 | profile 注入凭据 | 真实文件服务连通性 |
| 5 | 端到端：上传 → `/runs` 引用 → agent 读到文件 | 用例 9 |

## 12. 门禁

```powershell
.\.venv\Scripts\python.exe -X utf8 -m ruff check lca/plugins/transport/webserver lca/infrastructure/fileservice
.\.venv\Scripts\python.exe -X utf8 -m ruff format --check <changed files>
.\.venv\Scripts\python.exe -X utf8 -m lca.infrastructure.cli.cli plan compile profiles/web-assistant.yaml
.\.venv\Scripts\python.exe -X utf8 -m lca.infrastructure.cli.cli plan compile profiles/mangli-enterprise.yaml
.\.venv\Scripts\python.exe -X utf8 -m lca.infrastructure.cli.cli audit-plugin-shape
```

`plan compile` 前后各跑一次，diff `effect_policy`：只允许出现新增路由条目；`allowed_effects` / `approval_required` 不应因新增 `network` 而实际变化（`bundles/session-runtime.yaml` 的 `telemetry_otel` 已声明 `network`）。

## 13. 风险与 delete-when

| 风险 | 说明 | 缓解 |
|---|---|---|
| 双副本一致性 | 本地 FileStore 与 OSS 独立演进，软删除互不通知 | 以本地为准，`source` 仅溯源 |
| 内存峰值 | 单文件 100MB 在解析与转发各驻留一份 | 并发取决于调用方；需要更大文件时改流式 |
| 顺序对应 | `data.files` 是纯字符串数组，只能按顺序映射 | 数量校验挡结构性变化；同名同扩展名换序无法察觉 |
| 磁盘增长 | 本地副本无 TTL 清理 | 运维约定清理策略 |
| 落盘半途失败 | 多文件时 `put` 可能部分成功 | 返回 500 并记录已写入的 attachment_id，由调用方重试 |

**Delete-when**：文件服务支持前端直传（预签名 PUT）后，`POST /files` 与 `FileServiceClient` 整体删除，前端回到"直传后带 URL"模型。

## 14. 待确认

1. **生产凭据**：`appId` / `pwd` 的正式值与测试值不同，必须由部署环境注入，不得写入仓库、`.env` 示例或文档。轮换后需要重启进程（当前没有配置热加载）。
2. **启动口径一致性**：`lca-ops.yaml` 的 `kernel_serve.profile` 是 `profiles/web-assistant.yaml`，而 mangli 联调的启动命令用的是 `profiles/mangli-enterprise.yaml`。新 plugin 挂在 `bundles/web-app.yaml`，两者都会加载；但仍需确认运维侧实际跑的是哪一个，避免"代码在、接口 404"。
3. **`pwd` 是不透明字符串**（不是 MD5 派生）：原样透传到 query，不做任何转换或哈希。
