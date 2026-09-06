# plugins/meta — 薄注册桥

Providers、Strategies、Act/State 注册等**非业务**桥接。

| Legacy |
|---|
| `plugins/providers/` |
| `plugins/strategies/` |
| `plugins/act/` |
| `plugins/state/` |

保持 ≤8 文件/子目录；出现第二 seam 职责时拆到 cognitive/loop/domain。

**seam 定义**在 `plugins/seams/`（非本目录）。
