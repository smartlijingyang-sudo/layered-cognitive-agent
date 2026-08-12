"""Auto-discovered LobeHub patch modules.

Each subdirectory contains patch modules grouped by category.
Every module must export:
    meta: PatchMeta
    apply(ctx: PatchContext) -> bool
"""
