# Workspace SSOT 对齐计划（2026-10-03）

> 目标：**跨会话持久** + **工作区 SSOT 一个地方**。对齐 Muse 机制：
> 上传进 agent 自己的 workspace 落盘持久化，agent 感知到的"家" = 系统所说的 Workspace = 文件实际落点。
> 现状实证见 §0。**本计划只改文档中列出的点，改全、不留死角；代码不动，等评审后执行。**

## §0 现状：三个"工作区"各说各话（实证）

2026-10-03 19:53 用户上传`国庆长沙接待行程规划.html`（68KB），20:05 问 agent"这个文件有在 Workspace 吗"，
agent 答"对话上下文 ✅ 有，`/mnt/data` 工作区 ❌ 没有，不会自动落盘"。三处实证：

| # | "工作区"所指 | 实际位置 | agent 是否可见 | 状态 |
|---|---|---|---|---|
| 1 | prompt 里的 `{{sandbox_workspace_root}}` | guest 内 `/mnt/data`（`SANDBOX_MOUNT_ROOT`，Onlyboxes 镜像契约） | ✅ 唯一可见 | 空 |
| 2 | `WorkspaceService`（ADR-0244 D7.2） | host `{home}/workspace/`（`~/.lca/assistants/<id>/workspace/`） | ❌ 概念不可达 | 空（设计使然） |
| 3 | 上传实际落点（`FileStore`） | host `traces/files/{id}/`（blob + meta.json，conversation_id=null） | ❌ 世界模型中不存在 | **有文件** |

结论：agent"又说在又说不在"不是模型绕，是机制问题——同一个词指了三个地方，
且它唯一能看见的那个是空的。`FileStore` 无 `list()`（只有 put/get/read_bytes/exists），
"有仓库，没目录"。

## §1 目标态

```
{assistant_home}/workspace/          ← 唯一的 Workspace（SSOT），跨会话持久
├── uploads/                        ← 上传落点（替代 traces/files/）
├── files/                          ← agent 生成/保存的文件（write_file 默认落这里）
└── runs/<run_id>/                  ← run 隔离区（现有 GuestLayout.for_run 语义保留）
```

- guest 内路径契约不动：`/mnt/data` 仍是镜像契约，host 侧挂载源改为 `{home}/workspace/`。
  agent 在沙箱里看到 `/mnt/data/...`，背后就是 workspace/——"他老是说 /mnt/data 没意义"
  的解法是 prompt 文案改称"你的 Workspace"，路径名本身保留（改 guest 契约会掀翻 Onlyboxes）。
- 上传：`FileStore` 根从 `traces/files` 迁到 `{home}/workspace/uploads`，meta 写实 conversation_id，
  加 `list()`，agent 可发现、可跨会话读取。
- `WorkspaceService`（已有 `list()`/读写/traversal guard）与沙箱 host_root 指向同一物理目录，
  不再是两套东西。

## Task 1：FileStore 落点迁移 + list() + conversation_id 写实

**涉及文件**
- `lca/infrastructure/file/store.py`（`LocalFileStore.__init__` 默认根、`put` 签名已有 conversation_id 形参）
- `lca/plugins/transport/webserver/bootstrap/bootstrap.py:55`（`file_store_root = Path("traces/files")`）
- `lca/plugins/transport/webserver/handlers/runs/ingest/service/service.py:104`
 （`store.put(data=data, name=ref.name, mime_type=...)` 未传 conversation_id → meta.json 里 null）
- `lca/plugins/memory/providers/file_store_provider.py`（读 traces/files 的另一处）

**步骤**
1. `FileStore` 抽象类加 `list() -> list[StoredFile]`（按 name/mtime 排序）；`LocalFileStore` 实现
   （遍历根目录读 meta.json，损坏的 meta 跳过并记日志）。
2. bootstrap 默认根改为 `{assistant_home}/workspace/uploads`（home 从 kernel seam 取，
   与 WorkspaceService 同源；回退逻辑保留）。
3. ingest service 的 `put` 调用传入真实 conversation_id（调用链上已有 run/session 上下文，
   由执行者确认取值点；取不到时显式记日志，不静默 null）。
4. `file_store_provider.py` 的根引用同步改掉；全局 grep `traces/files` 确认零残留。

**验收**
- 上传文件落 `{home}/workspace/uploads/{id}/`，meta.json conversation_id 非 null。
- 新会话 agent 调 `list_files`（或 FileStore.list 暴露的工具）能看到上轮上传的文件并读取内容。
- `grep -rn "traces/files" lca/ tests/ --include=*.py` 零命中（测试除外，见 Task 5）。

## Task 2：沙箱 host 挂载源 → workspace/（SSOT 统一）

**涉及文件**
- `lca/contracts/models/core/state/guest_layout.py`
  （`GuestLayout.onlyboxes()`/`for_run()` 的 `base_root` 默认 `SANDBOX_MOUNT_ROOT`）
- `lca/infrastructure/sandbox/local/adapter.py:62,98-100`
  （`Path(SANDBOX_MOUNT_ROOT)` host 路径、`GuestLayout.from_root(SANDBOX_MOUNT_ROOT)`）
- `lca/infrastructure/sandbox/factory/factory.py`（onlyboxes/local 后端的 host_root 装配处）
- `lca/infrastructure/capability/sandbox/sandbox.py:33`（`base_dir` 默认值）
- `lca/infrastructure/attachment/default/provider.py:148-149`
  （附件路径拼 `f"{SANDBOX_MOUNT_ROOT}/..."`——guest 视角，保持不动，注释标明）

**步骤**
1. host 侧挂载源改为 `{assistant_home}/workspace/`：
   `GuestLayout.onlyboxes()` → `from_root(workspace_host_root())`，
   `for_run(run_id)` → `workspace_host_root()/runs/<run_id>`（run 隔离语义保留）。
2. guest 内契约不动：`SANDBOX_MOUNT_ROOT = "/mnt/data"` 保留，
   agent 在沙箱里仍见 `/mnt/data`，背后已是 workspace/。
3. `provider.py` 的 guest 路径拼接保持不动（那是 guest 视角）；local adapter 的 host 侧路径同步改。
4. `WorkspaceService` 的 root 与沙箱 host_root 断言为同一路径（启动时校验，不一致则 fail-fast，
   防将来又分叉）。

**验收**
- agent 在沙箱写文件 → host `{home}/workspace/` 下立即可见；反之亦然。
- 新开 run，`workspace/runs/<新run_id>/` 自动建立；`workspace/uploads/` 跨 run 可见。
- 旧 run 的 outputs 收集路径（`outputs_dir`）行为不变。

## Task 3：prompt/文案统一——"你的 Workspace"心智模型

**涉及文件**
- `lca/infrastructure/sandbox/prompt/prompt.py:38-47`
 （`{{sandbox_workspace_root}}`/`{{sandbox_outputs_dir}}`/`{{sandbox_uploaded_files}}` 渲染）
- `lca/infrastructure/attachment/system/role_renderer.py:105,144-151`
 （`{{sandbox_workspace_root}}` 替换、`sandbox_policy_text`）
- `lca/infrastructure/attachment/settings/settings.py:48`
  （`sandbox_policy_text(workspace_root)` 文案）
- `lca/infrastructure/attachment/system/templates/` 下 system role 模板（含 `{{sandbox_workspace_root}}`
  上下文句）

**步骤**
1. 渲染值不变（`/mnt/data`），但模板文案改为："你的 Workspace（持久化工作目录，
   跨会话保留；host 侧即你的 assistant workspace）"。`/mnt/data` 只作为路径出现，
   不再作为概念名称。
2. `sandbox_policy_text` 同步改措辞；`{{sandbox_uploaded_files}}` 段注明文件已落在
   workspace/uploads，可用工具列出。
3. 全局 grep `sandbox_workspace_root`/`/mnt/data` 的用户可见文案，统一口径。

**验收**
- 新 run 的 system prompt 里，"工作区"一词只指向一个概念；抽查 3 个历史问法
  （"文件在 Workspace 吗""保存到工作区""列一下工作区文件"）agent 回答不再自相矛盾。

> **状态（2026-10-08）：已落地。** commit `4ebae41ee` 改了两个 prompt section 的文案
> （HomeSection 与 cloud_sandbox_system_role.md）：概念名统一为「你的 Workspace」，
> `/mnt/data` 只作为 guest 路径值出现；回复面要求优先给 workspace 相对路径。
> per-run 沙箱根绑定由 `78034deea` 完成（SessionConfig.workspace_root）；
> guest 脚本 ROOT 跟随会话根由 `f03b2359a` 完成（LCA_GUEST_ROOT）；
> 模型可见相对路径投影的单点在 guest `emit()`（`8094cc234`，取代宿主侧前缀投影），
> 契约绝对入参映射由 `b6608bb58` 完成；carrier 对 agent-only run 的助理身份解析
> 由 `66fafdcf0` 与 `01f205289` 完成（ownership store 反查 + 裸字符串 agent 解析）。

## Task 4：历史 traces/files 迁移 + 旧根废弃

> **状态（2026-10-03 21:0x，李超决策）：本 Task 已撤销——"历史不迁移"。** `traces/files/` 旧根保留只读；迁移脚本/双读/废弃/回填 memory 均不执行；设计要点 4 的"迁移期双读"随之作废。

**步骤**
1. 一次性迁移脚本：`traces/files/{id}/` → `{home}/workspace/uploads/{id}/`
   （blob + meta.json 原样搬；meta 缺 conversation_id 的标 `migrated:true`，不编造）。
2. 迁移后 `traces/files` 改名 `traces/files.deprecated-<日期>` 保留一轮，
   下下轮确认无引用后删除。
3. 回填 memory：迁移的文件逐个记一条 memory（"用户曾上传 <name>"），
   补 2026-10-03 发现的"下次会话 agent 不知道这份文件"缺口。

**验收**
- 迁移前后文件数一致（`find | wc -l` 对比）；旧根零引用（Task 1 验收已覆盖）。

## Task 5：测试全量更新 + 新增回归测试

**涉及文件**（引用 `/mnt/data` 或 `traces/files` 的测试，2026-10-03 实测 16 个，执行者复核补全）
- `tests/infrastructure/sandbox/test_export_file_no_duplicate_store.py`
- `tests/infrastructure/test_local_sandbox_attachment_path.py`
- `tests/scenario/onlyboxes/test_onlyboxes_sandbox.py`
- `tests/scenario/officecli/test_officecli_plane.py`
- `tests/scenario/run_0/test_run_command_output_harvest.py`
- `tests/contracts/test_attachment_seams.py`
- `tests/contracts/models/environment/test_execution_environment.py`
- `tests/infrastructure/environment/test_environment_catalog.py`
- `tests/infrastructure/runtime_plane/test_access_classify.py`
- `tests/infrastructure/runtime_plane/test_access_policy.py`
- `tests/infrastructure/memory/test_standing_write_path.py`
- `tests/plugins/prompts/test_home_memory_sections.py`
- `tests/plugins/session/derivers/step_tree/test_journal_fold_concurrent_tools.py`
- `tests/loop/commit/test_record_step_tool_result_failure_kind.py`
- `tests/integration/test_hitl_e2e_loop.py`
- （另：`lca/infrastructure/sandbox/surface/fingerprint.py` 的 `_WORKSPACE_ROOT_ALIASES`
  加 workspace host 路径别名，保留 `/mnt/data` 别名）

**新增回归测试**（`tests/scenario/test_workspace_ssot.py`）
- WSOT-01：上传 → 落 `{home}/workspace/uploads/`，meta conversation_id 写实。
- WSOT-02：FileStore.list 能列出上传文件。
- WSOT-03：沙箱内写入 → host workspace 可见（双向）。
- WSOT-04：新会话（新 run）能读取上一会话上传/生成的文件（跨会话持久）。
- WSOT-05：`WorkspaceService` root == 沙箱 host_root（同一物理目录断言）。
- WSOT-06：旧 `traces/files` 零引用（防回潮）。

**验收**：`LLM_API_KEY=dummy pytest tests/scenario/test_workspace_ssot.py` 全绿；
上述 16 个文件按新路径更新后全绿（pre-existing 红除外，标出）。

## Task 6（可选）：前端文件浏览

对齐 Muse 的 System Files 思路：前端加"Workspace 文件"浏览入口，
读 `{home}/workspace/`（经现有 `/files` 下载/meta 接口扩展 list）。
依赖 Task 1–2 完成后做。本计划不展开，另起前端任务。

## 风险与取舍

1. **只映射 workspace/ 子目录，不碰 home 根**：memory、config 等仍在 home 下其他位置，
   agent 在沙箱里够不着——隔离边界清晰。
2. **run 隔离保留**：`runs/<run_id>/` 继续按 run 隔离；跨会话持久的是 `uploads/` 和 `files/`。
   这是"统一"与"隔离"的折中，比 Muse 更保守（Muse 的 workspace 无 run 隔离）。
3. **guest 内 `/mnt/data` 路径名保留**：改的是 host 挂载源，不动 Onlyboxes 镜像契约；
   agent 口中的"/mnt/data"从此有意义（= 它的 Workspace）。
4. **迁移期双读**：Task 4 迁移窗口内，FileStore 可短暂双根读取（新根优先），迁移完立即收敛到单根。

## 与 Muse 机制的对齐关系

| Muse | 本计划 |
|---|---|
| 上传进 `workspace/user/` 落盘持久化 | Task 1：`workspace/uploads/` |
| agent 随时翻自己文件系统（发现=浏览） | Task 1 `list()` + Task 2 统一挂载 |
| Workspace 即 agent 的家，无第二套 | Task 2：单物理目录 + 启动断言 |
| Library 只收 `your_files` 交付物 | 不变（本次不碰 Library 语义） |
