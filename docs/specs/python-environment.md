# LCA Python 环境

LCA 后端运行在 `/opt/lca/venv`(系统级 venv)。`./scripts/lca-ops` 与 `python -m lca_kernel serve` 都必须用这个 venv 的 python,否则会触发"日志为空 + 立即退出"的鬼火问题。

## 三条铁律

1. **运行时只能用 `/opt/lca/venv/bin/python`。** 不论是 lca-ops 还是 lca_kernel serve。
2. **装包必须用 `/opt/lca/venv/bin/pip3`**(或 `python -m pip`),**不**用 `pip` / `pip3` / `uv pip` —— 后者装到 `/home/lichao/.local/`(pip 3.11 用户级)或 `~/.cache/uv`(uv 缓存),跟 venv 完全隔离。
3. **新依赖 vendored**:LCA 把 `cordis`(`vendor/cordis/`)等 vendored 包当一等公民。新增 vendored 依赖必须 `pip install -e vendor/<pkg>`,不要从 PyPI 拉。

## 为什么

`./scripts/lca-ops` 的 shebang 是 `#!/usr/bin/env bash`,内部 `python -m lca.infrastructure.cli.cli`,**取决于当前 `$PATH` 的 python3**。`/opt/lca/venv/bin/python3` 在 `$PATH` 中,所以默认走 venv。lca-ops 启动时 import 整个 LCA 模块图(包括 cordis / cryptography / pydantic / lca_kernel.boot) — 任何依赖缺失都会在 lca-ops 启动瞬间 raise,表现为:

- `./scripts/lca-ops <anything>` 报 `ModuleNotFoundError`
- `python -m lca_kernel serve` 死锁式退出(traceback 走 stderr 缓冲,前台看起来无输出 + 不退出,后台看似"还在启动")

## 故障排查

| 症状 | 真因 | 修 |
|---|---|---|
| `ModuleNotFoundError: No module named 'cordis'` | venv 缺 vendored cordis | `/opt/lca/venv/bin/pip3 install -e vendor/cordis` |
| `ModuleNotFoundError: No module named 'cryptography'` | venv 缺 cryptography | `/opt/lca/venv/bin/pip3 install cryptography` |
| lca-ops 起来但 kernel spawn 失败,`/tmp/lca-kernel.log` 无新内容 | spawn 用了别的 python | 看下面"spawn 路径" |
| `lca-ops kernel-restart` 报"lca_kernel serve 没在跑",`lca-ops heal` 60s 超时 | 见 kernel-restart-vs-heal |

### 看当前解释器

```bash
which python3                   # 应是 /opt/lca/venv/bin/python3
python3 -c "import sys; print(sys.executable)"  # 应是同一路径
/opt/lca/venv/bin/python3 -c "import cordis; print(cordis.__file__)"  # 应是 vendor/cordis/src/cordis
```

## spawn 路径(lca-ops → lca_kernel)

`KernelServeService._spawn`(lca/infrastructure/cli/services/kernel/serve.py)负责 spawn `lca_kernel serve` 子进程。约定:

- **`sys.executable`**(2026-09-09 修复):用当前 lca-ops 解释器直接 Popen。`lca-ops` 走 `/opt/lca/venv/bin/python`,子进程也走同一解释器 — 装包一致。
- **不**用 `uv run python -m lca_kernel serve`:`uv run` 在项目根创/复用 `.venv/`,与 `/opt/lca/venv` 不同步,经常找不到 `cordis` / `cryptography`。
- **不**用 `python` 裸命令:依赖 `$PATH`,在某些 shell 配置下会被替换为 pip 用户级 python(`/home/lichao/.local/bin/python`),装包全错地方。

## kernel-restart vs heal

- **`lca-ops kernel-restart`**:假设旧 kernel_serve 进程在跑(发 SIGTERM,等 K6 dispose,再 spawn 新进程)。**仅当旧进程存在时**才完成 spawn。
- **`lca-ops heal`**:从零 spawn。即使没旧进程也会拉起。

如果 `kernel-restart` 失败并提示"lca_kernel serve 没在跑",说明旧进程已死(OOM / SIGKILL / 异常退出),直接用 `heal` 拉新。

## 装新依赖流程

```bash
# 1. 在 venv 装
/opt/lca/venv/bin/pip3 install <pkg>

# 2. 验证
/opt/lca/venv/bin/python3 -c "import <pkg>; print(<pkg>.__file__)"

# 3. lca-ops 仍走默认 PATH,所以装完立即可用,无需重启 lca-ops
./scripts/lca-ops status --json
```

不要把 `pip install <pkg>` 直接敲在 shell(无 venv 前缀) — 大概率装到 `/home/lichao/.local/`,然后花 10 分钟 debug "为什么 import 不到"。

## 背景与决策

- ADR-0119 决定 4:LCA 进程入口切到 `python -m lca_kernel serve`,lca-ops 不再长管进程,只 `state()` / `heal()`。
- vendored cordis:见 `vendor/cordis/pyproject.toml`,LCA 内部 plugin / context API 走 vendored 版本,与 PyPI `cordis`(0.0.0 占位)不兼容。
