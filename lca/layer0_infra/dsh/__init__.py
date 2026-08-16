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
    "DshTurnDriver": ("lca.layer0_infra.dsh.driver", "DshTurnDriver"),
    "DshTurnSpec": ("lca.layer0_infra.dsh.driver", "DshTurnSpec"),
    "DshNotification": ("lca.layer0_infra.dsh.models", "DshNotification"),
    "DshTurnResult": ("lca.layer0_infra.dsh.models", "DshTurnResult"),
    "compose_dsh_prompt": ("lca.layer0_infra.dsh.prompt", "compose_dsh_prompt"),
    "is_dsh_driver": ("lca.layer0_infra.dsh.routing", "is_dsh_driver"),
    "run_dsh_machine_turn": ("lca.layer0_infra.dsh.run", "run_dsh_machine_turn"),
    "DshSettings": ("lca.layer0_infra.dsh.settings", "DshSettings"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY_IMPORTS[name]
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value
