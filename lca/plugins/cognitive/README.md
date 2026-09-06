# plugins/cognitive — 认知可替换实现

Seam 树：**cognitive/** · 目标 home for brain, body, gate, memory, perceive, reasoner, critic, sensors。

| 子组 | Legacy 来源 | 说明 |
|---|---|---|
| `perceive/` | `plugins/perceive/` | PerceiveHub 组装 |
| `think/` | `plugins/think/` | Think pipeline provider |
| `brain/` | `plugins/brain/` | ModularBrain 等 |
| `body/` | `plugins/body/` | Body provider |
| `gate/` | `plugins/gate/` + `plugins/gates/` | 薄注册 → `cognition/brain/decision_gates` |
| `memory/` | `plugins/memory/` | Memory backend |
| `reasoner/` | `plugins/reasoner/` | LLM reasoner |
| `critic/` | `plugins/critic/` | Reflect critic |
| `sensors/` | `plugins/sensors/` | 传感器 |

**新 @plugin 请在本树下开包**（`cognitive/<group>/<id>/plugin.py`）。Legacy 顶层目录冻结新增。

算法 SSOT 仍在 `lca/cognition/`（零 emit）。
