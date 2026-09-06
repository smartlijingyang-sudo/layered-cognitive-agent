# Transport carrier — write path

> ADR-0195 §2.4 · [platform-directory-architecture.md](../../../../docs/specs/platform-directory-architecture.md)

**Carrier** triggers runs and domain commands. It does not append Session facts,
fold projections, or interpret phase graphs.

| Subpath | Responsibility |
|---|---|
| `runs/execute/` | POST run scheduling, loop drivers, execution environment |
| `runs/lifecycle/` | Run lifecycle coordinator, runnable assembly |
| `runs/resume.py` | Durable HIL resume (`recover_live_agent` authority) |
| `runs/answer.py` | *(future)* HIL answer wire |
| `assistants/` | *(future)* assistant domain API |
| `composio/` | *(future)* composio domain API |

Legacy `handlers/runs/execute/` and `handlers/runs/lifecycle/` re-export from here until P5 shim deletion.
