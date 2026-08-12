# LobeHub UI（LCA 内置，独立副本）

本目录 **与 `/home/lichao/lobehub` 无任何关系**，是 LCA 项目自维护的 LobeHub 副本。

## 目录（均在 LCA 仓库根下）

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 可运行的 LobeHub 源码（gitignore，由脚本生成） |
| `.lobehub-upstream/` | 官方 git 浅克隆缓存（gitignore） |
| `.lobehub-stack/` | gateway 进程 pid / 日志（gitignore） |
| `deploy/lobehub/.env.lca` | 本地 env 模板（**提交进 git**） |

## 首次拉取 v2.2.13

```bash
./scripts/sync_lobehub_ui.sh
```

从 `https://github.com/lobehub/lobehub.git` 拉取 tag `v2.2.13`，写入 `lobehub-ui/`。

## 启动

```bash
./scripts/start_lobehub_stack.sh dev
```

`dev` / `sync` 会自动：

1. 从官方 tag 同步 `lobehub-ui/`（若需要）
2. **自动打 LCA 补丁**（`deploy/lobehub/patch_lobehub.py` — 统一补丁引擎，19 个幂等 patch）
3. 启动 gateway（**Python 代码比进程新时自动重启**）
4. 启动 LobeHub dev

若只改了 gateway Python，可：

```bash
./scripts/start_lobehub_stack.sh restart-gateway
```

若只改了 LCA 补丁脚本、未 sync 官方 UI：

```bash
python3 deploy/lobehub/patch_lobehub.py          # apply all
python3 deploy/lobehub/patch_lobehub.py verify   # dry-run check
python3 deploy/lobehub/patch_lobehub.py list     # show manifest
# LobeHub dev 需手动刷新 / 重启 dev 进程
```

`dev` 启动前会自动停止占用 `:3010` 的旧 LobeHub/Next 进程（含 `.next/dev/lock`）。
若本机已有 `lobe-postgres(:25432)` / `lobe-minio(:19000)` 等容器，脚本会自动跳过 docker compose。
若需保留已有 dev 实例：`LOBE_REUSE_DEV=1 ./scripts/start_lobehub_stack.sh dev`

停止全部：`./scripts/start_lobehub_stack.sh stop`

## 版本锁定

同步后在 `lobehub-ui/.lca-origin.json` 可查看来源 tag 与同步时间。

## 补丁治理规则

### 铁律：永远不要直接编辑 `lobehub-ui/`

`lobehub-ui/` 是由 `sync_lobehub_ui.sh` 从上游同步 + 打补丁生成的工作副本。
**任何直接修改都会在下次 sync 时被覆盖丢失。**

### 正确流程

```
1. 在 lobehub-ui/ 中实验性修改，验证效果
2. 将修改转化为 patch_lobehub.py 中的补丁函数 p_xxx()
3. 注册到 PATCHES manifest（含 depends_on / why / technical_detail）
4. 添加 verify marker 到 _VERIFY_MARKERS
5. 运行 sync_lobehub_ui.sh 验证补丁能从干净上游正确应用
6. 运行 doctor 确认全绿
```

### 治理命令

```bash
# 检测未注册的直接修改
python3 deploy/lobehub/patch_lobehub.py drift

# 全量健康检查（verify + drift + 一致性 + 依赖图）
python3 deploy/lobehub/patch_lobehub.py doctor

# 生成结构化 JSON manifest
python3 deploy/lobehub/patch_lobehub.py manifest

# 详细列表（含 why / how）
python3 deploy/lobehub/patch_lobehub.py list --verbose
```

### 补丁元数据规范

每个 PatchMeta 必须包含：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 唯一标识符，snake_case |
| `description` | ✅ | 一句话描述做了什么 |
| `files` | ✅ | 修改的文件路径列表 |
| `risk` | ✅ | low / medium / high — 上游升级时的破坏风险 |
| `category` | ✅ | streaming / runtime / provider / auth / route / devux / proxy / ui |
| `depends_on` | ❌ | 前置依赖的补丁名列表 |
| `why` | ❌ | 为什么需要这个补丁（业务/技术原因） |
| `technical_detail` | ❌ | 具体改了什么（技术细节） |

### 补丁函数规范

```python
def p_xxx() -> bool:
    """一句话 docstring 说明补丁作用。"""
    rel = "path/to/file.ts"
    text = _read(rel)
    if "marker_string" in text:  # 幂等检查
        return False
    anchor = "..."  # 上游原文锚点
    if anchor not in text:
        raise SystemExit("[xxx] anchor not found")
    text = text.replace(anchor, replacement, 1)
    _write(rel, text)
    return True
```

**关键原则**：
- 返回 `True` = 本次应用了，`False` = 已存在（跳过）
- 用 `raise SystemExit` 报告锚点不匹配（上游升级时触发）
- 每个补丁必须幂等（多次运行结果相同）
