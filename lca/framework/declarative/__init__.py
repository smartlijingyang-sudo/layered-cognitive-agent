"""Declarative phase-graph interpreter and its capability providers.

The interpreter itself, its factory, and every capability seam it injects
through Cordis live under :mod:`lca.framework.declarative.plugins`.  This
package is intentionally inert: it owns no executable code beyond
re-exporting the plugin entry points so that
``lca.framework.declarative.plugins.<name>.setup`` is discoverable from
profile bundles and tests alike.
"""

from lca.framework.declarative import plugins

__all__ = ["plugins"]
