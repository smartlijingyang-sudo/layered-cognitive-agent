"""DeepSeek Harness compare driver.

A Run *driver*, not a third execution plane. LCA sets SDK launch (cwd, cordis,
env paths); DSH owns agent loop, skills, and workspaceContext. Journal
projection is the only LobeHub-facing adapter.
"""

__all__ = [
    "DshNotification",
    "DshSettings",
    "DshTurnDriver",
    "DshTurnResult",
    "DshTurnSpec",
    "compose_dsh_prompt",
    "is_dsh_driver",
    "run_dsh_machine_turn",
]

_LAZY_IMPORTS = {
    "DshTurnDriver": ("lca.infrastructure.dsh.driver", "DshTurnDriver"),
    "DshTurnSpec": ("lca.infrastructure.dsh.driver", "DshTurnSpec"),
    "DshNotification": ("lca.infrastructure.dsh.models", "DshNotification"),
    "DshTurnResult": ("lca.infrastructure.dsh.models", "DshTurnResult"),
    "compose_dsh_prompt": ("lca.infrastructure.dsh.prompt", "compose_dsh_prompt"),
    "is_dsh_driver": ("lca.infrastructure.dsh.routing", "is_dsh_driver"),
    "run_dsh_machine_turn": ("lca.infrastructure.dsh.run", "run_dsh_machine_turn"),
    "DshSettings": ("lca.infrastructure.dsh.settings", "DshSettings"),
}


def __getattr__(name: str) -> object:
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY_IMPORTS[name]
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value
