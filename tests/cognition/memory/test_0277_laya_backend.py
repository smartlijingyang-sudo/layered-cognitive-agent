"""Tests for lca.cognition.memory.laya_backend (ADR-0277 Phase 4).

Unit tests run with the plain interpreter (no laya / torch needed): the
backend imports lazily, and unavailable paths are exercised with a fake
``laya`` module injected into ``sys.modules``.

The real-model integration test only runs when ``LAYA_REAL_TEST=1`` and the
checkpoint is actually loadable; otherwise it skips.
"""

from __future__ import annotations

import math
import os
import sys
import time
import types

import pytest

from lca.cognition.memory.laya_backend import (
    DEFAULT_CHECKPOINT,
    LayaDecision,
    LayaScore,
    LayaScoreEngine,
    recalibrate_probs,
)


# ------------------------------------------------------------------ helpers

def _fake_laya(monkeypatch, load_impl):
    """Inject a fake ``laya`` module whose ``load`` behaves as given."""
    fake = types.ModuleType("laya")
    fake.load = load_impl
    monkeypatch.setitem(sys.modules, "laya", fake)
    return fake


def _engine_with_agent(monkeypatch, agent):
    _fake_laya(monkeypatch, lambda checkpoint, device=None: agent)
    return LayaScoreEngine(checkpoint="fake-ckpt", cache_dir="/tmp/laya-test-cache")


def _score_answer(probs):
    return {
        "type": "score",
        "score": sum(i * p for i, p in enumerate(probs)),
        "probabilities": {str(i): p for i, p in enumerate(probs)},
        "confidence": 0.5,
        "answer_confidence": max(probs),
    }


class _FakeAgent:
    """Minimal stand-in for laya.Agent with canned payloads."""

    def __init__(self, batch_payload=None, single_payload=None):
        self._batch = batch_payload
        self._single = single_payload
        self.batch_calls: list = []
        self.single_calls: list = []

    def predict_batch(self, states, questions):
        self.batch_calls.append((states, questions))
        return self._batch

    def predict(self, state, questions):
        self.single_calls.append((state, questions))
        return self._single


# ------------------------------------------------- import / availability

def test_module_import_never_raises_without_laya():
    # Collection already imported the module; this pins the contract that
    # importing the backend must not require the laya package.
    assert "lca.cognition.memory.laya_backend" in sys.modules


def test_engine_invalid_temperature_rejected():
    with pytest.raises(ValueError):
        LayaScoreEngine(temperature=0.0)
    with pytest.raises(ValueError):
        LayaScoreEngine(temperature=-1.5)


def test_unavailable_when_laya_package_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)  # `import laya` -> ImportError
    eng = LayaScoreEngine()
    assert eng.is_available() is False
    assert eng.load_error()
    with pytest.raises(RuntimeError) as ei:
        eng.score_relevance("q", ["c"])
    assert "not available" in str(ei.value)
    assert DEFAULT_CHECKPOINT in str(ei.value)
    with pytest.raises(RuntimeError):
        eng.decide({"x": 1}, {"d": {"type": "noul", "instructions": "?"}})


def test_unavailable_when_checkpoint_load_fails(monkeypatch):
    def _boom(checkpoint, device=None):
        raise OSError("checkpoint not found")

    _fake_laya(monkeypatch, _boom)
    eng = LayaScoreEngine(checkpoint="no/such-checkpoint")
    assert eng.is_available() is False
    assert "no/such-checkpoint" in (eng.load_error() or "")
    with pytest.raises(RuntimeError) as ei:
        eng.score_relevance("q", ["c"])
    assert "not available" in str(ei.value)


def test_close_is_safe_when_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)
    eng = LayaScoreEngine()
    eng.close()  # must not raise


# ------------------------------------------------------- temperature math

def test_recalibrate_temperature_one_is_identity():
    probs = [0.7, 0.2, 0.1]
    out = recalibrate_probs(probs, 1.0)
    assert out == pytest.approx(probs, abs=1e-9)
    assert sum(out) == pytest.approx(1.0)


def test_recalibrate_larger_temperature_flattens():
    peaked = [0.9, 0.06, 0.04]
    c1 = max(recalibrate_probs(peaked, 1.0))
    c15 = max(recalibrate_probs(peaked, 1.5))
    c3 = max(recalibrate_probs(peaked, 3.0))
    assert c1 > c15 > c3  # hotter -> flatter -> lower max probability
    assert c15 < 0.9  # the conservative default must reduce over-confidence


def test_recalibrate_small_temperature_sharpens():
    peaked = [0.6, 0.25, 0.15]
    assert max(recalibrate_probs(peaked, 0.5)) > max(recalibrate_probs(peaked, 1.0))


def test_recalibrate_rejects_non_positive():
    with pytest.raises(ValueError):
        recalibrate_probs([0.5, 0.5], 0.0)


# ------------------------------------------------- score_relevance (mock)

def test_score_relevance_mock_shapes_and_calibration(monkeypatch):
    payload = [
        {"answers": {"relevance": _score_answer([0.02, 0.03, 0.05, 0.1, 0.8])}},
        {"answers": {"relevance": _score_answer([0.8, 0.1, 0.05, 0.03, 0.02])}},
        {"answers": {"relevance": _score_answer([0.2, 0.2, 0.2, 0.2, 0.2])}},
    ]
    eng = _engine_with_agent(monkeypatch, _FakeAgent(batch_payload=payload))
    scores = eng.score_relevance("What is the deploy checklist?", ["a", "b", "c"])
    assert len(scores) == 3
    assert all(isinstance(s, LayaScore) for s in scores)
    assert [s.label for s in scores] == [4, 0, 2]
    assert all(0.0 <= s.confidence <= 1.0 for s in scores)
    # Conservative calibration: reported confidence below the raw argmax mass.
    assert scores[0].confidence < 0.8
    assert scores[1].confidence < 0.8
    # One batched forward pass for all candidates (System-1 batching).
    states, question = eng._agent.batch_calls[0]
    assert len(states) == 3
    assert set(question) == {"relevance"}
    assert question["relevance"]["type"] == "score"
    assert len(question["relevance"]["criteria"]) == 5


def test_score_relevance_empty_candidates(monkeypatch):
    eng = _engine_with_agent(monkeypatch, _FakeAgent(batch_payload=[]))
    assert eng.score_relevance("q", []) == []


def test_score_relevance_custom_legend(monkeypatch):
    payload = [{"answers": {"relevance": _score_answer([0.0, 0.0, 1.0])}}]
    eng = _engine_with_agent(monkeypatch, _FakeAgent(batch_payload=payload))
    legend = {0: "no", 1: "maybe", 2: "yes"}
    scores = eng.score_relevance("q", ["c"], legend=legend)
    assert scores[0].label == 2


# ------------------------------------------------------- decide (mock)

def test_decide_noul_mock(monkeypatch):
    single = {"answers": {"distill": {"type": "noul", "noul": 0.85,
                                     "confidence": 0.85, "answer_confidence": 0.85}}}
    eng = _engine_with_agent(monkeypatch, _FakeAgent(single_payload=single))
    schema = {"distill": {"type": "noul",
                          "instructions": "Is this trace worth distilling?"}}
    dec = eng.decide({"trace": "..."}, schema)
    assert isinstance(dec, LayaDecision)
    assert dec.decision == "yes"
    # Calibrated confidence is below the raw over-confident 0.85.
    assert 0.5 < dec.confidence < 0.85
    assert dec.raw["answers"]["distill"]["noul"] == 0.85


def test_decide_choice_mock(monkeypatch):
    single = {"answers": {"reconcile": {
        "type": "choice", "choice": "merge",
        "probabilities": {"supersede": 0.1, "merge": 0.75, "keep-both": 0.15},
        "confidence": 0.6, "answer_confidence": 0.75}}}
    eng = _engine_with_agent(monkeypatch, _FakeAgent(single_payload=single))
    schema = {"reconcile": {"type": "choice",
                            "instructions": "How to reconcile?",
                            "criteria": {"supersede": "a", "merge": "b",
                                         "keep-both": "c"}}}
    dec = eng.decide({"new": "claim"}, schema)
    assert dec.decision == "merge"
    assert 0.0 < dec.confidence < 0.75


def test_decide_multi_question_json_and_min_confidence(monkeypatch):
    single = {"answers": {
        "a": {"type": "noul", "noul": 0.9, "confidence": 0.9, "answer_confidence": 0.9},
        "b": {"type": "choice", "choice": "x",
              "probabilities": {"x": 0.6, "y": 0.4},
              "confidence": 0.5, "answer_confidence": 0.6},
    }}
    eng = _engine_with_agent(monkeypatch, _FakeAgent(single_payload=single))
    schema = {"a": {"type": "noul", "instructions": "?"},
              "b": {"type": "choice", "instructions": "?", "criteria": {"x": "", "y": ""}}}
    dec = eng.decide({}, schema)
    import json as _json

    assert _json.loads(dec.decision) == {"a": "yes", "b": "x"}
    # Weakest link: confidence is the minimum across questions (conservative).
    assert dec.confidence <= max(recalibrate_probs([0.6, 0.4], 1.5))


def test_decide_rejects_bad_schema(monkeypatch):
    eng = _engine_with_agent(monkeypatch, _FakeAgent(single_payload={}))
    with pytest.raises(ValueError):
        eng.decide({}, {})
    with pytest.raises(ValueError):
        eng.decide({}, {"q": {"type": "bogus", "instructions": "?"}})


# ------------------------------------------------- real-model integration

_REAL = os.environ.get("LAYA_REAL_TEST") == "1"
_real_engine: LayaScoreEngine | None = None


def _get_real_engine() -> LayaScoreEngine:
    global _real_engine
    if _real_engine is None:
        _real_engine = LayaScoreEngine()
    return _real_engine


@pytest.mark.skipif(not _REAL, reason="set LAYA_REAL_TEST=1 to run the real checkpoint")
def test_real_score_relevance_mixed_languages():
    eng = _get_real_engine()
    if not eng.is_available():
        pytest.skip("laya unavailable: %s" % eng.load_error())
    query = "部署 checklist 有哪些步骤？"
    candidates = [
        "The deploy checklist: 1) run migrations 2) smoke test 3) flip the flag.",
        "部署清单：1）执行数据库迁移 2）冒烟测试 3）切换流量开关。",
        "我最喜欢的川菜是麻婆豆腐和回锅肉。",
    ]
    t0 = time.perf_counter()
    scores = eng.score_relevance(query, candidates)
    dt = time.perf_counter() - t0
    print("\nreal score_relevance: %.2fs for %d candidates (%.0f ms/candidate)"
          % (dt, len(candidates), dt / len(candidates) * 1000))
    for s, c in zip(scores, candidates):
        print("  label=%d conf=%.3f :: %s" % (s.label, s.confidence, c[:40]))
    assert len(scores) == 3
    assert all(0 <= s.label <= 4 for s in scores)
    assert all(0.0 < s.confidence <= 1.0 for s in scores)
    # The two deploy-checklist candidates must outrank the food sentence.
    assert scores[0].label >= scores[2].label
    assert scores[1].label >= scores[2].label


@pytest.mark.skipif(not _REAL, reason="set LAYA_REAL_TEST=1 to run the real checkpoint")
def test_real_decide_noul():
    eng = _get_real_engine()
    if not eng.is_available():
        pytest.skip("laya unavailable: %s" % eng.load_error())
    schema = {"distill": {"type": "noul",
                          "instructions": "Is this episodic trace worth "
                                          "distilling into a long-term semantic "
                                          "claim? 是否值得提炼为长期语义记忆？"}}
    t0 = time.perf_counter()
    dec = eng.decide(
        {"trace": "User asked for the deploy checklist three Wednesdays in a row. "
                  "用户连续三个周三询问部署清单。"},
        schema,
    )
    dt = time.perf_counter() - t0
    print("\nreal decide (noul): %.2fs decision=%s conf=%.3f"
          % (dt, dec.decision, dec.confidence))
    assert dec.decision in ("yes", "no")
    assert 0.0 < dec.confidence <= 1.0
