"""Starlette-based gateway transport — PR-4 实施(ADR-0112 修订版 + ADR-0115)。

模块清单:
- :mod:`.router` —— :class:`GatewayRouter` 实现 + ``lca-gateway-router`` L0 SEAM plugin。
- :mod:`.routes_health_options` —— ``lca-gateway-routes-health-options`` plugin(/health + OPTIONS)。
- :mod:`.routes_runs_sessions` —— ``lca-gateway-routes-runs-sessions`` plugin(/runs + /v1/sessions)。
- :mod:`.routes_openai_compat_files` —— ``lca-gateway-routes-openai-compat-files`` plugin(/v1/* + /files/*)。
- :mod:`.routes_device` —— ``lca-gateway-routes-device`` plugin(/api/device/*)。

webserver transport 的 factory 在 :mod:`gateway.app` —— 它直接驱动
:func:`lca_kernel.run_kernel_lifespan`,不在 transport 命名空间里保留独立
adapter 文件(ADR-0115 决定 6 要求 gateway/app.py 是 thin factory)。

参考 deepseek host/webserver/src/index.ts (WebServer extends Service + register/dispose)。
"""
