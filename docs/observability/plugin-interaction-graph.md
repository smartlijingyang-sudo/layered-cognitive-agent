# Plugin Interaction Graph — ADR-0065 §六

## Mermaid 渲染

`TraceInspector.plugin_interaction_graph(events)` 输出 Mermaid `flowchart LR` 字符串:

```mermaid
flowchart LR
    "plugin_a" -->|ok| "plugin_b"
    "plugin_b" -->|error| "plugin_c"
    Empty[无插件交互记录]
```

## 数据来源

边来自 `RuntimeObserved(operation="plugin.interaction")` 事件:
- `source` → `attributes.target_plugin`
- `outcome` → 边标签

## 触发时机

- 只读派生,不写账本(L6)
- CLI: `lca-ops graph <run_id>`
- Coding Agent: `coding_agent_plugin_graph_renderer.render(run_id)`
- Manifest: generator_id=`plugin_graph_renderer`,version=`<v>`

## 空图 fallback

无交互记录 → `flowchart LR\n    Empty[无插件交互记录]`(避免 Mermaid 解析失败)。