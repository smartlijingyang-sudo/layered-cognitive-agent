"""Strategy annotations must be resolvable at runtime.

``lca/framework/graph/strategies/*`` run under ``from __future__ import
annotations``, so an annotation naming a symbol the module never imports
is not a syntax error — it is a latent ``NameError`` for anything that
introspects the strategy (DI containers, ``typing.get_type_hints``,
schema generation). ``gate_chain_strategy`` annotated its gate sequence
with ``DecisionGate``, a cognition-side Protocol it deliberately does
not import.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import typing

from lca.contracts.protocols.graph.binding import BindingKind
from lca.framework.graph import strategies as strategies_pkg
from lca.framework.graph.strategies import gate_chain_strategy as gcs
from lca.framework.graph.strategy_registry import default_strategy_registry


def _resolution_targets(module: object) -> list[object]:
    """The module itself plus the classes/functions it defines."""
    own = (
        obj
        for obj in vars(module).values()
        if getattr(obj, "__module__", None) is module.__name__
        and (inspect.isclass(obj) or inspect.isfunction(obj))
    )
    return [module, *own]


def _strategy_modules() -> list[object]:
    return [
        importlib.import_module(f"{strategies_pkg.__name__}.{found.name}")
        for found in pkgutil.iter_modules(strategies_pkg.__path__)
    ]


def test_gate_chain_annotations_resolve():
    for target in _resolution_targets(gcs):
        typing.get_type_hints(target)


def test_every_strategy_module_annotation_resolves():
    for module in _strategy_modules():
        for target in _resolution_targets(module):
            typing.get_type_hints(target)


def test_registered_gate_chain_prototype_has_no_gates():
    strategy = default_strategy_registry().resolve(BindingKind.GATE_CHAIN)
    assert isinstance(strategy, gcs.GateChainStrategy)
    assert tuple(strategy.gates) == ()
