"""First-class plugin modules for the LCA harness runtime.

Each plugin is declared in a single ``.py`` file by the ``@plugin``
decorator (re-exported from :mod:`lca.harness.plugin_api`) with its full
manifest: ``id``, ``provides``, ``requires``, ``layer``, ``kind``,
``effects``, ``functional_group``, ``contract``, and ``test_suite``.
Plugins activate through ``bundles/*.yaml`` entries keyed by id; the
runtime resolves the id to the module path declared alongside the entry
and instantiates the plugin via its registered setup function.

Directory layout is a navigation aid, not a kind axis. Top-level
subdirectories group plugins by domain (``brain``, ``think``,
``observability``, ``events``, ``transport``, ...); the ``seams/`` and
``providers/`` trees carry the seam / provider split (seam exposes the
Protocol, provider fills it). All kind, layer, and effect facts live in
the manifest — directory location carries no semantic weight.

Composition-root code under :mod:`lca.plugins.composer` is being phased
out and moves to :mod:`lca.application.composer` (see PR-8 of
``docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md``).
After the migration this package contains only ``@plugin`` declarations
and their private helpers.
"""
