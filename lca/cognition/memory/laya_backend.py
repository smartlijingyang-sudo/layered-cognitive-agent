"""Laya System-1 decision backend for memory scoring and consolidation (ADR-0277 Phase 4).

Laya (NandhaKishorM/laya, Apache-2.0) is a non-autoregressive System-1 decision
engine: typed decisions (choice / score / noul) in a single forward pass (~33 ms).
ADR-0277 uses exactly two of its primitives:

- ``score``  -> retrieval-time relevance scoring of memory candidates
               (feeds the ACT-R style retrieval score in ADR-0277 C3);
- ``noul`` / ``choice`` -> consolidation decisions in the remember phase, e.g.
               noul: "is this episodic trace worth distilling into a semantic
               claim?"; choice: supersede / merge / keep-both for conflicting
               claims.

Honest technical constraints (from Laya's own BENCHMARKS.md, verified
2026-10-03 against the upstream repo):

1. The base checkpoints sit BELOW the majority-class baseline on the
   typed-decisions benchmark (0.362 / 0.352 vs 0.461). All capability on this
   benchmark comes from fine-tuning, so scoring MUST use the fine-tuned
   checkpoint ``convaiinnovations/laya-typed-decisions`` -- never the base
   ``laya`` / ``laya-multilingual`` checkpoints.
2. Both checkpoints ship over-confident (macro ECE 0.7331 before the
   temperature clamp, 0.5709 after). Every confidence this backend reports is
   therefore re-calibrated with an extra temperature scale (default T=1.5,
   conservative) on top of the checkpoint's own fitted temperatures. The
   direction of miscalibration is task-dependent, so T is configurable and a
   fit-on-your-own-data path (``LayaScoreEngine.fit_temperatures``) is exposed
   for when labeled memory data exists.

Chinese queries and routing:
Laya's ``Router`` detects script/language per request and routes non-English
text to the ``laya-multilingual`` (mmBERT-base, 100+ languages) checkpoint.
This backend deliberately pins ``convaiinnovations/laya-typed-decisions`` for
ALL languages instead, because the multilingual checkpoint is a base
checkpoint subject to constraint (1) above. To keep Chinese queries legible
to the model, the score legend and instructions are bilingual (Chinese +
English); callers who need pure-Chinese routing may subclass and override
``checkpoint`` / ``_select_checkpoint``.

The ``laya`` package is imported lazily inside ``LayaScoreEngine.__init__``.
If the import (or checkpoint load) fails, the engine reports
``is_available() == False`` and every inference method raises RuntimeError
with a clear message -- importing this module itself never raises.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CHECKPOINT = "convaiinnovations/laya-typed-decisions"
DEFAULT_CACHE_DIR = "/home/lichao/.cache/laya/checkpoints"

# Conservative extra temperature on top of the checkpoint's fitted temperatures.
# T > 1 flattens the distribution (counters the shipped over-confidence);
# official package clamps its own fitted temperatures to [0.5, 5].
DEFAULT_TEMPERATURE = 1.5

# Bilingual relevance legend used as the score question's criteria.
# Laya renders a score criterion list as "level %d: %s".
RELEVANCE_LEGEND: dict[int, str] = {
    0: "irrelevant / 无关",
    1: "weakly related / 弱相关",
    2: "related / 相关",
    3: "strongly related / 强相关",
    4: "directly answers the query / 直接回答该问题",
}

_SCORE_QUESTION_ID = "relevance"
_SCORE_INSTRUCTIONS = (
    "How relevant is the candidate memory to the query? "
    "候选记忆与查询的相关程度如何？"
)


@dataclass(frozen=True)
class LayaScore:
    """Relevance score for one candidate. ``confidence`` is temperature-calibrated."""

    label: int  # 0..4, index into RELEVANCE_LEGEND
    confidence: float  # calibrated max-probability, 0..1


@dataclass(frozen=True)
class LayaDecision:
    """Result of a consolidation decision (noul / choice)."""

    decision: str  # typed value projected by Laya, as a string
    confidence: float  # calibrated confidence, 0..1
    raw: dict = field(default_factory=dict)  # full Laya answer payload for audit


def recalibrate_probs(probs: list[float], temperature: float) -> list[float]:
    """Apply an extra temperature scale to a probability distribution.

    Recovers pseudo-logits via ``log(p)`` and re-applies
    ``softmax(logits / temperature)``. This is exact up to the additive
    constant softmax is invariant to: if the input came from
    ``softmax(z / t0)``, the output equals ``softmax(z / (t0 * temperature))``.

    ``temperature > 1`` flattens (counters over-confidence),
    ``temperature < 1`` sharpens. Must be > 0.
    """
    if not (temperature > 0) or not math.isfinite(temperature):
        raise ValueError(f"temperature must be a positive finite number, got {temperature!r}")
    eps = 1e-12
    zs = [math.log(max(p, eps)) for p in probs]
    scaled = [z / temperature for z in zs]
    m = max(scaled)
    exps = [math.exp(z - m) for z in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _calibrated_answer_confidence(answer: dict[str, Any], temperature: float) -> float:
    """Calibrated ``answer_confidence`` (max probability) for a Laya answer dict."""
    probs_map = answer.get("probabilities") or {}
    if answer.get("type") == "noul":
        p_true = float(answer.get("noul", 0.0))
        probs = [1.0 - p_true, p_true]
    else:
        # choice and score both carry an index-keyed "probabilities" map.
        items = sorted(probs_map.items(), key=lambda kv: str(kv[0]))
        probs = [float(v) for _, v in items]
    if not probs:
        return 0.0
    return max(recalibrate_probs(probs, temperature))


class LayaScoreEngine:
    """Pluggable System-1 backend: score relevance + consolidation decisions.

    Parameters
    ----------
    checkpoint:
        Hugging Face repo id (or local dir) of the Laya checkpoint. Defaults to
        ``convaiinnovations/laya-typed-decisions`` -- see module docstring for
        why the base checkpoints must NOT be used for scoring.
    cache_dir:
        Directory checkpoints are downloaded to. Never inside the repo.
    temperature:
        Extra conservative temperature applied to every reported confidence
        (default 1.5). > 1 flattens the over-confident raw distribution.
    device:
        Passed to ``laya.load`` (e.g. "cuda", "cpu"); None = Laya default.
    """

    def __init__(
        self,
        checkpoint: str = DEFAULT_CHECKPOINT,
        cache_dir: str = DEFAULT_CACHE_DIR,
        temperature: float = DEFAULT_TEMPERATURE,
        device: str | None = None,
    ) -> None:
        if not (temperature > 0) or not math.isfinite(temperature):
            raise ValueError(f"temperature must be a positive finite number, got {temperature!r}")
        self.checkpoint = checkpoint
        self.cache_dir = cache_dir
        self.temperature = temperature
        self.device = device
        self._agent: Any = None
        self._load_error: str | None = None
        try:
            import laya  # lazy: backend must import without laya installed
        except Exception as exc:  # any import failure -> unavailable
            self._load_error = f"laya package import failed: {exc}"
            return
        try:
            if cache_dir:
                # Keep weights in the caller's cache dir, not the HF default.
                os.environ.setdefault("HF_HOME", cache_dir)
                os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(cache_dir, "hub"))
            # "typed-decisions" alias resolves to the same standalone repo.
            self._agent = laya.load(checkpoint, device=device)
        except Exception as exc:  # any load failure -> unavailable
            self._load_error = f"laya checkpoint load failed ({checkpoint}): {exc}"

    # ------------------------------------------------------------------ state

    def is_available(self) -> bool:
        """True when the laya package imported and the checkpoint loaded."""
        return self._agent is not None

    def load_error(self) -> str | None:
        """Human-readable reason when unavailable, else None."""
        return self._load_error

    def close(self) -> None:
        """Release the resident checkpoint (best effort; safe to call anytime)."""
        self._agent = None
        try:
            import gc

            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------- primitives

    def _require_available(self) -> Any:
        if self._agent is None:
            raise RuntimeError(
                f"LayaScoreEngine is not available: {self._load_error}. "
                f"Install the 'laya' package and download checkpoint {self.checkpoint!r} "
                "(see module docstring)."
            )
        return self._agent

    def score_relevance(
        self,
        query: str,
        candidates: list[str],
        legend: dict[int, str] | None = None,
    ) -> list[LayaScore]:
        """Score each candidate's relevance to the query (Laya ``score`` primitive).

        One batched forward pass over all candidates (System-1 speed). Returns
        ``LayaScore`` list in candidate order; ``label`` is the rounded expected
        level (0..4), ``confidence`` the temperature-calibrated max probability.
        """
        agent = self._require_available()
        if not candidates:
            return []
        legend = legend or RELEVANCE_LEGEND
        levels = [legend[i] for i in sorted(legend)]
        question = {
            _SCORE_QUESTION_ID: {
                "type": "score",
                "instructions": _SCORE_INSTRUCTIONS,
                "criteria": levels,
            }
        }
        states = [f"Query: {query}\nCandidate: {cand}" for cand in candidates]
        payload = agent.predict_batch(states, question)
        # predict_batch returns one payload per state:
        # [{"model": ..., "answers": {qid: ans}, "usage": ...}, ...]
        per_state = payload if isinstance(payload, list) else [payload]
        out: list[LayaScore] = []
        n_levels = len(levels)
        for item in per_state:
            ans_map = item.get("answers") if isinstance(item, dict) else None
            if not isinstance(ans_map, dict):
                ans_map = item if isinstance(item, dict) else {}
            ans = ans_map.get(_SCORE_QUESTION_ID, {})
            probs_map = ans.get("probabilities") or {}
            probs = [float(probs_map.get(str(i), probs_map.get(i, 0.0))) for i in range(n_levels)]
            total = sum(probs)
            if total <= 0:
                out.append(LayaScore(label=0, confidence=0.0))
                continue
            probs = [p / total for p in probs]
            calibrated = recalibrate_probs(probs, self.temperature)
            expected = sum(i * p for i, p in enumerate(probs))
            label = max(0, min(n_levels - 1, round(expected)))
            out.append(LayaScore(label=label, confidence=max(calibrated)))
        return out

    def decide(self, state: dict, schema: dict) -> LayaDecision:
        """Run a consolidation decision (Laya ``noul`` / ``choice`` primitives).

        ``schema`` is a Laya questions dict, e.g.::

            {"distill": {"type": "noul",
                         "instructions": "Is this episodic trace worth "
                                         "distilling into a semantic claim?"}}
            {"reconcile": {"type": "choice",
                           "instructions": "How does the new claim relate to "
                                           "the existing one?",
                           "criteria": {"supersede": "...", "merge": "...",
                                        "keep-both": "..."}}}

        For a single-question schema the decision is that question's typed
        value (choice label / rounded score level / "yes" / "no") as a string;
        for multi-question schemas it is a JSON object of ``{qid: value}``.
        Confidence is the calibrated ``answer_confidence`` (minimum across
        questions for multi-question schemas -- weakest link, conservative).
        The full Laya payload is kept in ``raw`` for the audit log
        (ADR-0277 C5).
        """
        agent = self._require_available()
        if not isinstance(schema, dict) or not schema:
            raise ValueError("schema must be a non-empty questions dict")
        for qid, qdef in schema.items():
            if not isinstance(qdef, dict) or qdef.get("type") not in ("choice", "score", "noul"):
                raise ValueError(
                    f"schema[{qid!r}] must define a Laya question with type in "
                    "{choice, score, noul}"
                )
        payload = agent.predict(state, schema)
        # Agent.predict returns {"model": ..., "answers": {qid: ans}, "usage": ...}
        answers = payload.get("answers") if isinstance(payload, dict) else None
        if not isinstance(answers, dict):
            answers = payload if isinstance(payload, dict) else {}
        values: dict[str, str] = {}
        confidences: list[float] = []
        for qid, ans in answers.items():
            qtype = ans.get("type")
            if qtype == "choice":
                values[qid] = str(ans.get("choice"))
            elif qtype == "score":
                values[qid] = str(round(float(ans.get("score", 0.0))))
            elif qtype == "noul":
                values[qid] = "yes" if float(ans.get("noul", 0.0)) >= 0.5 else "no"
            else:
                values[qid] = json.dumps(ans, ensure_ascii=False, default=str)
            confidences.append(_calibrated_answer_confidence(ans, self.temperature))
        if len(values) == 1:
            decision_str = next(iter(values.values()))
        else:
            decision_str = json.dumps(values, ensure_ascii=False, sort_keys=True)
        confidence = min(confidences) if confidences else 0.0
        raw = payload if isinstance(payload, dict) else {"answers": answers}
        return LayaDecision(decision=decision_str, confidence=confidence, raw=raw)

    # ------------------------------------------------- optional: own-data fit

    def fit_temperatures(self, records: list) -> dict:
        """Fit per-bucket temperatures on labeled data (delegates to Laya).

        ``records`` are ``(qtype, logits, target, k)`` tuples; build them with
        ``laya.calibrate.records_from_labeled`` on a loaded agent. This is the
        honest fix for the shipped over-confidence (BENCHMARKS.md: "Fit
        temperatures on your own data") once memory-scored labels exist.
        """
        agent = self._require_available()
        return agent.fit_temperatures(records)
