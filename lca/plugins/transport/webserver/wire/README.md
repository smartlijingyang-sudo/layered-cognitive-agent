# Transport wire — DTO adapters

> ADR-0195 §2.4 Adapter pattern

Maps HTTP/CLI payloads ↔ `lca/contracts` types. No business rules, no I/O beyond
serialization.

| Source (legacy) | Target |
|---|---|
| `handlers/runs/wire/` | `wire/runs/` (P3-11) |
| route request bodies | contract DTOs |

Skeleton only until P3-11 consolidation.
