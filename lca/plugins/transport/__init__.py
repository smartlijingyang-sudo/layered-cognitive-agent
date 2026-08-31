"""Transport namespace — 替代 `gateway/` 物理包(ADR-0115 决定 2)。

每个 transport 子包是一个 plugin,只通过 :mod:`lca.contracts.protocols.route_registry`
跟 kernel 解耦,不直接 import ``lca_kernel.*`` 或 ``lca.cognition / agent / runtime``。

子包:
- ``webserver`` —— Starlette-based gateway transport(PR-4)。
- ``acp`` —— JSON-RPC / ACP transport(后续 ADR-0118)。
- ``cli`` —— argv dispatch(后续 ADR-0119)。
"""
