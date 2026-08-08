# ADR-0044: 代码沙箱适配器 — Protocol + 多后端（E2B / local microVM / Mock）

## 状态

Accepted

## 背景

Agent 需要执行模型生成的代码（数据分析、图表、文件变换），但不能在宿主进程里
裸 `exec`：这既是安全边界，也是能力边界（依赖库、超时、资源限额）。

本仓库已通过 `Sandbox` Protocol（`lca.contracts.protocols`）与纯数据契约
（`SandboxResult` / `SandboxFile` / `SandboxOutputDelta`）把「隔离执行」与上层
工具 / journal 叙事解耦。实现侧最初只有两条：

| Adapter | 隔离 | 用途 |
|---|---|---|
| `E2BSandboxAdapter` | 云端 Firecracker microVM | 生产默认（需 `E2B_API_KEY`） |
| `MockSandboxAdapter` | **无**——进程内受限 `exec` | 单元测试 / 显式离线 demo |

缺的一环很清楚：**真正有隔离能力、但不依赖云端 E2B 账号的本地后端**。同时
Mock 容易被误解为「本地沙箱」——它不是安全边界，只是测试替身。

选型对比（不采纳的路子也写清楚，避免重复踩坑）：

| | microsandbox | Dify Sandbox | E2B 自托管 (e2b-dev/infra) |
|---|---|---|---|
| 隔离 | microVM (libkrun) | seccomp + namespace | Firecracker microVM |
| 部署 | 嵌入式库，无 daemon | docker-compose sidecar | Terraform + Nomad + Consul |
| 硬件 | Linux KVM / macOS Apple Silicon | 任意 Docker 主机 | 裸金属 / 嵌套虚拟化，运维重 |
| 结论 | **本地主力** | **无 KVM 时的 HTTP 兜底（后续）** | 不是「本地沙箱」，不采纳 |

明确不建议：自己拼 gVisor / nsjail / per-task Docker——Dify / Judge0 的公开复盘
表明这是高 CVE 与高配置债路径。

## 决定

### 一、统一 Protocol，多 Adapter 实现

- contracts 层只保留 `Sandbox` Protocol + `SandboxResult` / `SandboxFile`。
- 实现全部落在 `lca.layer0_infra.sandbox`：
  - **E2B**（生产云）：`E2BSandboxAdapter`，可选组 `sandbox-e2b`
  - **Local**（本地 microVM）：`LocalSandboxAdapter`（microsandbox），可选组 `sandbox-local`
  - **Mock**（测试替身）：`MockSandboxAdapter`，零可选依赖，**非安全边界**
- 执行期 stdout/stderr 经共享 `SandboxStreamEmitter` 发射 `SandboxOutputDelta`
  （journal 唯一发射点），与 ADR-0037 叙事平面一致。
- 工具面 `SandboxCodeTool`（`run_sandbox_code`）只依赖 Protocol，不感知后端。

### 二、显式后端选择，禁止静默假能力

`resolve_sandbox()` 选择顺序：

1. `LCA_SANDBOX_BACKEND=local` → `LocalSandboxAdapter`（不要求 E2B key）
2. `LCA_SANDBOX_BACKEND=mock` 或 `prefer_mock=True` → `MockSandboxAdapter`
3. 有 `E2B_API_KEY`（或 `backend=e2b` 且有 key）→ `E2BSandboxAdapter`
4. 否则 → `None`，**调用方省略沙箱工具**（对齐 ProductionLLMResolver：no fake capability）

生产默认接线（`build_default_tools`）不在缺 key 时静默挂 Mock。Mock 仅用于
单元测试与显式 offline demo（`include_sandbox_mock=True`）。

### 三、可选依赖组，核心安装面不动

```toml
sandbox-e2b = ["e2b-code-interpreter>=1.0"]
sandbox-local = ["microsandbox>=0.6,<0.7"]
```

Adapter 内用 `importlib` 延迟导入；缺依赖时返回结构化 `SandboxResult.error`，
不在 import 期炸掉进程。

### 四、Local 后端约束（MVP）

- 语言：与 E2B MVP 一致，仅 Python
- 输入挂载根：`/mnt/data`（`SANDBOX_MOUNT_ROOT`，全后端一致，工具路径可移植）
- 默认网络：`Network.none()`（本地未信任代码默认断网；需要联网时再显式放宽）
- microsandbox 0.x 仍为 beta：版本锁在 `>=0.6,<0.7`，集成测试可 mock SDK

### 五、Dify Sandbox 作为规划中的无 KVM 兜底

当目标机器无 KVM / 嵌套虚拟化时，microsandbox 起不来。后续可增加
`LCA_SANDBOX_BACKEND=dify`：HTTP client → `langgenius/dify-sandbox` sidecar
（Python/Node、生产验证久、无 native SDK）。本 ADR 接受该方向，**本迭代不
实现**——等有明确 CI / 笔记本无 KVM 需求再加 adapter，避免过早引入第二运行时。

### 六、明确不采纳

- E2B 自托管：应用零改动但运维是「自建 E2B 云」，不是本地开发沙箱。
- 自研 gVisor/nsjail 拼装：重复造轮子，安全与配置债高。
- 把 Mock 当生产 / 本地沙箱兜底：破坏「no fake capability」哲学。

## 后果

### 正向

- 无 E2B 账号时仍可显式选择真实隔离后端（local microVM）。
- Protocol 边界保持：上层与 journal 不绑定具体供应商。
- Mock 定位写清，降低「假沙箱」误用风险。
- 可选依赖组不膨胀默认安装体积。

### 负向 / 风险

- microsandbox 0.x API（尤其 `exec_stream` 事件字段）可能变——靠版本上界 +
  适配器内兼容逻辑缓解。
- 本地 microVM 需要虚拟化硬件；无 KVM 环境在 Dify adapter 落地前只能用 E2B
  或（显式）Mock。
- 多后端意味着 factory 与文档需持续同步 `LCA_SANDBOX_BACKEND` 语义。

## 关联

- ADR-0004 Protocol-First 可插拔
- ADR-0037 Journal-as-Truth（`SandboxOutputDelta` 叙事）
- ADR-0043 文件产物 / FileStore（沙箱生成文件进同一产物通道）
