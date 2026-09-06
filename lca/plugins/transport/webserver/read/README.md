# Transport read — observe path

> ADR-0195 §2.4 · C7 观察面

**Read** folds Session / spine facts into wire DTOs for HTTP/SSE. No control-plane
side effects, no Session.append, no state repair.

| Subpath | Responsibility | Legacy |
|---|---|---|
| `runs/live.py` | SSE / OpenAI stream | `handlers/runs/terminal/live_*` |
| `runs/timeline.py` | Run timeline projection | `handlers/runs/observability/*` |
| `runs/debug.py` | Debug fold views | doctor-adjacent reads |
| `runs/terminal/` | Terminal materialization (fold) | `handlers/runs/terminal/` |

Migration: P3-07–P3-09. Skeleton only until those PRs land.
