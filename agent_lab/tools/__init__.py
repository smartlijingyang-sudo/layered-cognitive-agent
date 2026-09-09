"""agent_lab/tools — tool implementations only.

The named-tool registry (``registry.py`` + ``registry.yaml``) was
removed in PR-E.2; tool loading is now driven by the LCA plugin layer
via ``lca.plugins.lab.tools.provider``. This package now only holds
the tool implementation classes (the concrete ``Tool`` subclasses).
"""