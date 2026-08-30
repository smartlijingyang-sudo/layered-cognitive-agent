"""Keep declarative contract module boundaries explicit and backward compatible."""

from lca.contracts.protocols.declarative_common import (
    DeclarativeValidationError as SplitDeclarativeValidationError,
)
from lca.contracts.protocols.declarative_execution import (
    DeclarativeRunOutcome as SplitDeclarativeRunOutcome,
)
from lca.contracts.protocols.declarative_execution import (
    PhaseRunCursor as SplitPhaseRunCursor,
)
from lca.contracts.protocols.declarative_graph import (
    CognitivePhaseGraphPlan as SplitCognitivePhaseGraphPlan,
)
from lca.contracts.protocols.declarative_graph import (
    ValidationReport as SplitValidationReport,
)
from lca.contracts.protocols.declarative_phase_graph import (
    CognitivePhaseGraphPlan,
    DeclarativeRunOutcome,
    DeclarativeValidationError,
    PhaseRunCursor,
    PluginSpec,
    ValidationReport,
)
from lca.contracts.protocols.declarative_plugin import PluginSpec as SplitPluginSpec


def test_legacy_declarative_module_reexports_specialized_contracts() -> None:
    """Existing callers keep object identity while new callers use focused modules."""

    assert DeclarativeValidationError is SplitDeclarativeValidationError
    assert PluginSpec is SplitPluginSpec
    assert CognitivePhaseGraphPlan is SplitCognitivePhaseGraphPlan
    assert ValidationReport is SplitValidationReport
    assert PhaseRunCursor is SplitPhaseRunCursor
    assert DeclarativeRunOutcome is SplitDeclarativeRunOutcome
