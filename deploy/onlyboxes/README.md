# Onlyboxes sandbox images (LCA + LobeHub terminalExec)

LobeHub 原生只走 **terminalExec**（`POST /api/v1/commands/terminal`）。Worker 通过
`WORKER_TERMINAL_EXEC_DOCKER_IMAGE` 选择终端运行时镜像；`pythonExec` 镜像为 Legacy。

## 正规路径（terminalExec — 当前生产通道）

Guest 磁盘根 **必须是 `/mnt/data`**（`GuestLayout.onlyboxes()`、LobeHub
`SANDBOX_UPLOADED_FILES_DIR`、ADR-0046）。镜像 `WORKDIR` 即该根；**不是**
上游 `onlyboxes-runtime` 默认的 `/workspace`。构建后 `smoke-guest-layout.sh`
会校验此契约。

| 路径 | 作用 |
|---|---|
| `deploy/onlyboxes/Dockerfile.terminal` | terminal 运行时（基于 `onlyboxes-runtime` + 数据栈） |
| `deploy/onlyboxes/build-terminal-image.sh` | 构建 `onlyboxes-terminal-local:lca` |
| `deploy/onlyboxes/configure-terminal-runtime.sh` | 写入 systemd drop-in 并重启 worker |

```bash
# 默认使用 onlyboxes-terminal-local:lca（含 officecli，ADR-0054）
./deploy/onlyboxes/build-terminal-image.sh   # 首次 / 升级 officecli
./deploy/onlyboxes/configure-terminal-runtime.sh
```

**注意**：`coolfan1024/onlyboxes-runtime:default` / `:lobehub` **不含** `officecli`。
LCA 生产路径必须用本目录构建的 `onlyboxes-terminal-local:lca`（或自建并设置
`ONLYBOXES_TERMINAL_IMAGE=...`）。systemd drop-in 必须写在
`/etc/systemd/system/onlyboxes-worker-docker.service.d/`（带 `.service.d`），
写到 `onlyboxes-worker-docker.d/` 会被 systemd 静默忽略。

## Legacy（pythonExec — 已不由 LCA 代码使用）

Worker 环境变量示例（保留供对照，LCA adapter 已不调用）：

```text
WORKER_PYTHON_EXEC_DOCKER_IMAGE=onlyboxes-python-local:3.11
```

## 预装包

与 `SANDBOX_PREINSTALLED_PYTHON_PACKAGES`（`lca/contracts/models/core/sandbox.py`）一致：

| 包 | 用途 |
|---|---|
| pandas / numpy | 表格与数值 |
| openpyxl / xlsxwriter | xlsx 读/写 |
| matplotlib / seaborn / pillow | 图表与图像（镜像预装文泉驿正黑 + `MATPLOTLIBRC`，中文坐标/标题不缺字） |
| fonts-noto-cjk / fonts-wqy-zenhei | **CJK 字体**（reportlab 中文 PDF；路径见 Dockerfile；**禁止运行时 curl 字体**） |
| scipy | 科学计算 |
| requests | HTTP |
| tabulate | 文本表 |
| python-docx / reportlab / fpdf2 / pypdf | 文档生成（DOCX/PDF） |
| **officecli**（钉版本，ADR-0054） | Word/Excel/PPT 统一 CLI；`OFFICECLI_SKIP_UPDATE=1` |

Office 平面：`install-officecli.sh` 在镜像构建时安装固定版 binary；agent **禁止**运行时 curl 安装。
升级：改 `OFFICECLI_VERSION` 后重建 terminal 镜像并跑 `build-terminal-image.sh` smoke。

terminal 镜像重建后须 **清掉旧 terminalExec session 并重启 worker**，否则会继续跑无字体的 `:default` 容器：

```bash
./deploy/onlyboxes/build-terminal-image.sh
./deploy/onlyboxes/configure-terminal-runtime.sh
# 或手动：
docker ps -q --filter ancestor=coolfan1024/onlyboxes-runtime:default | xargs -r docker rm -f
sudo systemctl restart onlyboxes-worker-docker
```

## 构建

```bash
./deploy/onlyboxes/build-python-image.sh
# 或自定义 tag：
ONLYBOXES_PYTHON_IMAGE=onlyboxes-python-local:3.11 ./deploy/onlyboxes/build-python-image.sh
```

构建默认使用清华 PyPI 源（`PIP_INDEX_URL` / `UV_INDEX_URL`），不依赖宿主机代理。

## 生效

- 每次 `pythonExec` 一般会 `docker run --rm` 新容器，**重建同 tag 后下一次任务即用新镜像**。
- 若 worker 缓存了旧层异常，可重启：

```bash
sudo systemctl restart onlyboxes-worker-docker
```

## 缺包策略

1. **优先**：把包写入 `requirements-python.txt` 并重建镜像（本目录）。
2. **临时**：用户代码内 `uv pip install --system -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`（慢、且受 `wait_ms` 约束，不推荐作为默认路径）。
3. **禁止**：依赖 SafeExecutor 对 `ModuleNotFoundError` 盲重试——确定性失败重试无意义。
