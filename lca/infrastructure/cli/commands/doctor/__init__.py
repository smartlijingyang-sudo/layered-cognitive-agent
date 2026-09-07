"""``lca-ops doctor`` subcommand package (ADR-0199 §5.3 / P2-08).

Subpackage marker only — registration with the top-level :mod:`lca.infrastructure.cli`
app is performed by importing :func:`lca.infrastructure.cli.commands.doctor.profile.register`
in the commands package's ``__init__.py`` (P2-12 wires this up if not done by an
earlier follow-up).
"""
