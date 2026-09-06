# plugins/loop — 执行图与 Loop 插件

Seam 树：**loop/** · phase executor、control contribution、loop driver、reducer plugin。

| 子组 | Legacy 来源 |
|---|---|
| `phase/<phase>/<variant>/` | `plugins/phase_graph/` executors |
| `graph/{topology,edges,resilient,recovery}/` | `plugins/phase_graph/` declarative providers |
| `control/<slot>/` | `plugins/control_contributions/` |
| `driver/` | `plugins/loop_drivers/` |
| `reducer/` | `plugins/runtime/reducer.py` |

机制 SSOT：`harness/graph/` + `lca/loop/`（FactGateway、transaction）。

**新 phase executor 请用** `loop/phase/<phase>/<variant>/plugin.py`。
