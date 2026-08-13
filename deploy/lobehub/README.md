# LobeHub UI（LCA 内置，独立副本）

本目录与 LobeHub 官方无关，是 LCA 项目自维护的 v2.2.13 副本。

## 目录结构

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 可运行的 LobeHub 源码（gitignore，由脚本生成） |
| `.lobehub-upstream/` | 官方 v2.2.13 git 缓存（gitignore，只读参考） |
| `.lobehub-stack/` | gateway/frontend 进程 pid + 日志（gitignore） |
| `deploy/lobehub/.env.lca` | 环境变量模板（**提交进 git**） |

## 启动

```bash
./scripts/start_lobehub_stack.sh dev
```

自动执行：同步 `lobehub-ui/` → 打 LCA 补丁 → 启动 gateway(:8765) → 启动 LobeHub dev(:3010)。

重启全部：`./scripts/start_lobehub_stack.sh restart`  
停止全部：`./scripts/start_lobehub_stack.sh stop`

## 补丁机制

### 铁律：永远不要直接编辑 `lobehub-ui/`

所有修改都会被下次 sync 覆盖。**正确做法是改 `deploy/lobehub/patches/*/xxx.py`。**

### 工作流程

```
1. 编辑 patch 定义
   vim deploy/lobehub/patches/category/my_patch.py

2. 运行 patch 引擎
   uv run python -m deploy.lobehub.patch_lobehub

   引擎自动：
   - 计算每个 .py 的 SHA256，与上次保存的 hash 比对
   - 若有变化 → 从 .lobehub-upstream/ 恢复目标文件到原始状态
   - 重放所有 patch → 目标 TS 文件被更新
   - Next.js / Vite HMR 自动热更新（无需重启前端）

3. 若改了 next.config.ts 相关 patch → 需重启前端
   bash scripts/start_lobehub_stack.sh restart
```

### Patch 模块结构

每个 patch 是一个 Python 文件，导出 `meta` 和 `apply`：

```python
from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="my_patch",
    description="一句话描述",
    files=("path/to/target.ts",),  # 被修改的文件
    risk="low",  # low/medium/high — 上游升级风险
    category="runtime",  # runtime/provider/auth/route/devux/proxy/ui
    verify_file="path/to/target.ts",
    verify_marker="MARKER_STRING",
)


def apply(ctx: PatchContext) -> bool:
    rel = "path/to/target.ts"
    text = ctx.read(rel)
    if "MARKER_STRING" in text:
        return False  # 已 patch 过

    old = "原始代码"
    new = "替换后的代码"
    if old not in text:
        raise SystemExit("[my_patch] anchor not found")

    ctx.write(rel, text.replace(old, new, 1))
    return True  # 本次应用了
```

**关键点**：
- `apply()` 返回 `True` = 本次应用，`False` = 跳过
- 锚点不匹配时 `raise SystemExit` 报错
- 必须幂等（多次运行结果相同）
- 引擎自动检测 `.py` 文件变化并触发重放

### 常用命令

```bash
# 应用所有 patch（检测变化后自动恢复+重放）
uv run python -m deploy.lobehub.patch_lobehub

# 列出所有 patch 及状态
uv run python -m deploy.lobehub.patch_lobehub list

# 验证 patch 是否正确应用
uv run python -m deploy.lobehub.patch_lobehub verify

# 强制从 upstream 恢复所有目标文件并重新 apply
uv run python -m deploy.lobehub.patch_lobehub --reset
```
