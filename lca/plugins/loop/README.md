# plugins/loop — 执行图与 Loop 插件

Seam 树：**loop/** · phase executor、control contribution、loop driver、reducer plugin。

| 子组 | 说明 |
|---|---|
| `phase/<phase>/<variant>/` | 六语义 phase executor |
| `graph/{topology,edges,resilient,recovery,nodes,state}/` | 声明式图 provider + 协作节点 + stop policy |
| `control/<slot>/` | control contribution |
| `driver/` | loop driver |
| `reducer/` | state reducer plugin |

机制 SSOT：`harness/graph/` + `lca/loop/`（FactGateway、transaction）。

**新 phase executor 请用** `loop/phase/<phase>/<variant>/plugin.py`。
