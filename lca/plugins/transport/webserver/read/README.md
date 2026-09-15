# Transport read — observe path

> ADR-0195 §2.4 · C7 观察面

## 1. 职责

**Read** folds Session / spine facts into wire DTOs for HTTP/SSE.

## 2. 不负责

No control-plane side effects, no `Session.append`, no state repair (C7 观察面)。

| Subpath | Responsibility | Legacy |
|---|---|---|
| `runs/live.py` | SSE / OpenAI stream | `handlers/runs/terminal/live_*` |
| `runs/timeline.py` | Run timeline projection | `handlers/runs/observability/*` |
| `runs/debug.py` | Debug fold views | doctor-adjacent reads |
| `runs/terminal/` | Terminal materialization (fold) | `handlers/runs/terminal/` |

## 7. 副作用

读取本身不改变状态，但两条路径会落地东西：

| 路径 | 后果 |
|---|---|
| `runs/terminal/failure`（现 `handlers/runs/terminal/failure/failure.py`） | 写诊断文件：`traces/runs/<run_id>/` 目录创建 + `kernel.log` 追加（`failure.py:67,72`） |
| `runs/live` SSE 尾读 | 向 `session.tail.subscribe(after_seq=…)` 注册订阅者（不是 Session observer，不改事实流）；teardown 时向每个订阅者队列投递 `None` 关闭其迭代 |

Migration: P3-07–P3-09. Skeleton only until those PRs land.
