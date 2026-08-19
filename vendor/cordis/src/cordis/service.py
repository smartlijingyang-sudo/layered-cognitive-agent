"""`cordis.service` — Service base class with auto-dispose and config validation.

Services are the primary unit of stateful logic in cordis. A Service:

1. Is created with a Context (automatically registers for auto-dispose)
2. Optionally declares a `config` class attribute (Pydantic model for validation)
3. Can override `dispose()` for cleanup
4. Is disposed in LIFO order when the context disposes
5. Errors in dispose are swallowed (logged but don't propagate)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Type

from cordis.context import Context

logger = logging.getLogger(__name__)


class Service:
    """Base class for cordis services.

    Subclass this to create stateful services that automatically register
    with a Context for lifecycle management.

    Example:
        class DatabaseService(Service):
            config = DatabaseConfig  # Pydantic model

            def __init__(self, ctx: Context, **config):
                super().__init__(ctx)
                self.connection = connect(config["host"], config["port"])

            async def dispose(self):
                await self.connection.close()

        ctx = Context()
        db = DatabaseService(ctx, host="localhost", port=5432)
        ctx.provide("database", db)
        # ... use db ...
        await ctx.dispose()  # calls db.dispose() automatically
    """

    config: ClassVar[Type[Any] | None] = None
    """Optional Pydantic model class for config validation.

    If set, the service will validate config kwargs against this model.
    Subclasses can override this to enforce type-safe configuration.
    """

    def __init__(self, ctx: Context, **config: Any) -> None:
        """Initialize the service and register with context for auto-dispose.

        Args:
            ctx: The context this service belongs to. The service will be
                 disposed when this context disposes.
            **config: Configuration kwargs. If `config` class attribute is set
                      to a Pydantic model, these kwargs are validated against it.
        """
        self.ctx = ctx
        # Validate config if a Pydantic model is declared
        if self.config is not None and config:
            self._validated_config = self.config(**config)
        else:
            self._validated_config = None
        # Register disposer that calls self.dispose()
        ctx.effect(lambda: self.dispose())

    async def dispose(self) -> None:
        """Cleanup hook called when the context disposes.

        Override this to release resources (close connections, stop threads, etc).
        Errors raised here are logged but swallowed to allow other services to dispose.
        """
        pass


__all__ = ["Service"]
