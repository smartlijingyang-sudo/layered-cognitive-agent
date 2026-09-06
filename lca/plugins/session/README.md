# plugins/session — Session runtime 与投影 plugin

事实平面 SSOT 在 [`lca/session/`](../../session/README.md)。本目录保留 `bundles/session-runtime.yaml` 装配的薄 plugin（runtime store、投影、标题、遥测）。

| 家族 | Bundle `$module` 前缀 | 说明 |
|---|---|---|
| runtime | `lca.plugins.session.runtime.plugin` | `session.store`（SessionStore + DSH Session） |
| checkpoint | `checkpoint_policy` | 三边界 flush policy |
| projection | `projection_*`, `session_*`, `token_usage` | DSH 投影 fold |
| title | `title_service` | 标题服务（`title_llm_provider` 按部署选挂） |
| telemetry | `telemetry_*` | 捕获 + OTel（bundle 默认 DISABLED） |

**Bundle SSOT:** [`bundles/session-runtime.yaml`](../../../bundles/session-runtime.yaml) — 每条 `$module` 须可 `importlib` 加载且暴露 `setup`。

## 迁移

Wave P1/P4/P5-02：事实 API（append / catalog / fold / repair / bind / recovery）→ `lca.session`；runtime 子模块目录化（`bus/facade.py`、`spine/hook.py` 等）。旧 flat 路径保留 COMPAT re-export，勿改 bundle 条目直至 canonical 路径稳定。

**delete-when（整目录收敛）：**

- `bundles/session-runtime.yaml` 无 `lca.plugins.session.runtime` 条目
- `rg "from lca.plugins.session.runtime.(session|event_catalog|repair|bind|recovery|fold|checkpoint) import" lca/ tests/` 无命中
- `rg "from lca.plugins.session.runtime.(bus.bus_facade|log.log_reader|cursor.cursor_port|spine.spine_hook|spine.spine_event_projection|resume.resume_point) import" lca/ tests/` 无命中
- runtime plugin：`$module` 指向 `runtime.plugin.plugin` 且 `runtime/plugin/__init__.py` COMPAT 可删
