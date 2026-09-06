"""Fact Plane architecture invariants — ADR-0192 §3.4."""

from __future__ import annotations

import ast
import inspect
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COGNITION = _REPO_ROOT / "lca" / "cognition"
_PERCEIVE_HUB = _COGNITION / "perceive" / "hub.py"
_PHASE_LOOP = _REPO_ROOT / "lca" / "plugins" / "loop" / "phase"
_PHASE_EMITTER = _REPO_ROOT / "lca" / "loop" / "emit" / "spine" / "phase_fact.py"
_TRANSACTION = _REPO_ROOT / "lca" / "loop" / "transaction.py"


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            ["rg", "--line-number", "--no-heading", "--color", "never", pattern, str(root)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    out: list[str] = []
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                out.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}:{line}")
    return out


class TestIFact1:
    def test_i_fact_1_fact_committer_protocol_importable(self) -> None:
        from lca.contracts.protocols.observability.fact_committer import FactCommitter
        from lca.infrastructure.session.fact_committer import SessionFactCommitter

        assert isinstance(SessionFactCommitter(), FactCommitter)


class TestIFact2:
    """I-FACT-2: Cognition must not use Journal production APIs directly."""

    def test_i_fact_2_perceive_hub_and_sink_clean(self) -> None:
        path = _PERCEIVE_HUB
        forbidden = (
            "bound.journal",
            "record_runtime(",
            "default_sink(",
            "emit_context_manifested_for_state",
            "emit_context_injected",
            "begin_step(",
            "cursor.advance",
            "_sink.emit",
        )
        matches: list[str] = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            for token in forbidden:
                if token in line:
                    matches.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}:{line}")
        assert not matches, "I-FACT-2 perceive_hub violations\n" + "\n".join(matches)

    def test_i_fact_2_cognition_no_direct_facade_record(self) -> None:
        """Cognition must route journal writes through append_journal_event seam."""
        forbidden_patterns = (
            "from lca.infrastructure.observability import record",
            "from lca.infrastructure.observability.facade.facade import record",
            "record_runtime(",
        )
        matches: list[str] = []
        for path in _COGNITION.rglob("*.py"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for token in forbidden_patterns:
                    if token in line:
                        matches.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}:{line}")
        assert not matches, "I-FACT-2 cognition facade violations\n" + "\n".join(matches)

    def test_i_fact_2_perceive_hub_pure(self) -> None:
        from lca.cognition.perceive import hub as perceive_hub

        source = textwrap.dedent(inspect.getsource(perceive_hub.SequentialPerceiveHub.perceive))
        body_text = ast.unparse(ast.parse(source))
        assert "journal" not in body_text.lower()
        assert "emit_context" not in body_text
        assert "cursor.advance" not in body_text


class TestIFact3:
    def test_i_fact_3_transaction_calls_phase_fact_emitter(self) -> None:
        text = _TRANSACTION.read_text(encoding="utf-8")
        assert "emit_phase_catalog_facts" in text

    def test_i_fact_3_runtime_journal_uses_session_committer(self) -> None:
        from lca.infrastructure.session.fact_committer import SessionFactCommitter
        from lca.runtime.runtime_journal import RuntimeJournalCommitter

        assert issubclass(RuntimeJournalCommitter, SessionFactCommitter)


class TestIFact5:
    @pytest.mark.parametrize("module_name", ["perceive", "remember"])
    def test_i_fact_5_phase_executors_no_scattered_emit(self, module_name: str) -> None:
        path = _PHASE_LOOP / module_name / "standard" / "plugin.py"
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "begin_step(",
            "end_step(",
            "emit_context_injected",
            "emit_context_manifested",
            "lifecycle_emit",
            "meta_event_emit",
        ):
            assert forbidden not in text, f"{path.name} must not call {forbidden}"

    def test_i_fact_5_phase_fact_emitter_exists(self) -> None:
        assert _PHASE_EMITTER.exists()
        text = _PHASE_EMITTER.read_text(encoding="utf-8")
        assert "emit_context_manifested_for_state" in text
        assert "begin_step" in text
        assert 'advance("perceive")' in text
