"""Public exports for ``background`` (auto-fixed)."""

from lca.infrastructure.computer.background.background import (
    BackgroundCommandRecord,
    BackgroundCommandRegistry,
    get_background_registry,
)

__all__ = ['BackgroundCommandRecord', 'BackgroundCommandRegistry', 'get_background_registry']
