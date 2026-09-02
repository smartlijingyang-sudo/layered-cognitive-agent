# ADR-0121: 附件 FileRef SSOT 与单一 AttachmentPlane Provider

- Status: Accepted (2026-08-31)
- Supersedes: 无
- Decision: 把"用户上传文件 → system prompt / tool dispatch / 下载 URL"三条链路统一到 `FileRef` SSOT,所有渲染、拦截、staging 由一个 `lca-attachment-default` plugin + 三个独立 Seam(Resolver / Stager / PromptRenderer)+ 一个 `SandboxBackend` 协议共同驱动。彻底关闭 2026-08-31 `run_75e88a76899b` 失效模式(reasoner cloud branch 因 `store is None` 丢 `<uploaded_files>` 注入)。

## Context

### 触发事件
- 2026-08-31 用户上传 `Clash_1752915628.yaml` 并问"这是什么文件"。
- `run_75e88a76899b` journal 显示:
  - `InboxFollowupCreated` 写入 user message 含 `<files_info>` identity-only 块(`<file url="/files/file_468d86e65e72">`)。
  - `AgentRunStarted` objective 同样不含 `<uploaded_files>`。
  - `_cloud_sandbox_block` 走 cloud 分支时 `store is not None` 不满足,**整段 system role 不渲染**;机器分支只输出"用电脑"段落。
  - 模型把 `/files/<aid>` 当文件系统路径丢给 `readFile` → Onlyboxes 沙箱 `Path("/files/file_...").is_file()` 报 `not a file: /files/file_468d86e65e72`。
  - 之后两条 `bash find / ...` 都 30s 超时;doctor H7 工具成功率 0%,run 被标 `canceled`。

### 根因
1. **`build_cloud_sandbox_prompt(tools, store)` 收不到 store**:`lca/cognition/brain/reasoner.py:219` 的 `_cloud_sandbox_block` 调用 `build_cloud_sandbox_prompt(tools)` 不传 `store=`,而 `build_cloud_sandbox_prompt` 内 `if any(name in cloud_values for name in names) and store is not None:` 把整段 cloud branch 丢了。
2. **多个 renderer 散落 5 个文件**:`format_machine_uploaded_files_prompt`(attachment/prompt.py)、`format_sandbox_uploaded_files_prompt`(attachment/prompt.py)、`format_skill_attachment_block`(attachment/prompt.py)、`machine_uploaded_files_for_ambient`(attachment/prompt.py)、`render_cloud_sandbox_system_role`(sandbox/prompt.py)、`plane_system_role`(sandbox/surface.py)。每个都分别决定"现在该渲 `<uploaded_files>` 还是该渲 `<files_info>`",任一分支条件变化就回归。
3. **历史 wrapper 三层**:sandbox.prompt 的 `format_machine_uploaded_files_prompt` → attachment.prompt 的 `machine_uploaded_files_for_ambient` → attachment.prompt 的 `format_machine_uploaded_files_prompt`,同一件事三份代码。
4. **tool dispatch 不拦截**:模型传给 `readFile` 的 `/files/<aid>` 字符串直送沙箱,沙箱 `is_file()` 误报,没有 host 端拦截 + 重写。
5. **skill preamble 重复注入**:`format_skill_attachment_block` 和 `render_cloud_sandbox_system_role` 都各自填 `sandbox_policy_text`,用户激活 skill 时重复出现。

### 用户决定
- 不改 lobehub 前端(`<file url>` 字段保留,patch `file_list_gateway_preview` 不变)。
- 走插件化思路:Protocol → Seam → Provider → Adapter → Plugin,职责单一。
- 沙箱可替换(Onlyboxes 之外可接 e2b / docker / ssh / 内存 stub)。
- 一次性清理历史垃圾:11 项死代码 / 重复 / 纯别名。
- 每条 PR 必带测试;trace 回归写专门测试做永久门禁。

## Decision

### 1. 新增 SSOT: `FileRef`

`lca/contracts/models/core/file_ref.py`:

```text
@dataclass(frozen=True)
class FileRef:
    kind: FileRefKind                     # 'user_upload' | 'sandbox_init' | 'inbox_staged'
                                          # | 'generated' | 'workspace' | 'external_url'
    target_key: str                       # stable identity (opaque, do not parse)
    display_path: str                     # what humans / LLM see
    process_path: str                     # current plane's executable path
    file_url: str                         # file: URI for cross-plane refs
    mime_type: str
    size_bytes: int
    source: FileRefSource                 # 'lobehub_upload' | 'sandbox_bootstrap' | ...
    attachment_id: str | None
```

任何下游(系统 prompt、tool 参数、Journal 记录)只能持有 `FileRef`;**禁止裸路径字符串、文件名、下载 URL 再被直接传**。

### 2. 三个独立 Seam

`lca/contracts/protocols/runtime/attachment.py`:

- `AttachmentResolver(Protocol)` — `resolve(ids) -> ResolvedAttachment[]`、`resolve_for_plane(ref, plane) -> FileRef`
- `AttachmentStager(Protocol)` — `stage_to_machine(run_id, refs)`、`stage_to_sandbox(sandbox_id, refs)`
- `AttachmentPromptRenderer(Protocol)` — `identity_block(refs)`、`guest_path_block(refs, plane)`、`inline_content_block(refs)`

加上沙箱后端 seam(独立文件):

`lca/contracts/protocols/runtime/sandbox_backend.py`:

- `SandboxBackend(Protocol)` — `mount_root()`、`ensure_mounts(manifest, timeout)`、`translate_ref(ref)`、`read_bytes(process_path)`、`list_files(directory)`

### 3. 默认 Provider: `lca-attachment-default`

`lca/infrastructure/attachment/default_provider.py` 内三实现一个文件:

- `DefaultAttachmentResolver` — 读 FileStore → FileRef;`resolve_for_plane` 单一源翻译 display_path → process_path。
- `DefaultAttachmentStager` — 把散落在 `stage_payload` / `build_mount_manifest` / `machine_harvest` 里的 stage 逻辑收敛到一处;`build_manifest` 复用同一份数据。
- `DefaultAttachmentPromptRenderer` — 渲染三个块,policy 前缀只出现一次,inline content guard 一次过。

### 4. 单一 System Role Renderer

`lca/infrastructure/attachment/system_role_renderer.py::render_system_role(plane, *, template_name, store, extra_placeholders) -> SystemRoleResult`:

- 单调读模板,单遍替换 `{{attachment_policy}}` / `{{uploaded_files}}` / `{{sandbox_uploaded_files}}` / `{{sandbox_environment_note}}` / `{{sandbox_workspace_root}}` / `{{sandbox_outputs_dir}}`。
- FileStore 从 ambient `run_file_store_scope` 取,reasoner 不再需要传 `store=`。
- `build_cloud_sandbox_prompt` 改为:`store is None` → 走 ambient;`store is not None` → 显式覆盖。
- 任一 future placeholder 不替换时,这一处漏出;系统 prompt 其它路径不再覆盖。

### 5. Tool Dispatch 拦截

`lca/infrastructure/tools/seam/file_ref_args.py::resolve_path_arg(raw, *, allowed_refs) -> ResolvedPathArg`:

- `/files/<aid>` → attachment_store.lookup → FileRef(workspace path)。
- `http(s)://...` → 临时 FileRef;sandbox curl 时再 fetch。
- 其它 → pass-through,`kind=workspace`。
- `UnresolvedFileRefError` / `AmbiguousFileRefError` 带 `context` 字典,Journal 可直接记录。

`SandboxComputer.read_file` 在 `normalize_sandbox_path` 之前调 `resolve_path_arg`,把 `/files/<aid>` 转 `display_path` 再下发。

### 6. 错误码闭集

`lca/contracts/protocols/runtime/attachment_errors.py`:

```text
class AttachmentErrorCode(str, Enum):
    UNRESOLVED_REF
    AMBIGUOUS_REF
    MISSING_ATTACHMENT
    POLICY_REJECTED
    STAGE_FAILED
    RENDERER_NOT_REGISTERED
    SANDBOX_BACKEND_UNAVAILABLE
```

`AttachmentError(RuntimeError)` 携带 `code: AttachmentErrorCode` + `context: dict[str, object]`;`UnresolvedFileRefError` / `AmbiguousFileRefError` 派生。

## 死代码清理清单(ADR-0121 §3)

| 类型 | 位置 | 处理 |
|---|---|---|
| 死函数 | `lca/infrastructure/workspace/deliverable.py::is_immediate_product_name` | 删(0 caller);同步删 `_IMMEDIATE_SUFFIXES` |
| 死类 | `lca/infrastructure/attachment/normalizer.py::TextNormalizationService` | 改纯函数 `normalize_for_injection` + `TextNormalizationRules` dataclass |
| 死 Protocol 方法 | `AttachmentIdentity.listed_paths` | 删;`FileStoreAttachmentIdentity.listed_paths` 同步删 |
| 1 行 wrapper | `sandbox/prompt.py::format_uploaded_files_prompt` | 删;更新 `test_sandbox_bootstrap.py` 用 SSOT |
| 1 行 wrapper | `sandbox/prompt.py::format_machine_uploaded_files_prompt` | 删;caller 已并入 renderer |
| 重复实现 | `format_skill_attachment_block` 二次注入 policy | 收敛到 `DefaultAttachmentPromptRenderer` |
| 多 Provider | `lca/plugins/seams/memory/attachment.py` Registry 模式 | 保留单例 provider,待 plugin loader PR 后续清理 |
| 多观察器 | `lca/infrastructure/tools/sandbox_observation.py` + `sandbox_exec_observation.py` + `lca_computer/observations.py` 三份并存 | 保留 `lca_computer/observations.py`,其它两份继续被生产代码使用,不破兼容 |

## 不变量

1. **路径 SSOT 闭集**:所有 prompt 渲染、tool dispatch、Journal 引用只能走 `FileRef` 或 `FileRef.process_path`。不允许裸路径字符串再跨层。
2. **C1 插件闭集**:改变 `FileRefKind` / `FileRefSource` / `AttachmentErrorCode` 必须先有 ADR;新加 plugin 必须先有 ADR。
3. **C2 双平面**:Renderer 不直接发副作用,Stager 不读模型输出,Resolver 不读 FileStore 之外的源。
4. **C3 Journal**:每次 staging / rendering 都通过 `RuntimeObserved` 记录 `label`(provider 标识),便于 debug 替代。
5. **C6 最小化**:Provider 默认实现只在 `default_provider.py`;插件骨架暂留 stub,实际 plugin loader 由后续 PR 落地。
6. **占位符替换闭集**:`{{attachment_policy}}` / `{{uploaded_files}}` / `{{sandbox_uploaded_files}}` / `{{sandbox_environment_note}}` / `{{sandbox_workspace_root}}` / `{{sandbox_outputs_dir}}` 只能由 `render_system_role` 替换。

## Consequences

### 正向
- 关闭 trace `run_75e88a76899b` 失效模式:`build_cloud_sandbox_prompt` 不再因 `store is None` 丢 cloud branch;`render_system_role` 单点替换所有占位符。
- 任何未来加的 attachment 相关功能(脱敏、版本化、加密、对象存储后端)只需替换 `lca-attachment-default` plugin,不影响调用方。
- 沙箱后端可替换:Onlyboxes / e2b / docker / ssh / 测试 stub 各自实现 `SandboxBackend`,挂载逻辑不再硬编码到 `runtime_mount.py`。
- `resolve_path_arg` 把"模型把 URL 当路径"的失败模式从"沙箱报怪错"升级到"host 拦截 + 重写 + Journal 留痕";未来类似 bug 直接出现在 journal 而非 reasoner 走错路。

### 风险与缓解
| 风险 | 缓解 |
|---|---|
| `DefaultAttachmentPromptRenderer` 把 policy 渲染到 system role,skill preamble 不再二次注入;行为变更 | 单测覆盖:`tests/lca/infrastructure/attachment/test_default_provider.py::TestDefaultRenderer` 显式断言 guest_path_block 形态;`tests/contracts/test_attachment_seams.py` 守住 Protocol 不变 |
| `run_file_store_scope` 必须由 CreateRun handler bind,漏绑定则 ambient None | `execute.py:336` 的 `with (...)` 块已经绑;`lca_kernel/run_kernel_lifespan` 的 entry point 也需要绑(后续 kernel 集成 PR) |
| `resolve_path_arg` 拦截所有 `/files/<aid>`,某些 lobehub 自定义 plugin 也用同前缀会误判 | 正则只匹配 `^/files/<id>/?$`,不会误判 `/files/<id>/<extra>` |
| 沙箱后端可替换后,e2b 后端实现需要重写 `translate_ref` / `ensure_mounts` 等 | Protocol 已收敛;`SandboxBackend` 5 方法单测覆盖在 `tests/contracts/test_attachment_seams.py::TestSandboxBackendContract` |

### 兼容策略
- `FileStoreAttachmentIdentity` 保留,user message `<files_info>` 注入仍走它(避免影响 lobehub `<file url>` 契约)。
- 旧的 `format_*` 函数在 `attachment/prompt.py` 保留(生产 caller 多),后续 PR 单独收敛。
- `attachment/__init__.py` re-export 列表保持兼容。

## 借鉴来源

- **deepseek-harness 的 `FileSystem` provider**:把"路径"换成 `FsTarget`(stable identity + processPath + fileUrl)而不是裸字符串。本 ADR 把这一抽象简化为 LCA 需要的子集(`FileRef` 不暴露 `targetKey` brand,但提供 `kind` + `source` 让 Journal / debug 替代)。
- **deepseek 的 `SandboxBackend` 协议边界**:`resolve`/`processPath`/`fileUrl` 翻译由后端集中完成,prompt 不出现 processPath。LCA 反过来:prompt 仍带 guest path(LLM 直接读),但 tool dispatch 走 host 拦截。

## 验证矩阵

| 改动 | 验证 |
|---|---|
| 新增 `FileRef` + 三 Protocol + `SandboxBackend` + `AttachmentErrorCode` | `ruff check + mypy` 全绿;`tests/contracts/test_attachment_seams.py` 15 项 |
| 默认 provider + 单一 system role renderer | `tests/lca/infrastructure/attachment/test_default_provider.py` 10 项;`tests/lca/cognition/brain/test_reasoner_cloud_branch_renders_uploaded_files.py` 1 项(trace 回归门禁) |
| `resolve_path_arg` 拦截 | `tests/lca/infrastructure/tools/seam/test_file_ref_args.py` 8 项 |
| 死代码清理 | `uv run vulture lca/infrastructure/attachment lca/infrastructure/tools/seam lca/contracts/models/core/file_ref.py lca/contracts/protocols/runtime/attachment.py lca/contracts/protocols/runtime/attachment_errors.py lca/contracts/protocols/runtime/sandbox_backend.py lca/cognition/brain/sandbox_prompt.py --min-confidence 80` 0 输出 |
| 全量 gate | `lint-imports` + `mypy lca` + `pytest` + importlinter `kernel-domain-isolation` & `transport-isolation` + `scripts/check_kernel_boundary.py` |
| 端到端 | daemon 重启后 `lca-ops journal logs -r <run_id>`,用户上传附件 + 问"这是什么文件"必须看到 `<uploaded_files>` 注入 + `readFile` 命中 `/mnt/data/<name>` |

## 后续 PR(不在本 ADR 范围)

- **PR-F**: `lca-attachment-default` 真正注册为 plugin(`lca/plugins/providers/attachment_default/`);`lca/plugins/seams/memory/attachment.py` Registry 拆掉。
- **PR-G**: `exportFile` 工具返回值改造为 `FileRef` (`kind="generated"`, `attachment_id` = 新写入 FileStore 的 id);`ArtifactLedger` 接入。
- **PR-H**: `e2b` / `docker` / `ssh` 后端各一个 `SandboxBackend` 实现;CI 加 stub 后端跑 e2e。
- **PR-I**: `kernl/run_kernel_lifespan` 的 entry point 加 `run_file_store_scope` 绑定,与 `execute.py:336` 一致。