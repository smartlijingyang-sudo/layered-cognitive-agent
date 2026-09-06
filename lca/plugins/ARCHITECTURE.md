# lca/plugins — 插件物理架构与 Seam 树

> **目录宪法：** [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)  
> **决策：** [ADR-0195](../../docs/adr/0195-platform-architecture-convergence.md) · [ADR-0190](../../docs/adr/adr-0190-extreme-plugin-organization.md)

## 1. 职责

**全部可替换贡献的 Manifest 安装单元。** 每个生产 plugin = 一个 `@plugin` 入口（通常单文件 `plugin.py`），由 `bundles/*.yaml` 的 `$module` 激活。

## 2. 不负责

- Plan 编译、MTK 图验证（`harness/graph`）
- Session append 语义（`lca/session`）
- Kernel 启动（`lca_kernel`）
- 组合根选 profile（`application`）

## 3. Seam 树（目标物理布局）

```text
plugins/
├── seams/              ← Protocol 槽位声明（已有，稳定）
├── cognitive/          ← 认知实现（brain/body/gate/memory/…）
├── loop/               ← phase executor、control、driver、reducer
├── observability/      ← deriver、exporter、sink、provider
├── transport/          ← webserver carrier/read、cli
├── domain/             ← assistant、tools、integrations、skill
├── composition/        ← composer、factories、profile、prompts
└── meta/               ← 薄 registry 桥（providers、strategies）
```

**新 plugin 必须**进入 seam 树路径；**禁止**在 legacy 顶层目录新增 `@plugin`（门禁 `test_platform_directory.py`）。

## 4. Legacy 顶层 → 目标（迁移对照）

| Legacy（现状） | 目标路径 | Wave |
|---|---|---|
| `phase_graph/` | `loop/phase/<phase>/<variant>/` | P4 |
| `control_contributions/` | `loop/control/<slot>/` | P4 |
| `brain/` `think/` `reasoner/` `critic/` | `cognitive/think/` `cognitive/brain/` … | P4 |
| `body/` | `cognitive/body/` | P4 |
| `gate/` `gates/` | `cognitive/gate/<id>/` | P4 |
| `perceive/` `sensors/` | `cognitive/perceive/` `cognitive/sensors/` | P4 |
| `memory/` | `cognitive/memory/` | P4 |
| `loop_drivers/` | `loop/driver/` | P4 |
| `plugins/runtime/` (reducer) | `loop/reducer/` | P4 |
| `observability/` | `observability/deriver|exporter|sink|provider/` | P2 |
| `events/publishers/spine_reflector_*` | **删除**（FactGateway） | P2 |
| `session/` | 机制 → `lca/session/`；剩余薄 plugin | P4 |
| `transport/` | `transport/webserver/{carrier,read,wire}/` | P3 |
| `assistant/` `tools/` `integrations/` | `domain/<name>/` | P4 |
| `composer/` `factories/` `profile/` `prompts/` | `composition/` | P4 |
| `collaboration/` | `domain/collaboration/` | P4 |
| `seams/` | **保留** | — |
| `providers/` `strategies/` `act/` `state/` | `meta/` | P4 |

## 5. 一包一 plugin

```text
plugins/<seam>/<group>/<plugin-id>/
  plugin.py       # 唯一 @plugin
  config.py       # 可选
```

- 单目录直接 `.py` 数 ≤8（见 package-organization-discipline）
- 禁止 `__init__.py` 内 `@plugin`
- 禁止 plugin → plugin 硬 import

## 6. `plugins/seams/`（已有）

声明 Seam 与 Protocol 的对应，**不含业务 setup**：

`act/` · `collaboration/` · `gate/` · `journal/` · `memory/` · `observability/` · `perceive/` · `state/` · `think/`

## 7. 装配

```yaml
# bundles/*.yaml
plugins:
  - id: phase.perceive.standard
    $module: lca.plugins.loop.phase.perceive.standard.plugin   # 迁移后 → lca.plugins.loop.phase.perceive.standard
```

## 8. 验证

```bash
./scripts/lca-ops audit-plugin-shape
uv run pytest tests/architecture/test_platform_directory.py -q
```

## 9. 公共入口

- 装饰器：`lca.harness.plugin_api.plugin`
- Manifest 类型：`lca.harness.plugin_manifest`

详见 [plugins/README.md](README.md)（setup 范式）。
