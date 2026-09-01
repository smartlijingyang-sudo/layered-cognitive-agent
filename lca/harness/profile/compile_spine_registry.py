"""``compile_spine_registry`` — assemble the spine handler registry from a profile.

The spine is a close-set subsystem (ADR-0165 + ADR-0165.1). Each
:data:`~lca.infrastructure.observability.spine.manifest.EXECUTION_POINTS`
entry must have a registered :class:`~lca.infrastructure.observability.spine.registry.SpineHandler`
whose ``wrap_fn`` is the actual ``emit_*`` helper from one of the 18
PR-3 reflectors. This module is the **build-time** assembly step that
walks the loaded profile, inspects every plugin whose module path lives
under :mod:`lca.plugins.observability.spine`, and registers every
``emit_*`` helper that targets an EXECUTION_POINTS entry as a wrap_fn
bound to the reflector module as its ``target_module``.

Layer-1 / Layer-2 enforcement (Task 3.5)
-----------------------------------------

The function returns a :class:`~lca.infrastructure.observability.spine.registry.SpineRegistry`.
The build-time pytest suite
(:func:`tests.observability.spine.test_registry_completeness`) then
calls :meth:`SpineRegistry.validate` against the full EXECUTION_POINTS
close-set and fails loudly if any EP is missing a registered handler.

The kernel boot hook (:func:`lca_kernel.boot.run_kernel`) calls this
function at boot. Per the PR-3 brief "soft check, not hard fail" — the
runtime hook logs a WARNING if coverage is incomplete, since sub-PRs
3.1–3.4 are still landing and the registry will not be fully populated
until those land. The hard-fail surface lives in the pytest suite, not
in the production boot path.

EP ↔ helper mapping
-------------------

The helper name does not always correspond to the EXECUTION_POINTS
literal it emits (e.g. ``emit_runtime_reducer_apply_start`` emits
``runtime.reducer.apply`` without the ``.start`` suffix). The registry
therefore reads the canonical EP from each helper's source via AST:
the first ``execution_point="..."`` keyword argument inside the helper
body is the EP the helper emits. Helpers without that literal (e.g.
private helpers, classifiers) are not added to the registry.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
import pkgutil
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
from lca.infrastructure.observability.spine.registry import (
    MissingWrapFn,
    SpineHandler,
    SpineRegistry,
)

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile

log = logging.getLogger(__name__)


_SPINE_PLUGIN_ROOT = "lca.plugins.observability.spine"


def _iter_spine_modules() -> Iterable[str]:
    """Yield every module path under the spine plugins package.

    Walks the ``lca.plugins.observability.spine`` package and its
    sub-packages (``reflectors``, ``classifiers``, ``derivers``). Used
    by the fallback path to discover ``@plugin`` registrations when the
    resolved profile does not enumerate every reflector explicitly.
    """
    try:
        package = importlib.import_module(_SPINE_PLUGIN_ROOT)
    except ImportError:
        return
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{_SPINE_PLUGIN_ROOT}."):
        if not module_info.ispkg:
            yield module_info.name


def _emit_helpers_from_module(module: Any) -> dict[str, Any]:
    """Pick every ``emit_*`` callable exported by ``module``.

    We use :attr:`module.__all__` when available (the convention for
    PR-3 reflectors) and fall back to scanning :func:`dir` for
    ``emit_`` prefixed callables. Returning the full mapping lets the
    caller pick the helper by name; only those whose AST body carries
    an ``execution_point="..."`` literal will be registered.
    """
    helpers: dict[str, Any] = {}
    names: Iterable[str]
    if isinstance(allattr := getattr(module, "__all__", None), Iterable):
        names = (n for n in allattr if not n.startswith("_"))
    else:
        names = (n for n in dir(module) if n.startswith("emit_"))
    for name in names:
        obj = getattr(module, name, None)
        if callable(obj):
            helpers[name] = obj
    return helpers


def _execution_point_from_helper(fn: Any) -> str | None:
    """AST-extract the EP literal a helper emits.

    Reads the source of ``fn`` and looks for the first
    ``execution_point="<literal>"`` keyword argument inside the
    function body. The literal is the canonical EP from
    :data:`EXECUTION_POINTS`. Returns ``None`` when no such literal
    exists — the helper is then skipped at registration time.
    """
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg != "execution_point":
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _register_module_helpers(
    registry: SpineRegistry,
    module: Any,
    module_name: str,
) -> None:
    """Register every ``emit_*`` helper from ``module`` whose AST names a canonical EP."""
    for helper_name, helper in _emit_helpers_from_module(module).items():
        ep = _execution_point_from_helper(helper)
        if ep is None:
            log.debug(
                "compile_spine_registry: helper %s.%s carries no execution_point literal",
                module_name,
                helper_name,
            )
            continue
        try:
            registry.register(
                execution_point=ep,
                wrap_fn=helper,
                target_module=module_name,
            )
        except MissingWrapFn:
            log.debug(
                "compile_spine_registry: reject helper %s.%s",
                module_name,
                helper_name,
            )


def _scan_fallback(registry: SpineRegistry) -> None:
    """Fallback: scan the spine plugins package for reflectors and register.

    When a profile does not enumerate reflector modules explicitly (the
    common case for non-OII-debug profiles), this path walks
    ``lca.plugins.observability.spine`` and registers every ``emit_*``
    helper whose AST carries an ``execution_point="..."`` literal.
    Duplicates (two helpers emitting the same EP) are resolved by
    ``SpineRegistry.register`` — last writer wins, which is acceptable
    because the close-set intent forbids double-registration upstream.
    """
    for module_name in _iter_spine_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            log.debug("compile_spine_registry: skip module %s: %s", module_name, exc)
            continue
        _register_module_helpers(registry, module, module_name)


def compile_spine_registry(
    profile: ResolvedProfile | None = None,
) -> SpineRegistry:
    """Walk the loaded profile and assemble the :class:`SpineRegistry`.

    Parameters
    ----------
    profile:
        The resolved profile whose plugins list this function walks to
        discover spine reflectors. ``None`` is allowed and skips the
        profile walk; the function then falls back to scanning the
        ``lca.plugins.observability.spine`` package.

    Returns
    -------
    SpineRegistry
        The assembled registry. Callers decide whether to call
        :meth:`SpineRegistry.validate` against EXECUTION_POINTS (the
        build-time pytest suite does; the runtime boot hook only logs).
    """
    registry = SpineRegistry()

    if profile is not None:
        for resolved_plugin in profile.plugins:
            module_name = resolved_plugin.module
            if not module_name.startswith(_SPINE_PLUGIN_ROOT):
                continue
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                log.debug(
                    "compile_spine_registry: skip unimportable %s: %s",
                    module_name,
                    exc,
                )
                continue
            _register_module_helpers(registry, module, module_name)

    if len(registry) == 0:
        _scan_fallback(registry)

    return registry


def log_coverage_gaps(registry: SpineRegistry) -> tuple[str, ...]:
    """Return the EP set that ``registry`` does not cover, logging each gap.

    Used by the runtime kernel boot hook as a soft check: a profile
    booted before PR-3 fully lands will not cover every EP. The hard
    fail lives in the pytest suite
    (``tests/observability/spine/test_registry_completeness``), which
    runs against the future full-coverage configuration.
    """
    registered = set(registry.keys())
    missing = tuple(point for point in EXECUTION_POINTS if point not in registered)
    if missing:
        log.warning(
            "spine_registry_coverage_gap: %d/%d execution points unregistered: %s",
            len(missing),
            len(EXECUTION_POINTS),
            ", ".join(sorted(missing)),
        )
    return missing


__all__ = [
    "SpineHandler",
    "SpineRegistry",
    "compile_spine_registry",
    "log_coverage_gaps",
]
