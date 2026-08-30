"""Guard the one-module-per-control-slot navigation contract."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPO / "bundles" / "declarative-phase-graph.yaml"
CONTROL_MODULE_PREFIX = "lca.plugins.control_contributions."


def _declared_control_modules() -> tuple[str, ...]:
    """Read the control contribution module paths from the default phase plan."""

    modules = []
    for line in BUNDLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("$module: "):
            continue
        module = stripped.removeprefix("$module: ")
        if module.startswith(CONTROL_MODULE_PREFIX):
            modules.append(module)
    return tuple(modules)


def test_each_declared_control_slot_is_one_navigable_plugin_module() -> None:
    """A control slot's policy and manifest must live in its declared module.

    This is intentionally a structural test rather than a runtime behavior
    test. It protects the locality benefit of the refactor: opening the module
    named by the plan must reveal both what the slot does and how it is
    contributed to the declarative graph.
    """

    modules = _declared_control_modules()

    assert len(modules) == 12
    assert all(not module.endswith("_plugin") for module in modules)
    for module_path in modules:
        module = importlib.import_module(module_path)
        source_path = Path(module.__file__ or "")
        source = source_path.read_text(encoding="utf-8")
        assert "@plugin(" in source
        assert "PhaseContribution(" in source
        assert "Executor" in source


def test_each_declared_control_executor_uses_the_phase_contract() -> None:
    """Control modules may see only the declared phase context and input.

    The executor signature is the adapter seam between plan governance and a
    control policy. Keeping that interface explicit prevents policies from
    depending on incidental implementation fields through untyped ``any``.
    """

    for module_path in _declared_control_modules():
        module = importlib.import_module(module_path)
        executors = [
            value
            for name, value in vars(module).items()
            if name.endswith("Executor") and inspect.isclass(value)
        ]
        assert len(executors) == 1
        parameters = tuple(inspect.signature(executors[0].execute).parameters.values())
        assert parameters[1].annotation == "PhaseContext"
        assert parameters[2].annotation == "PhaseInput"
