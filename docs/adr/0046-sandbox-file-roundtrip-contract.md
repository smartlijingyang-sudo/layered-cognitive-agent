# ADR-0046: 沙箱文件往返契约 — `/mnt/data` 输入 + `/mnt/data/outputs` 产出

## 状态

Accepted

## 背景

`docs/proposals/0003` Phase C 已打通链路两端：

- 上传附件 → `FileStore` → `CreateRunRequest.attachment_ids` → **run ambient 自动挂载** → 沙箱 `/mnt/data`；
- `SandboxResult.generated_files` → `FileStore` → A2A `file_part` → 前端下载卡片。

中间缺口是：**沙箱内显式写盘** 的读回契约（历史多后端时行为不一致）。

当前唯一生产后端为 **Onlyboxes**（`pythonExec` + bootstrap 挂载/产物块，见 ADR-0044 修订）。
路径约定仍为：`/mnt/data` 输入、`/mnt/data/outputs` 产出。

## 决定

### 〇、Run 级附件 ambient 自动挂载（架构契约）

历史上 Gateway 只把 `attachment_ids` 写进问题文案，依赖模型在
`run_sandbox_code` 再传一遍 id；模型漏传时出现
`FileNotFoundError: /mnt/data/<name>`。

现行契约（与 `tool_invocation_scope` / `RunScope` 同型）：

1. **Gateway**：`CreateRun.attachment_ids` 写入 `RunSession.attachment_ids`
2. **`execute_run`**：`with run_attachment_scope(session.attachment_ids)`
   覆盖整次 task（contextvars 跨 `create_task` 继承）
3. **`SandboxCodeTool`**：`merge_attachment_ids(explicit)` =
   ambient ∪ 工具参数（去重，ambient 先），再从 FileStore 读字节挂载
4. **问题文案**仍嵌入路径提示（`/mnt/data/<name>`），供模型写对路径；
   **挂载本身不依赖模型传 id**

非 Gateway 入口（脚本/测试）可显式 `with run_attachment_scope([...])`。

### 一、统一产出目录约定

- 输入挂载：`/mnt/data/<原文件名>`（既有 `SANDBOX_MOUNT_ROOT`，只读语义由工具层约定）
- **产出专用子目录**：`/mnt/data/outputs/`（`SANDBOX_OUTPUT_SUBDIR = "outputs"`）
- 执行结束后各 Adapter **仅** 从该目录收集文件进 `SandboxResult.generated_files`
- 写到其它路径的文件**不**收集（本 ADR 不引入写盘路径重定向 wrapper）

### 一·附、`run_command` / terminal 自动 harvest（ADR-0050 扩展）

- `execute_code`：bootstrap 末尾 `GUEST_ARTIFACT_SCANNER`（既有）。
- **`run_command`（terminal 平面）**：`RunBoundSandboxRuntime.run_terminal` 在
  shell 返回后跑同一 scanner，将 **新或内容变更**（sha256 指纹，run 内）的
  outputs 文件并入 `generated_files` → FileStore → 前端下载卡。
- 多步 officecli 只在文件内容变化时再发卡片，避免每步重复导出同一 pptx。
- 后台 `run_command(background=true)` 不在启动时 harvest；`export_file` 仍
  用于 outputs 外路径或显式再导出。

### 二、双通道合并（E2B）

E2B 在 `sandbox.kill()` **之前**：

```text
generated_files = IPython 富展示结果 + /mnt/data/outputs 目录文件
```

`plt.show()` 与 `plt.savefig("/mnt/data/outputs/x.png")` 并存，不是二选一。

### 三、数量 / 体积上限与可诊断截断

- `SANDBOX_MAX_GENERATED_FILES = 20`
- `SANDBOX_MAX_GENERATED_FILE_BYTES = 20 MiB`
- 超限文件**跳过**，不拖垮 `exit_code` / `success`；在 stderr 写入
  `[lca] skipped output ...` 诊断，禁止静默丢弃。

### 四、Local 无假能力

microsandbox 当前锁定版本（`>=0.6,<0.7`）提供 `fs.list` / `fs.read`。
若运行时缺失 list/read，返回空 `generated_files` 并 `warning` 日志——
**不**假装产出了文件（对齐 ADR-0044）。

### 五、Mock 路径语义对齐

Mock 覆写内建 `open()`：读写 `/mnt/data/...` 走内存映射；`outputs/` 下写入
进入 `generated_files`。既有 `mounted_files` / `save_file()` **保留**为内部/
向后兼容，不再作为 LLM 文档推荐写法。Mock 仅虚拟化 `open()`，不覆盖
`pathlib.Path.write_*` 等（已知限制）。

### 六、Protocol 与上层不变

`Sandbox.run(...)` 签名、`SandboxCodeTool` 存库与 A2A part 形状、前端投影
均不变；本 ADR 只改 Adapter 内部与工具 `description` 文案。

## 后果

### 正向

- 同一段读/写代码在 Mock / E2B / Local 上行为一致，测试可写 parity。
- 前端零改动即可消费写盘产物。
- 上限 + 诊断避免超大/海量文件拖垮宿主。

### 负向 / 风险

- 依赖 LLM 遵守 `outputs/` 路径；写错目录仍会丢产物（后续可加重定向兜底）。
- Mock 只覆盖 `open()`；测试应用内建 `open` 而非 pathlib 写盘。
- Local 若 SDK 能力回退，需在 PR / 文档中披露「E2B/Mock 已打通，Local 受限」。

## 关联

- ADR-0004 Protocol-First
- ADR-0043 文件产物 / FileStore 通道
- ADR-0044 代码沙箱适配器（本 ADR 补完写盘读回）
