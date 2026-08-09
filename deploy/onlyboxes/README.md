# Onlyboxes pythonExec 镜像（LCA）

生产 worker（`onlyboxes-worker-docker.service`）通过环境变量挂载镜像：

```text
WORKER_PYTHON_EXEC_DOCKER_IMAGE=onlyboxes-python-local:3.11
```

本目录是该镜像的**正规定义**（ADR-0044）：含数据分析常用包，避免运行时 `pip install`。

## 预装包

与 `SANDBOX_PREINSTALLED_PYTHON_PACKAGES`（`lca/contracts/models/core/sandbox.py`）一致：

| 包 | 用途 |
|---|---|
| pandas / numpy | 表格与数值 |
| openpyxl / xlsxwriter | xlsx 读/写 |
| matplotlib / seaborn / pillow | 图表与图像（镜像预装文泉驿正黑 + `MATPLOTLIBRC`，中文坐标/标题不缺字） |
| scipy | 科学计算 |
| requests | HTTP |
| tabulate | 文本表 |

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
