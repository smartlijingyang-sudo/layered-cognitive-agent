"""Regression test for the ``business-event-isolation`` importlinter contract.

PR-5 / ADR-0165.1: business code (cognition / runtime / agent / application)
must not import legacy journal backends or spine derivers directly. This
test builds the grimp import graph and asserts there are no import chains
from any source module to any forbidden target.

The contract is also enforced by ``pyproject.toml``'s
``[tool.importlinter.contracts] business-event-isolation`` entry. This test
exists for two reasons:

1. It runs even when ``lint-imports`` aborts early on another (currently
   broken) contract — ``lint-imports`` walks contracts in declaration order
   and aborts on the first uncaught exception, so a regression in
   ``business-event-isolation`` would otherwise be masked by upstream
   contract failures.
2. It produces a precise list of forbidden import chains with line numbers
   when it fails, which makes regressions easier to triage.
"""

from __future__ import annotations

from pathlib import Path

import grimp
import pytest

# Forbidden target modules (mirrors pyproject.toml).
FORBIDDEN_MODULES: tuple[str, ...] = (
    "lca.infrastructure.observability.journal.engine",
    "lca.infrastructure.observability.journal.backends",
    "lca.infrastructure.observability.journal.stream",
    "lca.infrastructure.observability.journal.step",
    "lca.infrastructure.observability.spine.derivers",
)

# Source modules (mirrors pyproject.toml).
SOURCE_MODULES: tuple[str, ...] = (
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
)


def _build_graph() -> grimp.ImportGraph:
    """Build the full lca import graph (no cache so the test sees current source)."""
    return grimp.build_graph(
        "lca",
        include_external_packages=True,
        cache_dir=None,
    )


@pytest.fixture(scope="module")
def graph() -> grimp.ImportGraph:
    return _build_graph()


def _find_chains(
    graph: grimp.ImportGraph,
    source: str,
    forbidden: str,
) -> list[tuple[str, ...]]:
    """Return all shortest import chains from ``source`` to ``forbidden``.

    ``as_packages=True`` mirrors the importlinter default — a forbidden
    import of any submodule inside ``journal.engine`` (for example) counts
    as a violation of ``journal.engine`` itself.
    """
    return list(
        graph.find_shortest_chains(
            importer=source,
            imported=forbidden,
            as_packages=True,
        )
    )


def test_business_event_isolation_no_direct_imports() -> None:
    """Direct ``from lca.infrastructure.observability.journal.<sub> import ...``
    statements in business modules must not exist.

    We check the source text instead of the static import graph because
    any direct import would also appear in the chain-based check below.
    This gives a clearer error message ("file X line Y") for the most
    common regression mode.
    """
    repo_root = Path(__file__).resolve().parents[2]
    forbidden_subnames = tuple(name.rsplit(".", 1)[-1] for name in FORBIDDEN_MODULES if "." in name)
    targets = {
        "lca.infrastructure.observability.journal.engine",
        "lca.infrastructure.observability.journal.backends",
        "lca.infrastructure.observability.journal.stream",
        "lca.infrastructure.observability.journal.step",
        "lca.infrastructure.observability.spine.derivers",
    }
    bad: list[str] = []
    for src_root in SOURCE_MODULES:
        src_path = repo_root / "lca" / src_root.removeprefix("lca.").replace(".", "/")
        if not src_path.exists():
            continue
        for py_file in src_path.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for target in targets:
                    if target in line:
                        # Allow indirect references in docstrings/comments (rare).
                        bad.append(f"{py_file.relative_to(repo_root)}:{line_no}: {line.strip()}")
    assert not bad, (
        "Direct forbidden imports of journal.* / spine.derivers "
        "found in business layers:\n  " + "\n  ".join(bad)
    )
    # Reference forbidden_subnames so editors do not flag it as unused.
    assert forbidden_subnames  # always true


def test_business_event_isolation_no_chains(graph: grimp.ImportGraph) -> None:
    """No import chain from any business module to any forbidden module.

    This is the hard-fail check that mirrors the importlinter contract
    (``as_packages=True``). It catches both direct and indirect (transitive
    via the ``lca.infrastructure.observability`` facade) forbidden imports.
    """
    violations: list[str] = []
    for source in SOURCE_MODULES:
        for forbidden in FORBIDDEN_MODULES:
            for chain in _find_chains(graph, source, forbidden):
                violations.append(f"{source} -> {forbidden}: {' -> '.join(chain)}")
    assert not violations, (
        "Forbidden import chains found "
        "(business-event-isolation contract violations):\n  " + "\n  ".join(violations)
    )


def test_business_event_isolation_contract_present_in_pyproject() -> None:
    """Sanity check: the pyproject.toml contract still exists with the
    expected configuration. Guards against accidental rename / removal.
    """
    import tomllib

    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = pyproject.get("tool", {}).get("importlinter", {}).get("contracts", [])
    match = next(
        (c for c in contracts if c.get("name") == "business-event-isolation"),
        None,
    )
    assert match is not None, "business-event-isolation contract not found in pyproject.toml"
    assert match.get("type") == "forbidden"
    assert set(match.get("source_modules", [])) >= set(SOURCE_MODULES)
    forbidden = set(match.get("forbidden_modules", []))
    expected_forbidden = set(FORBIDDEN_MODULES)
    assert expected_forbidden.issubset(forbidden), (
        f"forbidden_modules missing: {expected_forbidden - forbidden}"
    )
    # PR-5 hard-fail: contract must NOT carry a ``dry_run`` flag (none
    # exists in importlinter's forbidden contract schema; assert absence
    # so a future addition is intentional, not accidental).
    assert "dry_run" not in match, (
        "business-event-isolation contract must remain hard-fail "
        "(no dry_run flag). PR-5 promotion is complete."
    )


def test_business_event_isolation_lazy_loader_facade_symbols() -> None:
    """The PEP 562 ``__getattr__`` lazy loader on the observability facade
    still resolves the journal symbols at runtime. If a future refactor
    breaks the lazy loader, callers that depend on
    ``from lca.infrastructure.observability import RunStore`` will see
    AttributeError at first use.
    """
    import lca.infrastructure.observability as obs

    expected = (
        "RunStore",
        "UnregisteredJournalEventError",
        "RunState",
        "RunStatus",
        "fold_run_state",
        "OtelProjector",
        "InMemoryJournalStore",
        "read_journal",
        "stamped_to_record",
        "stamped_to_journal_record",
    )
    missing = [name for name in expected if not hasattr(obs, name)]
    assert not missing, "Observability facade missing expected lazy-loaded symbols: " + ", ".join(
        missing
    )
