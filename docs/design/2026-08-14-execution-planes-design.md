# 执行平面 — 纠偏后的架构

**日期**: 2026-08-14  
**状态**: Canonical（取代 `2026-08-14-execution-context-design.md`）  
**修订**: 同一日二次收敛。主环境唯一；双绑降为显式开关；操作面拆成两个适配器。  
**动机**: 修正 Host 路径精神分裂；按 LobeHub 原生切分吸收「两种产品环境」，用 LCA 已有 Run/Journal 把全流程写死。

旧草案把 Host / Onlyboxes / SSH / Windows 收进一个 `ExecutionContext.execute()`。分类错了。  
前一版纠偏把分类改对了，但把「两环境可以同时存在」写成了「默认两套脸全上」，并把 `ComputerRuntime` 画成按 `kind` 选传输的单类。那是在正确分类上复发上帝对象。

**架构一次定对。** 落地按缝拆 PR；中间态禁止 remap，禁止 Host-as-Sandbox，禁止单类 `if kind`。

---

## 1. 第一性原理

一个 agent 要操作计算资源。那不是一种东西，是四件独立的事：

| 问题 | 变的时候谁改 |
|---|---|
| **这是哪类产品环境？** 用户的机器，还是隔离沙箱？ | Prompt、HITL、导出、生命周期、工具脸 |
| **这一次 Run 的主环境是哪一个？** | 绑定。附件、Skill、默认工具脸只问这一问 |
| **怎么连上去？** sidecar / SSH / 沙箱 HTTP | 传输适配器 |
| **那台机器的 OS？** POSIX / Windows | `local_shell` 内部 |

同一种产品环境内部只有一个文件系统。Agent 看见的就是那个环境里的真实路径。**禁止跨环境翻译路径。**

`/mnt/data` 在沙箱里是真路径（LobeHub `SANDBOX_UPLOADED_FILES_DIR` + ADR-0046）。它在 Host 上才是假的。

由此推出三条，不再商量：

1. **种类只有两个。** `machine` 与 `sandbox`。SSH、Windows、E2B、浏览器 Computer Use 都不是第三种。
2. **一次 Run 恰好零个或一个主环境。** 主环境回答「附件落哪、Skill 跑哪、prompt 承诺哪、默认注册哪张脸」。没有主环境 = 无 computer exec。
3. **第二环境是显式开关，不是默认架构。** 两边都在线，不等于两套工具同时进清单。静默双绑把工具选择问题伪装成身份问题。

「plane」在本文只指这两种产品环境。不是 ADR-0051 `RunWorkspace`，不是 Search / Office / Evidence。磁盘根不叫 workspace。

---

## 2. 对 LobeHub 原生架构：吸取什么，我们强在哪

对照 `lobehub-ui`：`builtin-tool-local-system`、`builtin-tool-cloud-sandbox`、`builtin-tool-remote-device`、`tool-runtime/ComputerRuntime`、`device-sandbox`、`local-file-shell`。

LobeHub 的操作面不是「一个类按 kind 分支」。它是：

- 抽象 `ComputerRuntime`：文件 / shell / 搜索，子类实现 `callService`
- `LocalSystemExecutionRuntime`：IPC
- `CloudSandboxExecutionRuntime` **extends** 基类，再加 `executeCode` / `exportFile`

| LobeHub | 本方案 | 为何 |
|---|---|---|
| 两套工具包，标识 `lobe-local-system` / `lobe-cloud-sandbox` | **吸取。** 两张工具脸，WIRE 按标识投影 | 同一 `list_files` 换语义是我们现在的病 |
| 同一 `apiName`（`listFiles`）靠 identifier 分命名空间 | **必要偏差：`local_*` 前缀** | LCA 的 function calling 是扁平表；前缀是防腐层，不是第三套语义 |
| `exportFile` / `executeCode` 只在 cloud-sandbox | **吸取。** 机器脸不挂这两张 | 本机没有「从另一台机器导出」；代码解释器是沙箱产品 |
| `remote-device` 只做 list/activate，不是文件 backend | **吸取。** 设备选择 ≠ 环境 | Windows/Linux 远程都是 `machine` |
| `pathScopeAudit`：工作区外 → HITL，不 remap、不默认整盘 | **吸取，且与真路径同一批落地** | 真路径没有可写根就不稳定 |
| 抽象基类 + 两个具体运行时；`content` / `state` / `error` | **吸取切分，不吸取「一份类」。** 两个适配器，共享的是 Result 与格式化函数 | 单类 `if kind` 就是今天 `_maybe_local` 的升级版 |
| 两份 systemRole，沙箱第一句「不是用户本地」 | **吸取。** 只注入**主环境**的那一份；有第二环境再加一段短声明 | 禁止一个函数拼两种承诺 |
| 本机 prompt 有 `workingDirectory` 和 `homePath` | **吸取为数据。** `root` 是可写根；`home` 只进 prompt，不是第二信任根 | 相对路径对 `root`；「桌面」等口语对 `home` |
| 恰好一台在线则直接激活 | **吸取为解析规则。** 激活的是「机器候选」，不是自动当主环境 | 两边都在时，在线 sidecar 不得偷走主环境 |
| 附件只同步进沙箱；本机假定文件已在盘上 | **我们更好：主环境若是机器，附件落到真 `root/<name>`** | LCA 主 UI 是浏览器，附件在 FileStore |
| 本机产物留在用户盘，桌面端直接预览 | **我们更好：机器 `outputs_dir` 自动发布进 FileStore** | Web UI + 可能远程 Windows，没有桌面预览通道 |
| `activateDevice` 可在话题中途改绑定 | **我们更好：Run 开工冻结 `PlaneBindings`** | Journal / HITL / Team 可复现；换机 = 下一次 Run |
| 无 Run 级挂载/inspect | **保留 ADR-0050 `SandboxRuntime`** | 结构化挂载失败，强于「Agent 自己探路」 |
| 隐式 `activeDeviceId` | **我们更好：`PlaneRef` 纯数据进 Journal** | debug 先问主环境是哪一个 |
| 两套完整 TS 包（Inspector / Render） | **不复制 UI 包。** 后端两个适配器；前端靠 WIRE identifier 走现成 Inspector | LCA 不重写 LobeHub 卡片 |
| `device-sandbox` SRT 包命令 | 后做，不进身份对象 | 可写根 HITL 先落地；SRT 是传输加强 |

不吸取的：把本机伪装成 `/mnt/data`、单例抢占、`ExecutionContext` 上帝对象、默认双开两套工具。那些也不是 LobeHub 的默认产品形态。

---

## 3. 目标架构

```
                         Run
                           │
              bind PlaneBindings（冻结）
              primary 必问；secondary 仅显式
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
   主环境 PlaneRef                    第二环境 PlaneRef | None
   一张工具脸 + 一份 system role       默认不注册
          │                                 │
          ▼                                 ▼
   ComputerOps（Protocol）            同一 Protocol
   content + state + error
          │                                 │
          ▼                                 ▼
   MachineComputer                  SandboxComputer
   + MachineTransport               + SandboxRuntime
   sidecar | ssh | inproc           onlyboxes | 未来 e2b
          │                                 │
          ▼                                 ▼
   local_shell                      挂载 / inspect / harvest
   posix | windows                  ADR-0050
                                    + execute_code / export_file
```

六个变化原因，六个落点。浏览器 Computer Use 是另一种 embodiment，不扩 `PlaneKind`。

`ComputerOps` 是文件 / shell / 搜索的 Protocol（对齐 LobeHub 抽象基类）。  
`MachineComputer` 与 `SandboxComputer` 是两个实现，**构造时各绑死一张 `PlaneRef` 和一种传输**。没有 `if plane.kind`。  
`SandboxComputer` 另有 `execute_code` / `export_file`。  
`SandboxRuntime` 只做沙箱挂载/会话/inspect，不做本机文件。

共享的是 `ComputerOpResult` 和纯格式化函数，不是一个会分支的类。今天的 `_maybe_local`（对 `Sandbox` 鸭子调用 `computer_op`）删除。

已有 `RunWorkspace`（ADR-0051）是 Run 的截止时间 + 产物账本。**磁盘根不叫 workspace。** 身份对象叫 `PlaneRef`。

### 3.1 身份：`PlaneRef` / `PlaneBindings`（纯数据，无行为）

`lca/contracts/models/core/plane.py`

```python
class PlaneKind(str, Enum):
    MACHINE = "machine"
    SANDBOX = "sandbox"


@dataclass(frozen=True)
class PlaneRef:
    id: str  # device_id / sandbox session_id
    label: str
    kind: PlaneKind
    root: str  # 该环境内的真实可写根
    outputs_dir: str  # root/outputs
    platform: str = ""  # linux | darwin | win32 | ""
    home: str = ""  # 仅 prompt：用户家目录；不是第二可写根


@dataclass(frozen=True)
class PlaneBindings:
    primary: PlaneRef | None
    secondary: PlaneRef | None = None
```

没有 `execute()`、capability 集合、prompt 方法、`machine`/`sandbox` 访问器。读槽位用 L0 纯函数，例如 `ref_of(bindings, PlaneKind.MACHINE)`。

解析后的不变量（在 `resolve_plane_bindings` 里检查，不写进 dataclass 方法）：

- `secondary` 非空 ⇒ `primary` 非空，且 `primary.kind != secondary.kind`
- 同一种类不得绑两次

---

## 4. 产品环境

**机器 (`machine`)** — 对齐 `lobe-local-system`

- 用户本机或已激活的远程 sidecar。路径是那台机器上的真路径。
- 信任：用户的电脑。`root` 内直接执行；`root` 外 HITL（§5.5）。
- 生命周期：设备在线即在，不随 Run 删盘。
- 工具脸：`local_*`（§6）。无 `execute_code`、无 `export_file`。
- Prompt：这是用户的机器 `{label}`（`{platform}`）；工作根 `{root}`；家目录 `{home}`（若有，只用于理解「桌面」等口语）；附件在 `{root}/<filename>`；交付物写 `{outputs_dir}`；相对路径相对 `root`；绝对路径按 OS 原样，越 `root`（及平台临时目录以外）要审批。禁止出现 Cloud Sandbox / `/mnt/data`。

**沙箱 (`sandbox`)** — 对齐 `lobe-cloud-sandbox`

- Onlyboxes，未来 E2B / Modal。路径 `/mnt/data`。
- 信任：隔离盒。产物默认 harvest。
- 生命周期：绑定 Run，结束销毁（ADR-0050）。
- 工具脸：现有 `list_files` / `execute_code` / `export_file` …。
- Prompt：第一句必须是「这不是用户本地文件系统」。

主环境决定注入哪一份完整 system role。  
仅当 `secondary` 被显式绑上，再追加一段短声明：另有一套脸，路径不可混用。

---

## 4.1 完整链路：浏览器怎么用上这条架构

架构不是新开一条协议。现有 Run Live 不动：浏览器仍 `POST /lca-api/runs` + `GET .../live`。变的是 **Gateway 在开工时冻一份 `PlaneBindings`，后面每一跳只读它。**

```
浏览器  lobehub-ui :3010
  │  发消息 + 附件 +（可选）device_id / plane / extra_plane
  │  executeClientAgent → runLcaJournal
  │  POST /lca-api/runs          ──proxy──►  Gateway :8765 POST /runs
  │  GET  /lca-api/runs/{id}/live ──proxy──►  SSE Journal
  │
  ├─ 并行、不跟单条消息走：
  │    sidecar  python -m host / npx …
  │    WS /presence/connect  HELLO{device_id, platform, name, home?}
  │    PresenceRegistry 在线表
  │
Gateway
  │  1. ingest 附件 → FileStore（现状）
  │  2. resolve_plane_bindings(...) → session.bindings 冻结
  │       候选 machine ← Presence + §5.2
  │       候选 sandbox ← resolve_sandbox() 仅 Onlyboxes
  │       按 §5.1 选出 primary / secondary
  │  3. 附件落到已绑环境（主环境必落；secondary 仅当时才落）
  │  4. 只为主环境组默认工具脸 + 对应 system role
  │     secondary 有值才再注册第二张脸
  │  5. Agent/Team.run()     Team 共用这一份绑定
  │
Agent
  │  看见的工具脸 = 绑定结果
  │    主环境 machine：local_*     WIRE → lobe-local-system
  │    主环境 sandbox：list_files… WIRE → lobe-cloud-sandbox
  │    有 secondary：再加另一张脸（显式双绑，不是默认）
  │
适配器（构造时绑死 PlaneRef + 传输，无 kind 开关）
  │  local_read_file  → MachineComputer → MachineTransport → sidecar
  │                     真路径，无 remap
  │  read_file        → SandboxComputer → SandboxRuntime + guest 脚本
  │                     /mnt/data 是容器内真路径
  │
Observation  content + state + error
  │  record() → jsonl + LiveTail
  │  事件带 plane.kind / id / root / primary|secondary
  │
浏览器  LcaRunDriver
  │  WIRE[toolName] → identifier + apiName
  │  本机卡片走 lobe-local-system Inspector
  │  沙箱卡片走 lobe-cloud-sandbox Inspector
  │  state.files[].url → /files/* → Gateway FileStore
  │  本机 outputs_dir 已由 Gateway 经 sidecar 读回并发布
  │
拆除  finalize_run：拆沙箱会话；不删本机磁盘
```

前端要动的只有三处，都挂在已有补丁上，不换聊天协议：

| 点 | 现状 | 用上架构之后 |
|---|---|---|
| 发 Run | `LcaRunDriver` POST `/lca-api/runs` | 可选 `device_id` / `plane` / `extra_plane`。一台设备且无沙箱时自动当主环境 |
| 投影工具卡片 | `WIRE` 几乎全是 `lobe-cloud-sandbox` | `local_*` → `lobe-local-system`（`write_file_local` 已是先例） |
| 显示「在哪」 | Host Console / Presence | `GET /lca-api/context` 回 **已绑** `PlaneBindings` + **在线候选**（未绑的 sidecar 只出现在候选里） |

HITL：暂停时 `session.bindings` 仍在；续跑不重解析 Presence。用户换机或换主环境 = 下一条消息、下一次 Run。

人用终端（`/console/*`）继续走 Presence，不进 Agent 工具清单。

---

## 5. 全流程契约（一次 Run）

```
附件入库 FileStore
    → 解析并冻结 PlaneBindings（选出主环境）
    → 按主环境组工具 + 注入对应 system role
    → 附件落到已绑环境
    → Agent 调工具 → 对应适配器 → 传输
    → Observation（content/state/error）→ Journal / SSE / UI
    → 产物可下载
    → HITL 则暂停；续跑复用同一绑定
    → finalize 拆沙箱会话；不拆本机磁盘
```

### 5.1 何时绑定、主环境怎么选

1. `execute_run` **先** `resolve_plane_bindings(run)`，写入 `session.bindings`，此后只读。
2. **再** `build_default_tools(bindings=...)` / `build_solo_agent(..., bindings)`。禁止在组装时再 `resolve_sandbox()` 偷看 Presence。
3. HITL `WAITING_INPUT` 续跑：用 `session.bindings`，不重新解析。设备已离线 → 本机 op 结构化失败 `device_offline`，不换主环境。
4. Team 一次 Run 共用一份绑定；成员不各自选环境。
5. 用户换机或换主环境 = 下一次 Run。

今天 `build_g2a_chat_tools()` / `LLMTeamCaster` 在组装时自己 `resolve_sandbox()`，必须改成吃绑定。这是时序的根。

**选出主环境（默认恰好一张脸）：**

记 `M` = §5.2 得到的机器候选（可能为空），`S` = `resolve_sandbox()`（仅 Onlyboxes，可能为空）。

| 请求 | 结果 |
|---|---|
| `plane` 显式 | 该种类必须有候选，否则 Run 失败。它是 `primary` |
| 无 `plane`，仅 `S` | `primary = S` |
| 无 `plane`，仅 `M` | `primary = M` |
| 无 `plane`，`M` 与 `S` 都有 | **`primary = S`。`M` 留在候选，不进绑定。** 在线 sidecar 不得偷走浏览器会话的沙箱主环境 |
| 两者都无 | `primary = None`。无 computer exec |
| `extra_plane` 显式 | 该种类必须有候选、且与 `primary.kind` 不同，否则 Run 失败。写入 `secondary` |
| 无 `extra_plane` | `secondary = None` |

`device_id` 只参与选出 `M`（§5.2）。它**不**隐含 `plane=machine`，除非请求同时带了 `plane=machine`，或沙箱候选为空（上表「仅 M」）。

禁止静默把两个候选都写进绑定。禁止「两边都在就两套脸」。

### 5.2 设备怎么选（机器候选）

Presence 只回答「谁在线」。选谁成为机器候选 `M`：

| 在线 sidecar | 候选 |
|---|---|
| 0 | `M = None`。若主环境需要机器，prompt 可提示启动 sidecar。 |
| 1 | 那一台（吸取 LobeHub「只有一台就激活」）。 |
| N | 请求显式 `device_id`；否则该用户上次成功的仍在线设备；再否则 `M = None`，prompt 列出在线设备，请用户指定。 |

禁止静默绑第一台。禁止 Run 中途改 `bindings.primary` 或 `bindings.secondary`。

断线：

- 当前 op：传输错误，`retryable=true`，文案带 `PlaneRef.label`。
- 后续该环境 op：同一错误。不自动改绑到另一种类。
- 后台命令：传输不可达则标失败。
- 另一环境不受影响。

### 5.3 附件落到哪

聊天附件先进 FileStore（现状 ingest）。绑定之后：

| 已绑环境 | 落点 | 说明 |
|---|---|---|
| sandbox | `/mnt/data/<basename>` | 保持 ADR-0046 / LobeHub uploaded-files。`SandboxRuntime.ensure_ready` 负责。 |
| machine | `{root}/<basename>` | sidecar/传输 `write` 真实文件。Prompt 写真实路径。 |

默认只落 **primary**。`secondary` 有值才再落一份（同一 FileStore 字节）。未绑的候选环境不落、不假装已在。

上限与沙箱相同：单文件 100MB、最多 50 个。失败 = 该环境未就绪；机器拷失败不得假装文件已在。

本机**不**把附件写成 `/mnt/data/...`。

### 5.4 产物怎么变成用户能下的文件

| 环境 | Agent 怎么写 | 用户怎么拿到 |
|---|---|---|
| sandbox | `/mnt/data/outputs/...`；可用 `export_file` | harvest + `export_file` → FileStore URL（现状） |
| machine | `{outputs_dir}/...` | 写/跑成功后，对 `outputs_dir` 下新文件经传输读回，发布进 FileStore。远程盘必须走 sidecar，禁止假定 Gateway 本机有该路径。 |

机器脸 **不** 挂 `export_file`（吸取 LobeHub）。Web UI 需要 URL，所以我们比 LobeHub 多一步自动发布——这是产品差异，不是再造一张 Agent 工具。

`root` 内、`outputs_dir` 外的文件：不自动发布。Agent 应写到 `outputs_dir`。

### 5.5 本机可写根（与真路径同一批）

吸取 `pathScopeAudit`，对齐 L2 HITL，不新造安全对象：

- 相对路径相对 `PlaneRef.root`。
- 绝对路径按该 OS 原样用。
- 目标在 `root` 内，或平台临时目录（POSIX `/tmp`，Windows `%TEMP%`）：直接执行。
- 目标在其外：`ApprovalPendingError`，用户批过才执行。
- `home` 只帮助模型理解口语位置；写到 `home` 但越出 `root` 仍走 HITL。
- 拒绝 remap。拒绝静默改写到 `root` 下。
- 破坏性命令继续走现有 `DegradationPolicy`。

沙箱环境：容器即硬隔离；guest 脚本已限制在 `/mnt/data`。不重复一套 HITL。

### 5.6 Skill 跑哪张环境

Skill 不是第三环境。`run_skill_script` 必须绑在**一张** `PlaneRef` 上。

选择，按序第一条命中：

1. 调用方显式指定（`activate_skill(plane=...)` 或脚本参数）。
2. 这次调用由某张 computer 脸触发 → 那张脸的 `PlaneRef`。
3. `bindings.primary`。
4. 无主环境 → 结构化失败，不猜测。

禁止写死「双绑默认 sandbox」。禁止一次脚本跨两套路径。  
officecli 在本机跑时，`{workspace}` / `{outputs_dir}` 必须是渲染后的真路径。

---

## 6. 工具面与 WIRE

今天 `gateway/runs/wire.py` 把几乎全部 computer 工具投到 `lobe-cloud-sandbox`，即使 Host 在跑。已有例外：`write_file_local` → `lobe-local-system`。按这个模式铺开。

`local_*` 是扁平 function calling 的防腐前缀。LobeHub 侧仍是同一 `apiName`，靠 identifier 区分。不要在 prompt 里再发明第三套名字。

**沙箱脸**（该 `PlaneRef.kind=sandbox` 已绑时注册）

| LCA 名 | LobeHub identifier / api |
|---|---|
| `execute_code` | `lobe-cloud-sandbox` / `executeCode` |
| `run_command` … `glob_files` | 同上，现有 WIRE |
| `export_file` | `lobe-cloud-sandbox` / `exportFile` |

**机器脸**（该 `PlaneRef.kind=machine` 已绑时注册）

| LCA 名 | LobeHub identifier / api |
|---|---|
| `local_run_command` | `lobe-local-system` / `runCommand` |
| `local_list_files` | `listFiles` |
| `local_read_file` | `readFile` |
| `local_write_file` | `writeFile`（取代/合并 `write_file_local`） |
| `local_edit_file` | `editFile` |
| `local_search_files` | `searchFiles` |
| `local_move_files` | `moveFiles` |
| `local_grep_content` | `grepContent` |
| `local_glob_files` | `globFiles` |
| `local_get_command_output` | `getCommandOutput` |
| `local_kill_command` | `killCommand` |

机器脸 **没有** `execute_code` / `export_file`。

默认只注册 **primary** 那一张脸。`secondary` 有值才注册第二张，描述与短声明写清路径不可混用。

都没有：无 computer exec；保留 FileStore `write_file` + skills（现状降级）。

结果继续 `ComputerOpResult`：`content` 给 LLM，`state` 给 UI（`pluginState`），`error` 两边都看。截断、后台 `commandId` 走 `state` / `Observation.extra`。不新造 `OpResult` / Viewport / EnvState。

---

## 7. 传输、OS、解析、适配器

```
machine  ── sidecar（已有 host/ + Presence）
         ── ssh（允许，后做）
         ── inproc（测试）

sandbox  ── onlyboxes（已有）
         ── e2b/modal（未来新 adapter，不改 PlaneKind）
```

Windows：sidecar 的 `platform=win32`，`local_shell` 内部分发。没有 `WindowsContext`。  
SSH：`MachineTransport`。没有 `SSHContext`。

`resolve_sandbox()` **只** 返回真正的沙箱。`HostSandbox` 不再实现 `Sandbox`；它是 `MachineTransport`。  
`resolve_machine()` 从 Presence 按 §5.2 选出设备，得到机器候选 `PlaneRef`。  
`resolve_plane_bindings()` 按 §5.1 从候选和请求得到冻结的 `PlaneBindings`。

适配器（L0，不是 contracts 行为类）：

```python
class ComputerOps(Protocol):
    async def list_files(...) -> ComputerOpResult: ...
    async def read_file(...) -> ComputerOpResult: ...
    # write / edit / search / move / grep / glob
    # run_command / get_command_output / kill_command


class MachineComputer:
    def __init__(self, plane: PlaneRef, transport: MachineTransport): ...


class SandboxComputer:
    def __init__(self, plane: PlaneRef, runtime: SandboxRuntime): ...
    async def execute_code(...) -> ComputerOpResult: ...
    async def export_file(...) -> ComputerOpResult: ...
```

`MachineComputer` 只走 `transport.computer_op`。  
`SandboxComputer` 只走 guest 脚本 + `SandboxRuntime`。  
禁止一个对象同时持有两种传输并用 `kind` 分发。禁止 `ComputerRuntime(sandbox=HostSandbox)`。

---

## 8. 和现状的映射

| 今天 | 纠偏后 |
|---|---|
| `ExecutionSurface(backend, guest_root)` | `PlaneRef`；删除 `guest_root` |
| `resolve_sandbox()` 可返回 Host | 只返回 Onlyboxes |
| `set_sandbox_resolver(HostSandbox)` | `resolve_machine()` → 候选；`resolve_plane_bindings()` → 冻结 |
| `HostSandbox` 冒充 `Sandbox` | `MachineTransport` |
| `ComputerRuntime._maybe_local` | 删除。两个适配器 |
| `rewrite_guest_refs` | 删除 |
| `COMPUTER_WORKSPACE_ROOT = "/mnt/data"` | 仅沙箱常量 |
| 一份 `environment_note` 解释 remap | `machine_system_role.md` + 现有沙箱模板；只注入主环境 |
| 13 个工具全投 `lobe-cloud-sandbox` | 已绑的机器脸投 `lobe-local-system` |
| 两边都在就当一种沙箱 | 默认一张主脸；第二脸显式 |
| ADR-0050 / `Sandbox` Protocol | 不变，仅沙箱 |
| `RunWorkspace` | 不变；不承担磁盘根 |

分层：`PlaneRef` / `PlaneBindings` 在 contracts；解析与适配器在 L0；gateway 注入 Presence 与 `session.bindings`。L0 factory 顶层不 import gateway。

---

## 9. 面向未来

| 要加 | 落点 | 不改 |
|---|---|---|
| E2B / Modal / microVM | 新 `Sandbox` adapter | `PlaneKind`、工具名 |
| 无 sidecar 的远程机 | SSH `MachineTransport` | 不新增种类 |
| 远程 / 本机 Windows | sidecar + `platform=win32` | 不新增种类 |
| 多设备 | §5.2 + 请求 `device_id` | 不把列表塞进 `PlaneRef` |
| 一次 Run 同时用两环境 | 请求 `extra_plane` | 不改默认；不扩 `PlaneKind` |
| 多用户隔离 | 解析时选不同 `root` + §5.5 | 不造 guest 命名空间 |
| 浏览器 Computer Use | 新 embodiment | 不扩 `PlaneKind` |
| 截断 / 长任务 | constants + `BackgroundCommandRegistry` | 不改身份对象 |
| Daytona 式可暂停盘 | 沙箱 adapter 生命周期 | 仍是 `sandbox` |
| SRT 包命令 | MachineTransport 加固 | 不进 `PlaneRef` |

新环境要么是 `Sandbox` 实现，要么是 `MachineTransport`。新身体不是新 `PlaneKind`。

---

## 10. 拒绝清单

1. 禁止 `ExecutionContext.execute()`。
2. 禁止 Host 实现 `Sandbox`。
3. 禁止任何 `/mnt/data` ↔ 本机路径 remap。
4. 禁止 SSH / Windows / 浏览器 CU 与 machine/sandbox 并列。
5. 禁止单例 auto 吞掉一种环境。
6. 禁止 Viewport / Job / EnvState / Capability 进 `PlaneRef`。
7. 禁止第四套 Result。
8. 禁止 contracts 里写系统用户名或 npm 安装。
9. 禁止 Run 中途改 `primary` / `secondary`。
10. 禁止机器脸挂 `execute_code` / `export_file`。
11. 禁止本机可写根留到「以后再做」。
12. 禁止默认双绑；禁止「两边都在就两套脸」。
13. 禁止一个 Computer 类按 `kind` 分发；禁止 `_maybe_local`。
14. 禁止 Skill 写死默认 sandbox。
15. 禁止 `PlaneRef` / `PlaneBindings` 带行为方法。

---

## 11. 落地顺序

中间态允许旧 Host 暂时能跑，不允许继续 remap，不允许 Host-as-Sandbox 当目标态，不允许把双绑做成默认路径。

### PR 1 — 身份、主环境冻结、组工具吃绑定

- `PlaneRef` / `PlaneKind` / `PlaneBindings`（`primary` + `secondary`）
- `resolve_sandbox()` 不再接受 Host
- `resolve_machine()` + §5.2
- `resolve_plane_bindings()` + §5.1
- `execute_run` 先绑再组工具；`session.bindings` 冻结
- Journal 记 `primary`/`secondary` 的 `kind` + `id` + `root` + `platform`
- `ExecutionSurface` 废弃

### PR 2 — 两个适配器、机器真路径、可写根 HITL、主环境附件

- 删 `rewrite_guest_refs` 与 `_maybe_local`
- `HostSandbox` 降为 `MachineTransport`
- `MachineComputer` / `SandboxComputer`
- 主环境是机器时：`local_*` + WIRE → `lobe-local-system` + 本机 prompt
- 主环境是沙箱时：现有脸；模板去掉 remap 句子
- 附件只写入 **primary** 的真实根
- `root` 外路径 HITL
- 负面：本机访问 `/mnt/data` 失败且不翻译

### PR 3 — 机器产物发布、前端「在哪」

- 机器 `outputs_dir` 自动发布 FileStore
- `/lca-api/context` 返回已绑 `PlaneBindings` + 在线候选
- 下载：沙箱 harvest；机器经 sidecar 读
- 请求字段 `plane` / `extra_plane` / `device_id` 接到 LcaRunDriver（双绑 UI 可先不画，字段先通）

### PR 4 — 显式第二环境（需要产品开口再做）

- `extra_plane` 真正注册第二张脸
- 附件双落
- Skill §5.6 的「调用脸优先」
- 短声明 prompt

### PR 5 — 需要时再做

- SSH `MachineTransport`
- sidecar 安装 UX
- 命令级 SRT（LobeHub `device-sandbox`）

---

## 12. 验证

### 功能

- [ ] 仅 Host：主环境 machine；`local_*` + 真实 `root`；prompt 无 Cloud Sandbox / `/mnt/data`
- [ ] 仅 Onlyboxes：主环境 sandbox；现有沙箱工具 + `/mnt/data`；附件在 `/mnt/data/<name>`
- [ ] 两者都在、无 `extra_plane`：主环境 sandbox；**只有**沙箱脸；sidecar 仅出现在 `/context` 候选
- [ ] `plane=machine` 且有设备：主环境 machine；沙箱未绑；附件在 `{root}/<name>`
- [ ] `extra_plane` 显式：两套脸，WIRE 分别投 `lobe-local-system` / `lobe-cloud-sandbox`
- [ ] 本机写到 `outputs_dir` 的文件在聊天里可下（远程走 sidecar）
- [ ] 一台设备自动成为机器候选；多台无 `device_id` 不静默挑第一台
- [ ] HITL 续跑不换绑定
- [ ] 本机越 `root` 的写/跑进入审批
- [ ] Skill 无显式、无调用脸 → 走 `primary`，不写死 sandbox
- [ ] Journal 能按主环境过滤

### 负面

- [ ] 本机访问 `/mnt/data` → 不存在，无 remap
- [ ] 仅 Host 在线时 `resolve_sandbox()` 为 `None`
- [ ] 两边都在、无 `extra_plane` → `secondary is None`，清单无 `local_*`
- [ ] 无主环境 → 无 computer exec
- [ ] 无 `rewrite_guest_refs`，无 `_maybe_local`
- [ ] 机器清单里没有 `execute_code` / `export_file`
- [ ] Run 中途 Presence 换成另一台设备，绑定不变
- [ ] `ComputerOps` 实现类不出现 `if plane.kind` / `if bindings.primary.kind`

### 架构守卫

- [ ] `PlaneKind` 只有 `machine` | `sandbox`
- [ ] `PlaneRef` / `PlaneBindings` 无行为方法
- [ ] 实现 `Sandbox` 的类型不来自 `gateway.host_sandbox`
- [ ] `host/paths.py` 无 guest 翻译
- [ ] 不存在同时持有 `MachineTransport` 与 `SandboxRuntime` 并按 kind 分发的类
- [ ] `WIRE`：`local_*` → `lobe-local-system`；未加前缀 computer 名 → `lobe-cloud-sandbox`

---

## 13. Key Decisions

1. **两种产品环境，不是四种 backend。** 分类对齐 LobeHub 与业界。
2. **一次 Run 一个主环境。** `PlaneBindings.primary` 回答附件 / Skill / prompt / 默认脸。`secondary` 仅显式。
3. **身份是纯数据。** 避开已有 `RunWorkspace`。执行在两个适配器里，不在身份对象上。
4. **`/mnt/data` 只属于沙箱。** Host 不再伪装。
5. **操作面对齐 LobeHub 的继承切分，不是一份类。** `ComputerOps` + `MachineComputer` + `SandboxComputer`。删除 `_maybe_local`。
6. **`local_*` 是扁平工具表的防腐层。** 前端仍靠 LobeHub identifier。
7. **`export_file` / `execute_code` 仅沙箱。** 本机产物靠自动发布，因为我们是 Web UI。
8. **绑定开工冻结。** 比 LobeHub 中途 `activateDevice` 更可复现。
9. **主环境是机器时，附件暂存到真 `root`。** 适合浏览器上传。未绑环境不落。
10. **可写根 HITL 与真路径同一批。** `home` 只进 prompt。
11. **Skill 跟调用脸，否则跟主环境。** 不写死 sandbox。
12. **两边都在线时默认仍用沙箱。** sidecar 不得偷走主环境。要本机或双绑，请求里说。
13. **SSH / Windows 是传输和 OS。** ADR-0050 保留。

---

## 14. 仍开放（运维/产品，不挡本架构）

1. 机器默认 `root` 用 `LCA_HOST_ROOT` 还是用户指定目录——配置。
2. 多租户是否做系统用户——独立方案。
3. sidecar 用什么命令安装——独立方案。
4. 多设备时前端是设备选择器还是只靠 `device_id`——UI，规则已在 §5.2。
5. 何时在 UI 上露出「也用本机 / 也用沙箱」——产品；协议字段是 `extra_plane`，默认不做。
