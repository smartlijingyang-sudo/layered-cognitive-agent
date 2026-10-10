"""Plugin origin + trust envelope contracts (ADR-0199 §3.2 + §3.4).

``PluginOrigin`` records where a plugin came from (bundled / project / user /
pip) and what trust tier it was admitted at (core / trusted / untrusted),
together with the profile/bundle provenance that admitted it.

``TrustEnvelope`` bundles every active plugin origin plus the privileges
the caller has explicitly granted for the resulting run. ``SessionActivation``
(ADR-0199 §2.2.2) carries one ``TrustEnvelope``; privileges are checked
against the envelope at the Body / Guard stack seam (I-HPC-5:
provides ≠ privileges — undeclared privilege must fail-closed) and the
trust model enforces I-HPC-11 (信任默认拒绝 — untrusted origin defaults
to disabled).

Defined as pure data in the ``contracts`` layer: no I/O, no env reads,
no logging, no imports from ``lca.harness``, ``lca.application``,
``lca.infrastructure``, ``lca.cognition``, ``lca.runtime``, ``lca.agent``
or ``lca.plugins``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, Self, cast

__all__ = (
    "EMPTY_TRUST_ENVELOPE",
    "RULE_DEFAULTS",
    "PluginOrigin",
    "PluginSource",
    "PluginTrustLevel",
    "TrustEnvelope",
    "get_current_trust_envelope",
    "trust_envelope_scope",
)


PluginSource = Literal["bundled", "project", "user", "pip"]
"""Plugin provenance source (ADR-0199 §3.4).

- ``bundled`` — repo ``bundles/`` (shipped with LCA itself).
- ``project`` — project-local directory such as ``.lca/plugins/``.
- ``user`` — user-personal plugin location.
- ``pip`` — pip-installed entry-point plugin.
"""

PluginTrustLevel = Literal["core", "trusted", "untrusted"]
"""Plugin trust tier (ADR-0199 §3.4).

- ``core`` — reserved for bundled plugins; the kernel depends on these.
- ``trusted`` — operator-vetted source; may opt in via profile.
- ``untrusted`` — default for ``project`` and ``pip``; must be explicitly
  enabled in a profile and fail-closed on privilege escalation (I-HPC-11).
"""

RULE_DEFAULTS: frozenset[str] = frozenset({"platform.basic", "hitl.interact"})
"""规则默认 grant 集（ADR-0292 C2「用户显式授权 + 规则默认」）。

- ``platform.basic`` — 平台基础工具的占位 grant；grant-agnostic 工具不受
  运行时授权检查约束，该条目保证 envelope 非空校验通过。
- ``hitl.interact`` — HITL 交互工具（askUserQuestion / request_box_help）
  的规则默认 grant；它们是审批通道本身，不是需要用户显式授权的副作用。

``resolve_activation`` 构造真实 envelope 时把 ``load_grants(home)`` 的
assistant grants 与 ``RULE_DEFAULTS`` 合并（见 ADR-0292 §10 P3）。
"""

_CORE_ONLY_SOURCES: frozenset[str] = frozenset({"bundled"})
"""Sources that are allowed to claim ``trust="core"`` (ADR-0199 §3.4)."""

_NEVER_CORE_SOURCES: frozenset[str] = frozenset({"project", "pip"})
"""Sources that must NOT claim ``trust="core"`` (ADR-0199 §3.4)."""


@dataclass(frozen=True, slots=True)
class PluginOrigin:
    """Provenance + trust tier for a single plugin (ADR-0199 §3.4).

    The defaults per ADR-0199 §3.4 are *informational* — the constructor
    records the observed values, not policy. Policy enforcement (e.g.
    disabling untrusted origins by default, I-HPC-11) lives in the
    harness / resolve layer; this dataclass only rejects combinations
    that are categorically invalid (e.g. ``pip`` claiming ``"core"``).
    """

    source: PluginSource
    trust: PluginTrustLevel
    enabled_by: str
    discovered_at: str

    def __post_init__(self) -> None:
        if not self.enabled_by:
            raise ValueError("PluginOrigin.enabled_by must be non-empty")
        if not self.discovered_at:
            raise ValueError("PluginOrigin.discovered_at must be non-empty")
        if self.source in _NEVER_CORE_SOURCES and self.trust == "core":
            raise ValueError(
                f"PluginOrigin(source={self.source!r}) cannot claim trust='core'; "
                "'core' is reserved for bundled plugins (ADR-0199 §3.4)"
            )
        if self.source in _CORE_ONLY_SOURCES and self.trust != "core":
            raise ValueError(
                f"PluginOrigin(source={self.source!r}) requires trust='core' "
                "(ADR-0199 §3.4: bundled plugins ship as part of the kernel)"
            )


def _build_empty_envelope() -> TrustEnvelope:
    """Construct the empty singleton without triggering ``__post_init__``.

    The empty envelope is a sentinel — its origin and privilege sets are
    non-empty so the validation invariants pass, but the origin carries a
    synthetic ``<empty>`` provenance marker and the privilege set holds
    only the synthetic ``trust.empty`` verb. It is *not* a valid envelope
    to attach to a :class:`SessionActivation`; only fail-closed checks
    (e.g. doctor reports, kernel startup before any plugin has been
    admitted) should read it.
    """
    sentinel_origin = PluginOrigin(
        source="bundled",
        trust="core",
        enabled_by="<empty-sentinel>",
        discovered_at="<empty-sentinel>",
    )
    obj = object.__new__(TrustEnvelope)
    object.__setattr__(obj, "origins", (sentinel_origin,))
    object.__setattr__(obj, "granted_privileges", frozenset({"trust.empty"}))
    return obj


@dataclass(frozen=True, slots=True)
class TrustEnvelope:
    """Activated plugin origins and the granted privileges (ADR-0199 §3.4).

    One ``TrustEnvelope`` is attached to a :class:`SessionActivation`
    (ADR-0199 §2.2.2) and represents the closed set of plugins + the
    privilege ceiling for a single run. ``granted_privileges`` uses the
    same dotted ``capability.verb`` form as ``CommandEnvelope`` (ADR-0115
    / C5 capability 三维单调).
    """

    origins: tuple[PluginOrigin, ...]
    granted_privileges: frozenset[str]

    def __post_init__(self) -> None:
        if not self.origins:
            raise ValueError(
                "TrustEnvelope.origins must be non-empty; "
                "an envelope with zero origins has no auditable closure"
            )
        if not isinstance(self.granted_privileges, frozenset):
            raise ValueError(
                "TrustEnvelope.granted_privileges must be a frozenset "
                "(mutable sets break the frozen envelope contract)"
            )
        if not self.granted_privileges:
            raise ValueError(
                "TrustEnvelope.granted_privileges must be non-empty; "
                "an envelope without explicit privileges fails closed (I-HPC-11)"
            )
        if any(not privilege for privilege in self.granted_privileges):
            raise ValueError("TrustEnvelope.granted_privileges must not contain empty strings")

    @classmethod
    def empty(cls) -> Self:
        """Return the known empty singleton.

        Used by the kernel as the *zero* trust envelope before any
        plugin has been admitted. It is intentionally not a valid
        :class:`TrustEnvelope` for runtime use — :meth:`grants` returns
        ``False`` for every real privilege, so attaching it to a
        :class:`SessionActivation` and then attempting any action
        fail-closes by construction.
        """
        return cast("Self", EMPTY_TRUST_ENVELOPE)

    def grants(self, privilege: str) -> bool:
        """Pure membership check: is ``privilege`` in the granted set?"""
        return privilege in self.granted_privileges


EMPTY_TRUST_ENVELOPE: TrustEnvelope = _build_empty_envelope()
"""Known-empty singleton returned by :meth:`TrustEnvelope.empty`.

Carries one synthetic bundled/core origin and one synthetic privilege so
that the dataclass invariants (``non-empty origins``, ``non-empty
privileges``) pass. It is *not* a valid envelope for attaching to a
:class:`SessionActivation` — only empty-envelope checks (doctor reports,
kernel startup before any plugin has been admitted) should read it.
"""


# ── Ambient TrustEnvelope seam (ADR-0292 section 10) ──────────────────
#
# Mirrors ``lca.contracts.models.core.execution.decision``
# (``get_current_decision`` + ``decision_scope``): a contextvar carries the
# TrustEnvelope bound for the current run, so authorization gates (e.g.
# ``act.approve.gate``) can consult the grant set without a hard dependency
# on the session wiring. ``asyncio.create_task`` copies the context, so
# gates invoked downstream of ``trust_envelope_scope`` observe the envelope
# bound for them.
# ---------------------------------------------------------------------------

_current_trust_envelope: ContextVar[TrustEnvelope | None] = ContextVar(
    "lca_current_trust_envelope", default=None
)


def get_current_trust_envelope() -> TrustEnvelope | None:
    """Return the TrustEnvelope bound for the current run, or ``None`` when unbound.

    ``None`` = no envelope scope is active (legacy / offline / unit-test
    paths): ADR-0292 section-10 gates treat it as "no grants recorded" and
    fail closed on privileged actions.
    """
    return _current_trust_envelope.get()


@contextmanager
def trust_envelope_scope(envelope: TrustEnvelope) -> Iterator[None]:
    """Bind *envelope* as the ambient TrustEnvelope for the wrapped block.

    The production binder is the session/run driver (ADR-0199: the
    ``SessionActivation`` carries the ``TrustEnvelope``); gates read it via
    :func:`get_current_trust_envelope`. LIFO reset on exit.
    """
    token = _current_trust_envelope.set(envelope)
    try:
        yield
    finally:
        _current_trust_envelope.reset(token)
