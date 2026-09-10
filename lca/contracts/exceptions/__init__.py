"""Contract-layer subgraph exception family (ADR-0217 §3.3.1 / §3.3.3).

Closed set: depth, cycle, and port-naming conflict. Each subclass carries
its identifying attributes (depth, plan_ref, node_id, port) so callers can
inspect without re-parsing the message. Stays dependency-free per ADR-0015
+ AGENTS.md §2.1 — leaf.
"""