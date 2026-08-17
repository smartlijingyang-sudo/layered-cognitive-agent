"""dsh_core — 1:1 Python port of deepseek-harness ``packages/core``.

Each sub-package mirrors one ``@deepseek-ai/dsh-*`` package:

- ``scope``             → ``@deepseek-ai/dsh-scope``
- ``session``           → ``@deepseek-ai/dsh-session``
- ``tools``             → ``@deepseek-ai/dsh-tools``
- ``agent``             → ``@deepseek-ai/dsh-agent``
- ``system_prompt``     → ``@deepseek-ai/dsh-system-prompt``
- ``agent_default_model`` → ``@deepseek-ai/dsh-agent-default-model``
- ``agent_tool_presentation`` → ``@deepseek-ai/dsh-agent-tool-presentation``
- ``agent_loop``        → ``@deepseek-ai/dsh-agent-loop``

The plugin kernel (``lca.layer0_infra.plugin.kernel``) serves as the
Cordis equivalent — ``PluginContext`` provides ``effect``, ``on``,
``emit``, ``serial``, ``waterfall``, ``child``.
"""
