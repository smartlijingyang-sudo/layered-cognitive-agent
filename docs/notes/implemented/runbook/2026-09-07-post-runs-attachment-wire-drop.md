# Agent Note: `POST /runs` 把 LobeHub 附件 metadata 在 wire 上丢掉

Status: implemented

## Problem

LobeHub UI 把用户拖入的附件写到 `UIChatMessage` 顶层 `imageList[]` / `fileList[]` / `files[]`,但 `lcaExecuteGatewayRun` 在构造发给 LCA `POST /runs` 的 `messages` 时,只把 `content` 拷过去,丢了这三个字段。LCA ingress 看到的是裸文本 message,`parse_messages.file_refs` 为空,`prompt_assembler.task` section 只有 `USER_TASK: 分析下`,模型在 reasoning 里写 "no uploaded files",然后请用户重传附件。

证据:

- `traces/runs/run_22a83b4f1771/run_22a83b4f1771.spine.jsonl`:
  - `phase.think.fold.objective` 的 prompt 截断只看到 `ROLE: solo …CURRENT_DATE: … <tools>…`(全长 201 字符)。
  - `prompt_assembler.assemble.end.section_outputs.task = 'USER_TASK: 分析下'`,`prior_conversation = '(none)'`,`context = '(无历史上下文)'`。
  - `llm.call.end` 后模型 reasoning `text_delta = "no uploaded files."`(`seq=14`)。
  - 最终 stop.decision:`response_text = "您好！您提到「分析下」，但我目前没有看到需要分析的具体内容…"`。
- `traces/runs/run_dde085081f69/`(`run_22a83b4f1771` 之后用同 body 复现的 run):模型再次回应"请补充分析对象"。
- 直接对 LCA ingress 的单元调用 `.venv/bin/python -c "from lca.plugins.transport.webserver.handlers.runs.api.file_reference_parsing import collect_file_refs; ..."`:
  - `actual-from-lobehub body` → 0 refs
  - `+ imageList/fileList 顶层字段 body` → 2 refs
  - `OpenAI multipart (content=[{type:text,…},{type:image_url,…}]) body` → 1 ref

根因:

- `lobehub-ui/src/store/chat/agents/transports/lcaGateway/executeGatewayRun.ts:65-90` 取 `lastUser.content`(只 string)塞进 `messages`,丢了 `imageList` / `fileList` / `files`。
- `lca/plugins/transport/webserver/handlers/runs/ingest/ingress/ingress.py:55-65` 的 `parse_messages` 把 `last_user` 交给 `collect_file_refs`,后者**已经**支持 `structured_file_refs(item)` 读顶层 `imageList`/`fileList`/`files`,但 wire 上从来没传过来。
- LCA ingress 端**没有任何契约测试**覆盖 `prepare_run_from_messages` 收到带 `imageList` 的消息时的行为 → 回归静默发生。

## Proposal

1. 修改 patch 源 `deploy/lobehub/patches/runtime/lcaGateway/execute.ts`,把 `LcaStartRunBody.messages[]` 类型从 `{role, content: string}` 扩到 `{role, content: string, imageList?, fileList?, files?}`。
2. 修改 patch 源 `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts`,在构造 `lcaStartRun` 的 messages 前从 `lastUser` 抽 `imageList`/`fileList`/`files`,空数组丢弃(避免给纯文本轮次引入 wire 噪音),透传到 `[role:'user', content, ...attachmentExtras]`。
3. 跑 `python3 deploy/lobehub/patch_lobehub.py apply lca_runtime_agent_gateway` 把改动推到 lobehub-ui(derived 文件不入 git)。
4. LCA 端**契约测试**覆盖 hydration 路径,确保前端再有人压缩 wire shape 时会被 CI 拦下:
   - `tests/lca_plugins/transport/webserver/handlers/runs/api/test_collect_file_refs_wire.py`:覆盖 `imageList`/`fileList`/`files` 顶层字段、OpenAI multimodal `image_url`、纯文本不发明引用、空数组不强制发出。
   - `tests/lca_plugins/transport/webserver/handlers/runs/ingest/test_parse_messages_image_list.py`:覆盖 `parse_messages` 只取**最后一个** user message 的顶层附件字段,prior-turn 不污染当前轮。
   - `tests/scenario/lobehub_0/test_lobehub_patches.py::test_patch_source_*`:patch 源守门 — 任何改动 `attachmentExtras` 透传逻辑的人都必须通过这两个 unit 检查。

## Wire contract

- `POST /runs` body `messages[]` 中每个元素新增可选字段:`imageList?: {id, url, alt?}[]` / `fileList?: {id, name?, url?, fileType?}[]` / `files?: string[]`。均缺省 = 不出现在 wire 上,与历史纯文本消息 byte-compat。
- LCA `parse_messages` 只摘取**最后一个** user-role message 的附件字段,prior-turn 的 imageList/fileList **不**带进当前轮的 `attachment_ids`(测试 `test_prior_turn_imageList_is_dropped` 守门)。
- LCA `collect_file_refs` 同时支持本契约(imageList/fileList/files 顶层)和 OpenAI 标准(`content[]` 中 `type:image_url`)。

## Alternatives considered

### Why not 把 LobeHub UI 改为发 OpenAI multimodal(`content: [{type:text,...},{type:image_url,...}]`)?

否决:OpenAI 标准里没有 `type: file`,LCA 端需要扩展 `collect_file_refs` 增加 `type: file` 解析;改动面跨两个仓库且没有现成的 wire-shape 契约。Additive 顶层字段(`imageList`/`fileList`)LCA 端**已经**实现完整解析路径,只缺测试,改动最小。

### Why not 在 backend 解码 attachment_id 时从 lobehub-ui S3 反查?

否决:违反"lca 不知道 lobehub 实现"边界 — 跨仓库耦合;LCA ingress 已经有 `try_resolve_local_file` 走本地 FileStore 的快路径,继续以 `attachment_id` 为 wire 单元是 ADR-0099 的契约。

### Why not 在 client side 用 base64 data URL 内联进 `content`?

否决:对模型上下文体积不友好(`prompt_tokens` 暴涨),LCA 端没有 base64 解码路径,而且丢失了 FileStore 的 reuse / cache / 治理。

## Acceptance criteria

- 给定消息 `[{role:user, content:"分析下", imageList:[{id:"img-1", url:"https://s3/a.png"}]}]`,LCA `parse_messages().file_refs` 长度 == 1,source == `"imageList"`(`test_top_level_imageList_is_extracted_from_last_user_message`)。
- 给定消息含历史 `imageList` 但当前轮没有附件,`parse_messages().file_refs` == `()`(`test_prior_turn_imageList_is_dropped`)。
- 给定 `messages[0]` 仅有 `content`,`collect_file_refs` 返回 `[]`,不发明引用(`test_string_only_message_has_no_refs`)。
- patch apply 后 `lobehub-ui/.../lcaGateway/executeGatewayRun.ts` 出现 `attachmentExtras` 与 `...attachmentExtras`(`test_patch_source_forwards_attachment_extras_in_driver`)。
- patch apply 后 `lobehub-ui/.../lcaGateway/execute.ts` 类型扩展包含 `imageList?` / `fileList?` / `files?`(`test_patch_source_declares_attachment_extras_in_execute_ts`)。

## Risks

- 给 client `imageList`/`fileList`/`files` 加 3 个可选字段是非破坏性的 additive,纯文本消息 byte-compat,旧客户端/服务端无影响。
- 当前 LCA 端 `attachment_ids` 已经能容纳任意数量的附件(`compose_question` 在 `attachment_ids` 非空时拼 block);`FileStoreAttachmentIdentity` 的 `inline_max_bytes` 兜底 — 大附件走 staged file,不在 prompt 内联。
- `UIChatMessage.files`(string[],老字段)在 patch 源里被一并透传,与 `imageList`/`fileList` 互不依赖,前端 store 写入路径( `optimisticUpdate.ts:174`、 `conversationLifecycle.ts:595`)继续是 SSOT。

## Related

- `deploy/lobehub/patches/runtime/lcaGateway/execute.ts` — `LcaStartRunBody.messages` 类型扩展。
- `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts` — `attachmentExtras` 抽取 + 透传。
- `lca/plugins/transport/webserver/handlers/runs/ingest/ingress/ingress.py:55-65` — `parse_messages`(`collect_file_refs([last_user])` 是契约承担方)。
- `lca/plugins/transport/webserver/handlers/runs/api/file_reference_parsing.py` — `structured_file_refs` 已支持 `imageList`/`fileList`/`files` 顶层字段。
- `tests/lca_plugins/transport/webserver/handlers/runs/api/test_collect_file_refs_wire.py` — 新增契约测试。
- `tests/lca_plugins/transport/webserver/handlers/runs/ingest/test_parse_messages_image_list.py` — 新增契约测试。
- `tests/scenario/lobehub_0/test_lobehub_patches.py::test_patch_source_*` — patch 源守门测试。

## Delete-when

- `tests/lca_plugins/transport/webserver/handlers/runs/api/test_collect_file_refs_wire.py` 中的 `test_string_only_message_has_no_refs` 表达"裸文本不发明附件"语义 —— 在 LCA 不再把 `imageList`/`fileList`/`files` 当顶层字段契约之前,这一断言必须保留。
- `tests/lca_plugins/transport/webserver/handlers/runs/ingest/test_parse_messages_image_list.py::test_prior_turn_imageList_is_dropped` 表达"只有当前轮带附件" —— 在 LCA 重新定义 `extract_prior_turns` 的过滤策略之前必须保留。
- `tests/scenario/lobehub_0/test_lobehub_patches.py::test_patch_source_*` 在 `lcaExecuteGatewayRun` 不再是从 user message 抽取 attachment 的唯一切片之前必须保留(如果改用 React Context 注入,迁移到对应新位置即可)。
- delete_when 检测命令:`./scripts/lca-ops lobehub ensure` 通过 + `pytest tests/lca_plugins/transport/webserver/handlers/runs tests/scenario/lobehub_0/test_lobehub_patches.py` 全绿,且 `rg -n "attachmentExtras" deploy/lobehub/patches/runtime/lcaGateway/` 不为空。