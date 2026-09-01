"""EventSpine wrap-kind plugins (ctx_effect / ctx_intercept / assembler).

ADR-0165.1 §7.6.4 defines three weave paths. The installer implementations
for ``ctx_effect`` / ``ctx_intercept`` live in
:mod:`lca.plugins.observability.spine.runtime_hooks`; this package hosts
the ``@plugin`` Manifests that Profile / Bundle load via ``$module``.
The assembler wrap re-exports
:func:`~lca.harness.declarative.compile.instrument_wrap.wrap_instrument`.
"""
