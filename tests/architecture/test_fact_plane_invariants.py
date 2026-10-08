"""Fact Plane architecture invariants — ADR-0192 §3.4."""

from __future__ import annotations

import ast
import inspect
import shutil
import subprocess
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COGNITION = _REPO_ROOT / "lca" / "cognition"
_PERCEIVE_HUB = _COGNITION / "perceive" / "hub.py"


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
        from lca.infrastructure.session.commit.fact_committer import SessionFactCommitter

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
            "from lca.infrastructure.observability.facade.facade.facade import record",
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
    def test_i_fact_3_runtime_journal_uses_session_committer(self) -> None:
        from lca.infrastructure.session.commit.fact_committer import SessionFactCommitter
        from lca.runtime.loop.runtime_journal import RuntimeJournalCommitter

        assert issubclass(RuntimeJournalCommitter, SessionFactCommitter)


class TestIFact3V2Seam:
    """I-FACT-3 v2 (ADR-0221 切流后): catalog 事实的唯一汇入缝是
    ``append_catalog_bound`` → ``DefaultFactGateway.append_catalog``。

    arch 00:09 裁决 todo-87 (a): 意图存活, 归宿 seam 即此; 不钉
    ``emit_context_manifested_for_state``(零生产调用, 纯 vestigial)。
    """

    _SEAM_FILE = "lca/loop/fact_gateway.py"

    def test_append_catalog_bound_delegates_to_default_fact_gateway(self, monkeypatch) -> None:
        import lca.loop.fact_gateway as fg

        monkeypatch.setattr(fg, "_require_publish_writer", lambda session, *, fact, actor: object())
        seen: dict = {}

        def fake_init(self, writer):
            seen["writer"] = writer

        monkeypatch.setattr(fg.DefaultFactGateway, "__init__", fake_init)

        def fake_append_catalog(self, event, *, actor):
            seen["event"] = event
            seen["actor"] = actor
            return "RECEIPT"

        monkeypatch.setattr(fg.DefaultFactGateway, "append_catalog", fake_append_catalog)

        event = object()
        assert fg.append_catalog_bound(event, session=object(), actor="unit-test") == "RECEIPT"
        assert seen["event"] is event
        assert seen["actor"] == "unit-test"
        assert "writer" in seen

    def test_append_catalog_bound_drops_loudly_when_unbound(self, monkeypatch) -> None:
        import lca.loop.fact_gateway as fg

        monkeypatch.setattr(fg, "active_publish_session", lambda: None)
        warnings: list = []

        class _Log:
            def warning(self, event, **kwargs):
                warnings.append(event)

        monkeypatch.setattr(fg, "_log", _Log())

        assert fg.append_catalog_bound(object(), actor="unit-test") is None
        assert "fact_gateway.unbound_drop" in warnings

    def test_no_direct_gateway_construction_or_catalog_append_outside_seam(self) -> None:
        for pattern in ("DefaultFactGateway(", ".append_catalog("):
            hits = [
                h for h in _rg(pattern, _REPO_ROOT / "lca") if h.split(":", 1)[0].endswith(".py")
            ]
            offenders = [h for h in hits if not h.startswith(self._SEAM_FILE + ":")]
            assert not offenders, (
                "I-FACT-3 v2: catalog 必须经 append_catalog_bound 缝汇入, "
                "禁止绕过 seam 直接构造/调用\n" + "\n".join(offenders)
            )


class TestIFact5V2ProducerClosedSet:
    """I-FACT-5 v2: catalog/spine 事件生产者闭集 — 只能经 bound seam 发射。

    白名单 = lca/ 内调用 ``append_catalog_bound``/``publish_ep_bound`` 的模块
    (2026-10-09 iter-tests 实证枚举)。新增生产者必须先经 arch 裁决入白名单。
    """

    _PRODUCERS = frozenset(
        {
            "lca/loop/commit/tool_journal.py",
            "lca/loop/commit/memory_journal.py",
            "lca/loop/commit/delegation_journal.py",
            "lca/loop/commit/act_journal.py",
            "lca/loop/observation.py",
            "lca/loop/emit/spine/ep.py",
            "lca/infrastructure/session/emit/runtime_emit.py",
            "lca/infrastructure/session/emit/lifecycle_emit.py",
            "lca/infrastructure/session/emit/convergence_emit.py",
            "lca/infrastructure/session/emit/cognitive_emit/tool_events.py",
            "lca/infrastructure/session/emit/cognitive_emit/step_events.py",
            "lca/infrastructure/session/emit/cognitive_emit/reflection_events.py",
            "lca/infrastructure/session/emit/cognitive_emit/gate_events.py",
            "lca/infrastructure/session/commit/spine_envelope.py",
            "lca/infrastructure/session/commit/fact_committer.py",
            "lca/infrastructure/observability/meta_event_emit.py",
            "lca/infrastructure/observability/spine/exception/emit.py",
        }
    )

    def test_producer_closed_set(self) -> None:
        hits: list[str] = []
        for pattern in ("append_catalog_bound(", "publish_ep_bound("):
            hits.extend(_rg(pattern, _REPO_ROOT / "lca"))
        offenders = []
        for hit in hits:
            rel = hit.split(":", 1)[0]
            if not rel.endswith(".py"):
                continue
            if rel == "lca/loop/fact_gateway.py":
                continue  # 缝定义本身
            if rel not in self._PRODUCERS:
                offenders.append(hit)
        assert not offenders, "I-FACT-5 v2: 未在白名单的生产者模块\n" + "\n".join(offenders)
