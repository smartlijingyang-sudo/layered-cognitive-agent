# LobeHub UI（LCA 内置，独立副本）

本目录与 LobeHub 官方无关，是 LCA 项目自维护的 v2.2.13 副本。

## 目录结构

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 可运行的 LobeHub 源码（gitignore，由脚本生成） |
| `.lobehub-upstream/` | 官方 v2.2.13 git 缓存（gitignore，只读参考） |
| `.lca-ops/` | gateway/lobehub pid + 日志 |
| `deploy/lobehub/.env.lca` | 环境变量模板（**提交进 git**） |
| `lca-ops.yaml` | 栈配置 SSOT |
| `scripts/lca-ops` | 唯一入口 |

## 启动

```bash
./scripts/lca-ops          # 手册
./scripts/lca-ops dev      # 第一次 / 全停之后
./scripts/lca-ops status
./scripts/lca-ops heal     # 有问题自己修
./scripts/lca-ops logs     # journal 实况（思考 / 工具 / 步）
```

`dev`：补丁 + gateway :8765 + LobeHub :3010 + daemon。日常用 `heal`，不要先 `restart`。

## 状态与补丁：status 字段语义

`./scripts/lca-ops status` 的 lobehub 块有两层补丁检查，含义不同：

| 字段 | 看的是 | 健康标准 | 异常时怎么办 |
|---|---|---|---|
| `patches` | `deploy/lobehub/patches/**/*.py` 实际写到 lobehub-ui 的 anchor/marker | 全部 `verify` OK | 直接跑 `python3 deploy/lobehub/patch_lobehub.py`（不需要 restart，HMR 自动生效） |
| `pnpm-patches` | lobehub-ui 上游声明的 `pnpm.patchedDependencies`（用 bun 装的 node_modules，要手工 `git apply`） | marker 文件存在 + 无 drift | **几乎总是上游依赖漂移** —— 不是 LCA 配错；去 lobehub-ui/patches/ 重新从上游生成 patch 文件 |

### `ensure` 是 short-circuit，不是"全量重打"

`./scripts/lca-ops lobehub ensure` 会按顺序跑 `_ensure_source / _ensure_patches / _ensure_pnpm_patches / _ensure_env / _ensure_deps`，但**每一项都是 no-op-when-up-to-date**：

- `_ensure_patches` 只在 `deploy/lobehub/patches/` 的 hash 变了时才重新打。改了一次 patch 后快照会更新，下次 ensure 看到 hash 没变就什么都不做。
- `_ensure_pnpm_patches` 只在 `.lca-ops/lobehub-pnpm-patches.marker` 不存在时才尝试 apply，写了 marker 之后永远 short-circuit。

也就是说 `ensure` 不等于"重新打一遍补丁"。要**强制重打**：

```bash
# 重打源码补丁（从 .lobehub-upstream/ 恢复目标文件 + 重放所有 patch）
python3 deploy/lobehub/patch_lobehub.py --reset

# 仅检查现状（不改任何东西，输出每个 patch 的 OK/BROKEN/SKIP）
python3 deploy/lobehub/patch_lobehub.py verify

# 强制重试 pnpm patches（删 marker + 跑 ensure）
rm .lca-ops/lobehub-pnpm-patches.marker
./scripts/lca-ops lobehub ensure
```

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
   ./scripts/lca-ops lobehub restart
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
