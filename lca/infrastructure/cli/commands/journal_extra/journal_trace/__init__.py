"""Journal trace CLI package — parse, render, and command submodules.

The public surface (``register``) is re-exported here so the original
import path ``lca.infrastructure.cli.commands.journal_extra.journal_trace``
keeps working unchanged.
"""

from lca.infrastructure.cli.commands.journal_extra.journal_trace.command import register

__all__ = ["register"]
