"""Compose-time named factories.

The composition root (``lca/layer4_app/spawn.py``) does not instantiate
concrete services inline — it resolves a factory through the cordis
context (``ctx.require("<capability>.compose_service")()``). Each module
in this package provides exactly one such factory.

Adding a new compose-time service:

1. Add a module here exposing ``build_<name>_compose()``.
2. Decorate ``setup()`` with ``@plugin(provides=["<name>.compose_service"], ...)``.
3. Reference ``$module: lca.plugins.compose.<name>`` from the bundle.
"""
