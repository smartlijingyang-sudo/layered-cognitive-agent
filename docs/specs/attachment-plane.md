# Attachment Plane Spec (ADR-0121)

> Status: 现行规范;每次变动先更新 `docs/adr/0121-attachment-fileref-and-plane-provider.md`,再改代码。

## 1. 一句话

附件 = 一个 `FileRef` + 三个 Seams(`AttachmentResolver` / `AttachmentStager` / `AttachmentPromptRenderer`) + 一个 `SandboxBackend` 协议 + 一个 `lca-attachment-default` 默认 provider。**所有附件相关代码必须经过它们之一**。

## 2. 链路总览

```text
lobehub UI POST /files/{id}
  ↓ FileStoreAttachmentIdentity.compose_question
  ↓ <files_info><file id=... url="/files/{id}"></files_info>   (user message)
  
  ↓ run_file_store_scope(store) [CreateRun entry]
  ↓ run_attachment_scope([id])    [CreateRun entry]

CognitiveRuntime._loop
  ↓ reasoner._cloud_sandbox_block(tools)
  ↓ build_cloud_sandbox_prompt(tools)
  ↓ _render_cloud_sandbox_block → render_system_role(plane, template_name)
    ↓ DefaultAttachmentPromptRenderer.identity_block(refs)   (current turn)
    ↓ DefaultAttachmentPromptRenderer.guest_path_block(refs, plane)
        → "/mnt/data/Clash_1752915628.yaml"
    ↓ single-pass placeholder substitution
  ↓ <uploaded_files> ... </uploaded_files>                    (system prompt)

  ↓ LLM picks readFile({path: "/mnt/data/Clash_1752915628.yaml"})
  
Tool dispatcher
  ↓ SandboxComputer.read_file(path=...)
  ↓ _resolve_path_arg_or_passthrough(path)   # NEW
    ↓ resolve_path_arg("/mnt/data/...")
      → /mnt/data/... is workspace path → pass-through
    ↓ resolve_path_arg("/files/file_xxx")   # model misuse
      → resolve_for_plane(FileRef, plane) → /mnt/data/<name>
  ↓ normalize_sandbox_path → guest script READ_FILE_SCRIPT
  ↓ hit /mnt/data/Clash_1752915628.yaml ✓
```

## 3. FileRef 闭集

```text
FileRefKind   = Literal[
    "user_upload",      # 人通过 lobehub 上传
    "sandbox_init",     # 已 stage 到沙箱 /mnt/data/<name>
    "inbox_staged",     # 已 stage 到机器 .lca/inbox/<run>/<name>
    "generated",        # 工具产出 (exportFile 等)
    "workspace",        # 任意 guest/host 路径
    "external_url",     # http(s):// — 待 fetch
]
FileRefSource = Literal[
    "lobehub_upload",   # 来自 lobehub UI 上传
    "sandbox_bootstrap",  # 来自 runtime_mount
    "machine_stage",    # 来自 inbox stage_payload
    "tool_export",      # 来自工具 (exportFile 等)
    "inline_text",      # 内联到 prompt 的文本
]
```

每个 FileRef 必带:

```text
target_key   # 稳定身份,消费者不解析
display_path # 给 LLM / 用户看
process_path # 当前 plane 上可执行路径
file_url     # file: URI
mime_type, size_bytes, attachment_id
```

## 4. 三个 Seam 的契约

### 4.1 `AttachmentResolver`

```text
resolve(ids) -> tuple[ResolvedAttachment, ...]
resolve_for_plane(ref, plane) -> FileRef
```

实现: `lca/infrastructure/attachment/default_provider.py::DefaultAttachmentResolver`

### 4.2 `AttachmentStager`

```text
stage_to_machine(run_id, refs) -> dict[target_key, absolute_path]
stage_to_sandbox(sandbox_id, refs) -> tuple[MountEntry, ...]
build_manifest(refs) -> MountManifest
```

实现: `DefaultAttachmentStager`(同上)。

### 4.3 `AttachmentPromptRenderer`

```text
identity_block(refs) -> str
guest_path_block(refs, plane) -> str
inline_content_block(refs) -> str
```

实现: `DefaultAttachmentPromptRenderer`(同上)。

## 5. `SandboxBackend` 协议

```text
mount_root() -> str
ensure_mounts(manifest, *, timeout_s) -> MountManifest
translate_ref(ref) -> FileRef
read_bytes(process_path) -> bytes | None
list_files(directory) -> Sequence[str]
```

默认实现: Onlyboxes(`lca/infrastructure/sandbox/onlyboxes_adapter.py`)。
可替换实现: e2b / docker / ssh / in-memory stub(后续 PR)。

## 6. 单一 System Role Renderer

入口: `lca/infrastructure/attachment/system_role_renderer.py::render_system_role`

```text
render_system_role(
    plane: PlaneRef | None,
    *,
    template_name: str,
    store: FileStore | None = None,
    extra_placeholders: dict[str, str] | None = None,
) -> SystemRoleResult
```

- 内部单遍替换所有占位符:
  `{{attachment_policy}}` / `{{uploaded_files}}` / `{{sandbox_uploaded_files}}`
  `{{sandbox_environment_note}}` / `{{sandbox_workspace_root}}` / `{{sandbox_outputs_dir}}`
  `{{label}}` / `{{platform}}` / `{{root}}` / `{{outputs_dir}}`
- FileStore 缺省从 `run_file_store_scope` ambient 取;reasoner 无需传 `store=`。
- 返回 `SystemRoleResult { text, plane_kind, refs_rendered: tuple[FileRef, ...] }`。
  Journal 用 `refs_rendered` 记一次性审计(可关联到 model 实际看到的 guest 路径)。

## 7. Tool Dispatch 拦截

`lca/infrastructure/tools/seam/file_ref_args.py`:

```text
resolve_path_arg(raw, *, allowed_refs=None) -> ResolvedPathArg
```

| raw 形态 | 处理 |
|---|---|
| `/files/<aid>` | 通过 ambient FileStore lookup → FileRef (workspace path 由 host 返回) |
| `http(s)://...` | FileRef(kind=user_upload, target_key=url), 实际 fetch 由 sandbox 端 curl 完成 |
| 绝对/相对路径 | pass-through, kind=workspace |
| 空 / 不匹配 | raise UnresolvedFileRefError |
| `<aid>` 匹配多个 | raise AmbiguousFileRefError |

## 8. 错误码闭集

```text
AttachmentErrorCode(str, Enum):
    UNRESOLVED_REF                # 模型给的 raw 解析不到 FileRef
    AMBIGUOUS_REF                 # 解析到多个候选
    MISSING_ATTACHMENT            # FileStore 中查不到
    POLICY_REJECTED               # inline policy 拒绝(超出 max_bytes 等)
    STAGE_FAILED                  # 写盘失败
    RENDERER_NOT_REGISTERED       # attachment plane 装配失败
    SANDBOX_BACKEND_UNAVAILABLE   # 当前 sandbox backend 不支持该 op
```

每个 `AttachmentError` 携带 `code` + `context: dict[str, object]`,Journal 写入时无需 parse message。

## 9. 测试覆盖

| 测试 | 守门 |
|---|---|
| `tests/contracts/test_attachment_seams.py` | 15 项 Protocol conformance |
| `tests/lca/infrastructure/attachment/test_default_provider.py` | 10 项 Resolver/Stager/Renderer + system role regression gate |
| `tests/lca/cognition/brain/test_reasoner_cloud_branch_renders_uploaded_files.py` | 1 项 trace `run_75e88a76899b` 永久门禁 |
| `tests/lca/infrastructure/tools/seam/test_file_ref_args.py` | 8 项 dispatch 拦截 |

## 10. lobehub 前端契约

- `<file id name type size url>` 字段保留;`url` 仍指向 `/files/<aid>` HTTP 下载地址。
- `<uploaded_files>` 块由 LCA 后端注入;前端 patch `deploy/lobehub/patches/ui/file_list_gateway_preview.py` 不动。
- `file_list_gateway_preview` patch 的 `window.open(url, '_blank')` 已经支持浏览器下载(Content-Disposition: attachment 由 `lca/plugins/transport/webserver/handlers/files.py::download_file` 设置)。

## 11. 不允许的写法

- ❌ 任何 `sandbox_computer` / `runtime_exec` 直接读 `/files/<aid>` 字面量。
- ❌ 任何 `prompt.py` / `surface.py` / `sandbox.prompt` 再次渲染 `<uploaded_files>` / `<files_info>`。
- ❌ 任何 caller 拿裸路径字符串跨过 `resolve_path_arg` 透传到 sandbox。
- ❌ 任何 `format_*` wrapper 在生产代码中存在(只在 `tests/test_attachment_prompt.py` 历史兼容测试里允许)。