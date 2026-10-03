"""Auth URL Provenance Gate — intercepts unverified authorization URLs (INV-CONN-03).

Enforces that any OAuth, authorize, or token URL produced by the model
MUST have proven fact lineage in the session (e.g. from tool receipts or
user messages), blocking hallucinated auth links at the cognitive boundary.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.gate_policy import GateDecided
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate

_URL_PATTERN = re.compile(r"https?://[^\s\)\"\'\>]+")
_AUTH_KEYWORDS = ("oauth", "authorize", "token", "signin", "login", "composio.dev")
_AUTH_QUERY_KEYS = {"client_id", "redirect_uri", "response_type", "auth_config_id"}

_PROVENANCE_KEY = "_auth_url_provenance"


def is_auth_intent_url(url: str) -> bool:
    """Returns True if the URL contains authentication/OAuth/authorization intent."""
    parsed = urlparse(url)
    lower_netloc = parsed.netloc.lower()
    lower_path = parsed.path.lower()

    # Skip localhost / loopback
    if lower_netloc in ("127.0.0.1", "localhost"):
        return False

    # Check path and domain keywords
    for kw in _AUTH_KEYWORDS:
        if kw in lower_netloc or kw in lower_path:
            return True

    # Check OAuth query parameters
    query_params = parse_qs(parsed.query)
    if any(k in _AUTH_QUERY_KEYS for k in query_params):
        return True

    return False


def _get_provenance_set(state: AgentState) -> set[str]:
    perceive = getattr(state, "perceive", None)
    if perceive is not None and isinstance(perceive, dict):
        return perceive.setdefault(_PROVENANCE_KEY, set())
    # Fallback to in-memory tag
    if not hasattr(state, _PROVENANCE_KEY):
        setattr(state, _PROVENANCE_KEY, set())
    return getattr(state, _PROVENANCE_KEY)


class AuthUrlProvenanceGate(DecisionGate):
    """Intercepts hallucinated auth/oauth URLs without tool receipt provenance."""

    def register_provenance(self, state: AgentState, url: str) -> None:
        """Records a verified auth URL into the state's provenance set."""
        prov = _get_provenance_set(state)
        prov.add(url.strip())

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        text = decision.response_text or ""
        if not text:
            return decision

        found_urls = _URL_PATTERN.findall(text)
        auth_urls = [u for u in found_urls if is_auth_intent_url(u)]
        if not auth_urls:
            return decision

        prov = _get_provenance_set(state)
        unverified: list[str] = []
        for url in auth_urls:
            # Check direct match or normalized prefix match
            clean_url = url.rstrip("/.,;)")
            if not any(clean_url == p.rstrip("/.,;)") or clean_url in p or p in clean_url for p in prov):
                unverified.append(url)

        if not unverified:
            return decision

        # Rewrite decision: remove hallucinated URLs and inject tool guidance
        rewritten_text = text
        for bad_url in unverified:
            rewritten_text = rewritten_text.replace(
                bad_url,
                "（未经验证的第三方链接已阻断。动态授权与第三方连接严禁在文本中脑补，必须调用官方连接工具生成。）",
            )

        forced = Decision(
            decision_id=decision.decision_id,
            action_type=decision.action_type,
            rationale=(
                f"{decision.rationale or ''} [AuthUrlProvenanceGate intercepted {len(unverified)} unverified auth URL(s)]"
            ).strip(),
            confidence=decision.confidence,
            response_text=rewritten_text,
            tool_calls=decision.tool_calls,
            delegations=decision.delegations,
            degraded_from=decision.degraded_from,
            extra=decision.extra,
            task_progress=decision.task_progress,
            needs_approval=decision.needs_approval,
        )

        with contextlib_suppress():
            record_gate_decided(
                state,
                GateDecided(
                    event_id=new_id("gate"),
                    gate="AuthUrlProvenanceGate",
                    verdict="rewrite",
                    facts={
                        "unverified_auth_urls": unverified,
                        "action_type": decision.action_type.value if hasattr(decision.action_type, "value") else str(decision.action_type),
                    },
                ),
            )

        return forced


def contextlib_suppress():
    import contextlib
    return contextlib.suppress(Exception)
