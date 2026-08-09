# ADR-0044: 代码沙箱适配器 — Onlyboxes（console + docker worker）

## 状态

Accepted（2026-08 修订：退役 E2B / microsandbox / Mock 生产路径）

## 背景

Agent 需要执行模型生成的代码（数据分析、图表、文件变换），但不能在宿主进程里
裸 `exec`。仓库最初提供三条后端（E2B 云、microsandbox 本地 microVM、进程内 Mock），
在本机环境中：

- microsandbox 依赖 `/dev/kvm`，嵌套虚拟化不可用时无法启动；
- E2B 依赖外部 API key，与「本机可控」目标冲突；
- Mock 无隔离，禁止作为生产假能力。

本机已部署 **Onlyboxes**（console `:8089` + worker-docker），提供
`pythonExec` / `terminalExec` REST 与 MCP。

## 决定

### 一、唯一生产后端：Onlyboxes

- `Sandbox` Protocol + `SandboxResult` / `SandboxFile` 不变（contracts 纯数据）。
- 实现：`lca.layer0_infra.sandbox.onlyboxes_adapter.OnlyboxesSandboxAdapter`
- 工厂：`resolve_sandbox()` 仅在配置齐全时返回 Onlyboxes，否则 `None`（省略工具）。

环境变量：

| 变量 | 含义 |
|---|---|
| `ONLYBOXES_BASE_URL` | console HTTP 根，如 `http://127.0.0.1:8089` |
| `ONLYBOXES_ACCESS_TOKEN` | 控制台签发的 access token（`obx_…`） |
| `LCA_SANDBOX_BACKEND` | 可选；仅 `onlyboxes` 受支持 |

### 二、执行与文件契约

- 执行通道：`POST /api/v1/tasks`，`capability=pythonExec`，`mode=sync`
- 输入挂载：bootstrap 将 `files` 写入 guest `/mnt/data/<name>`（ADR-0046）
- 产出收集：user code 写 `/mnt/data/outputs/`；bootstrap 在 stdout 末尾发射
  base64 artifact 块，adapter 解析为 `generated_files`
- 工具面 `SandboxCodeTool`（`run_sandbox_code`）不变

### 三、明确退役

| 已删除 | 原因 |
|---|---|
| `E2BSandboxAdapter` / `sandbox-e2b` | 云依赖，本机不使用 |
| `LocalSandboxAdapter` / microsandbox | 需 KVM，本机不可用 |
| `MockSandboxAdapter` 生产接线 | 禁止静默假能力；单测用测试内联 Fake |

### 四、运维前置

1. Onlyboxes console 在线
2. 至少一个 **online** worker-docker（`pythonExec` 能力）
3. 控制台创建 access token 写入 `.env`
4. **pythonExec guest 镜像**使用本仓库定义的 data baseline（见下节）

### 五、pythonExec 镜像 baseline（预装包）

Worker 环境变量示例：

```text
WORKER_PYTHON_EXEC_DOCKER_IMAGE=onlyboxes-python-local:3.11
```

镜像定义与构建入口（正规路径，禁止只在 `/tmp` 临时 Dockerfile 上改）：

| 路径 | 作用 |
|---|---|
| `deploy/onlyboxes/Dockerfile.python` | guest 镜像 |
| `deploy/onlyboxes/requirements-python.txt` | 预装包清单 |
| `deploy/onlyboxes/matplotlibrc` | 默认字体（CJK + `axes.unicode_minus`） |
| `deploy/onlyboxes/build-python-image.sh` | 构建 + import / CJK smoke |
| `deploy/onlyboxes/README.md` | 运维说明 |

预装清单与 contracts 常量 `SANDBOX_PREINSTALLED_PYTHON_PACKAGES`、
`SandboxCodeTool.description` **三方对齐**：

`pandas` · `numpy` · `openpyxl` · `xlsxwriter` · `matplotlib` · `seaborn` ·
`pillow` · `scipy` · `requests` · `tabulate`

构建默认走清华 PyPI（`PIP_INDEX_URL` / `UV_INDEX_URL`），不依赖宿主机 HTTP 代理。
缺包策略：**改 requirements 并重建镜像**；运行时 `pip install` 仅作临时兜底
（受 Onlyboxes `wait_ms` 上限约束，不作为默认路径）。

```bash
./deploy/onlyboxes/build-python-image.sh
# 一般无需重启 worker：下次 pythonExec 会 docker run 新容器
# 异常时: sudo systemctl restart onlyboxes-worker-docker
```

## 后果

- 正向：本机 Docker worker 可执行代码；与附件挂载 / 产物下载同一工具面；
  数据分析常用包预装，避免 `ModuleNotFoundError: pandas` 类确定性失败被重试 3 次。
- 负向：依赖 Onlyboxes 进程与 worker 镜像体积；增包需走 `deploy/onlyboxes` 重建。
- 测试：HTTP 层用 mock client；工具层用测试内联 Sandbox，不引入生产 Mock 适配器。
