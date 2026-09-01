"""``spine.reflector.source`` — I17 source-level trace FieldProducer.

Task 9.1: implements the third leg of the D11 auto-source scheme
(ADR-0165.1 §7.5.4). Every ``*.start`` event in the spine MUST carry
audit-grade evidence of where the call originated from and which
local state was in scope at the call site; this producer is the
plumbing that makes that contract hold without instrumenting every
caller.

It contributes three keys into ``EventRecord.payload``:

- ``source_location`` — ``{file, line, function}`` of the call site
  (the caller of ``produce``, not ``produce`` itself).
- ``call_frames``     — list of up to 10 ``{file, line, function}``
  frames, **outermost first** (the deepest frame is the caller of
  ``produce``; the shallowest is the program entry point).
- ``locals_snapshot`` — ``{"pre_call": {name: repr_str}}`` with the
  total UTF-8 byte size capped at ``max_locals_bytes`` (default 4 KB).
  Values matching ``redact_patterns`` are replaced with ``"***"``.

Why ``outermost first``
-----------------------
``traceback.extract_stack()`` returns frames ordered with the *current*
frame last. Reversing the slice gives the outermost-first ordering,
which matches the visual layout of ``traceback.print_stack()`` and
makes the deepest frame (``index -1``) trivially the source_location
caller. We document this choice so consumers do not have to guess.

Why stdlib ``traceback`` / ``inspect`` (not a custom walker)
-----------------------------------------------------------
The controller's ruling for I17 is to mirror Java's
``Thread.currentThread().getStackTrace()`` via Python stdlib. ``traceback.extract_stack``
and ``inspect.stack`` are battle-tested and capture the live frame
state we need (line numbers, function qualnames, current locals).
We do NOT walk frames manually; that path has bitten us before with
reference cycles and dead-frame snapshots.

Secret redaction
----------------
The default ``redact_patterns`` covers:

- OpenAI key shape (``sk-<16+ alphanumeric>``).
- Generic ``api_key=`` / ``secret=`` / ``password=`` / ``token=``
  assignments.
- Any attribute/key name that contains ``KEY`` / ``SECRET`` /
  ``PASSWORD`` / ``TOKEN`` (e.g. ``OPENAI_API_KEY``) — the *value* of
  such a key is replaced, regardless of the value's content.

Limits
------
- ``locals_snapshot`` is bounded by ``max_locals_bytes`` (default
  4096). When the cumulative UTF-8 size exceeds the cap, later
  entries are dropped and any partially written value is truncated
  with a trailing ``"…"`` so consumers can see the truncation
  happened. The cap counts only the *values*; keys and the JSON
  envelope overhead are not counted.
- ``SourceAttacher`` MUST never raise inside ``produce``: a broken
  reflection path would block every instrumented call. All
  ``OSError`` / ``AttributeError`` from ``inspect`` are swallowed and
  the affected field is replaced with a well-formed placeholder.
"""

from __future__ import annotations

import inspect
import re
import traceback
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.spine.producer import Phase
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin

# Maximum stack frames we ever return in ``call_frames`` — matches
# the brief's "up to 10 frames" requirement.
_MAX_FRAMES = 10

# Tail marker appended when a single value is truncated to honour
# the ``max_locals_bytes`` cap. Three dots so the marker is itself a
# single UTF-8 byte overhead and visually distinct from ``"..."``.
_TRUNCATION_MARKER = "…"

# Replacement for any redacted value. Kept short so redaction never
# bloats the snapshot, and so the cap math is predictable.
_REDACTED_VALUE = "***"

# Regex fragment that matches any identifier-ish key containing
# KEY / SECRET / PASSWORD / TOKEN. Used as a *key-name* check
# (case-sensitive, per the brief); the value gets redacted
# regardless of its shape.
_SECRET_KEY_FRAGMENT = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN)")

# Default regex patterns applied on top of any caller-supplied ones.
# OpenAI key, generic ``api_key=...`` assignments, and the like.
_DEFAULT_REDACT_PATTERNS: tuple[str, ...] = (
    r"sk-[A-Za-z0-9]{16,}",
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+",
)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Plain ``{file, line, function}`` triple for a single call site.

    Frozen + slotted so producers cannot mutate it after assembly and
    so the size is predictable when serialised to JSON.

    Implements ``Mapping`` semantics (``__getitem__`` / ``keys`` /
    ``__iter__``) so consumers that prefer dict-style access
    (``frame["file"]``, ``set(frame.keys())``) work alongside the
    attribute-style access (``frame.file``) the brief's call-site
    test uses. ``asdict()`` is the canonical serializer entry point
    when JSON-shape is required.
    """

    file: str
    line: int
    function: str

    def __getitem__(self, key: str) -> Any:
        if key not in ("file", "line", "function"):
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Any:
        yield "file"
        yield "line"
        yield "function"

    def keys(self) -> Any:
        return iter(("file", "line", "function"))

    def asdict(self) -> dict[str, Any]:
        """Return ``{"file": ..., "line": ..., "function": ...}``."""
        return {
            "file": self.file,
            "line": self.line,
            "function": self.function,
        }


@dataclass(frozen=True, slots=True)
class LocalsSnapshot:
    """Snapshot of locals at the call site, with secrets redacted.

    The brief's tests use ``fields["locals_snapshot"].pre_call`` as
    the dict to scan for secrets; this dataclass keeps the envelope
    shape stable so future revisions can add ``post_call`` /
    ``exception_call`` without breaking consumers. ``pre_call`` is
    a nested mapping of ``{envelope: {name: repr_str}}``; envelopes
    are currently ``"locals"`` (frame locals) and ``"ctx"``
    (``ctx.__dict__`` / class attrs).
    """

    pre_call: dict[str, dict[str, str]]


class SourceAttacher:
    """I17 source-level trace FieldProducer.

    Attributes
    ----------
    name:
        ``"spine.reflector.source"`` — matches the plugin manifest id
        and the merge key consumed by ``EmitPipeline``.
    priority:
        ``8`` — runs after spantree (``5``) and signature (``100`` is
        currently higher-numbered than us, so signature runs later in
        the merge; lower numbers run first so on conflict we win).
        Sits ahead of context (``20``) so source_location is stamped
        before any post-state mutations overwrite keyspace.
    enabled:
        Profile-level toggle; the plugin boot installs the producer
        and the pipeline skips it when ``enabled=False``.
    """

    name: str = "spine.reflector.source"
    priority: int = 8
    enabled: bool = True

    def __init__(
        self,
        *,
        max_locals_bytes: int = 4096,
        redact_patterns: list[str] | None = None,
        priority: int = 8,
    ) -> None:
        """Configure cap and redaction policy.

        ``max_locals_bytes`` caps the cumulative UTF-8 byte size of
        every value string in ``locals_snapshot.pre_call``. Keys and
        the JSON envelope are not counted against the cap.

        ``redact_patterns`` are compiled with ``re.error``-on-invalid
        so a misconfigured profile fails loud at boot rather than
        silently leaking secrets.
        """
        if max_locals_bytes <= 0:
            raise ValueError("max_locals_bytes must be positive")
        self.max_locals_bytes = max_locals_bytes
        self.priority = priority
        self._patterns: tuple[re.Pattern[str], ...] = tuple(
            re.compile(p) for p in _DEFAULT_REDACT_PATTERNS
        ) + tuple(re.compile(p) for p in (redact_patterns or ()))

    def produce(
        self,
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any] | None,
        ctx: Any,
        span: Any,
        phase: Phase,
    ) -> dict[str, Any]:
        """Return ``source_location`` + ``call_frames`` + ``locals_snapshot``.

        ``phase`` is accepted for protocol conformance but the
        producer is phase-agnostic — the same triple is contributed
        in ``"pre"`` / ``"post"`` / ``"exception"``. The ``*.start``
        enforcement (PR-9 / I17) lives in ``EmitPipeline``; this
        producer simply assembles the data.

        ``fn`` / ``args`` / ``kwargs`` / ``span`` are accepted but not
        consumed — the source_location is the call site of *this*
        ``produce``, not the call site of ``fn``.
        """
        del fn, args, kwargs, span, phase  # documented unused; see docstring.

        try:
            location = self._source_location()
            frames = self._call_frames()
            snapshot = self._locals_snapshot(ctx)
        except (OSError, AttributeError, KeyError, TypeError):
            # ``inspect`` raises ``OSError`` for builtins / shadowed
            # frames; ``AttributeError`` for objects that drop
            # ``__dict__`` between when we start and when we read.
            # None of these must escape the merge path.
            return {
                "source_location": SourceLocation("", 0, ""),
                "call_frames": [],
                "locals_snapshot": LocalsSnapshot(pre_call={}),
            }

        return {
            "source_location": location,
            "call_frames": frames,
            "locals_snapshot": snapshot,
        }

    # ── internal helpers ─────────────────────────────────────────────

    def _source_location(self) -> SourceLocation:
        """Capture the call site of ``produce`` (not ``produce`` itself).

        Walks back from ``inspect.currentframe()`` through any frames
        that belong to this module (every helper above
        ``_source_location`` is a frame too — ``produce``,
        ``_call_frames``, etc.) and lands on the first user frame.
        For the brief's nested ``a_function`` test that is
        ``a_function``'s frame.

        ``__file__``-based identity is fragile against ``__main__``,
        symlinks, and zipimports; the canonical check is the frame's
        ``f_globals["__name__"]`` matching this module's name.
        """
        module_name = __name__
        frame = inspect.currentframe()
        if frame is None:
            return SourceLocation("", 0, "")
        # Walk the call stack until we leave this module.
        while frame is not None:
            candidate = frame.f_back
            if candidate is None:
                break
            if candidate.f_globals.get("__name__") != module_name:
                # ``co_qualname`` is dotted (``"<locals>.a_function"``);
                # the brief expects the unqualified function name.
                # Strip the leading qualname module and any enclosing
                # ``<locals>`` so ``"<locals>.a_function"`` -> ``"a_function"``.
                qualname = str(getattr(candidate.f_code, "co_qualname", candidate.f_code.co_name))
                function = qualname.rsplit(".<locals>.", 1)[-1]
                return SourceLocation(
                    file=candidate.f_code.co_filename,
                    line=int(candidate.f_lineno),
                    function=function,
                )
            frame = candidate
        return SourceLocation("", 0, "")

    def _call_frames(self) -> list[SourceLocation]:
        """Return up to 10 frames, **outermost first**.

        ``traceback.extract_stack(limit=_MAX_FRAMES + N)`` already
        strips the tail of the stack to ``limit``; we over-fetch by a
        small margin so the producer's own frames (``produce``,
        ``_call_frames``, ``_source_location``) are removed before we
        hand the list to ``EmitPipeline``. The remaining frames are
        reversed so the shallowest caller is ``[0]``.
        """
        # Over-fetch to leave room for stripping the producer's own
        # stack frames. ``+8`` is a documented upper bound on the
        # producer's internal frame depth (``produce`` -> ``produce``
        # helpers -> helpers -> ``traceback`` itself).
        raw = traceback.extract_stack(limit=_MAX_FRAMES + 8)
        # Strip trailing frames belonging to this producer. Walk
        # backwards until we leave the ``source.py`` module.
        while raw and raw[-1].filename.endswith("source.py"):
            raw.pop()
        # Materialise to a list so mypy sees ``StackSummary`` -> ``list[FrameSummary]``
        # and downstream slicing / reversing stays type-stable.
        frames: list[traceback.FrameSummary] = list(raw)
        # Trim to the brief's cap.
        frames = frames[-_MAX_FRAMES:]
        # ``extract_stack`` is innermost-first; flip to outermost-first.
        frames.reverse()
        result: list[SourceLocation] = []
        for frame in frames:
            qualname = str(frame.name)
            function = qualname.rsplit(".<locals>.", 1)[-1]
            lineno = frame.lineno if frame.lineno is not None else 0
            result.append(
                SourceLocation(
                    file=str(frame.filename),
                    line=lineno,
                    function=function,
                )
            )
        return result

    def _locals_snapshot(self, ctx: Any) -> LocalsSnapshot:
        """Build the redacted, byte-capped locals snapshot.

        Scans:

        - The caller's ``f_locals`` (locals of the frame that called
          ``produce``), under the ``"locals"`` envelope key.
        - ``ctx.__dict__`` (when ``ctx`` exposes it), under the
          ``"ctx"`` envelope key. This is what makes
          ``ctx.token = "sk-abc…"`` reachable for the brief's
          redaction test.

        Envelope keys are *not* redacted (they are the producer's own
        keys, never user data). Only the values inside them can be
        replaced with ``"***"``.

        The cap counts only the *values* — keys and the JSON braces
        are overhead the cap deliberately ignores.
        """
        snapshot: dict[str, dict[str, str]] = {"locals": {}, "ctx": {}}
        caller_locals = self._safe_caller_locals()
        if caller_locals:
            snapshot["locals"] = self._redact_mapping(caller_locals)
        ctx_attrs = self._safe_ctx_attrs(ctx)
        if ctx_attrs:
            snapshot["ctx"] = self._redact_mapping(ctx_attrs)
        # Apply the byte cap envelope-by-envelope so callers can
        # still tell ``ctx`` from ``locals`` after truncation. The
        # cap is split evenly between the two envelopes; overflow in
        # one envelope does not eat the other's budget.
        return LocalsSnapshot(pre_call=self._cap_envelopes(snapshot))

    def _cap_envelopes(self, envelopes: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        """Apply ``max_locals_bytes`` across each envelope independently.

        Each envelope (``"locals"``, ``"ctx"``) gets half the budget
        so neither can starve the other. Values are kept in insertion
        order; once the envelope's budget is exhausted, later entries
        are dropped and the last fitting entry is truncated with
        ``"…"``.
        """
        if not envelopes:
            return {}
        envelopes_count = len(envelopes)
        per_envelope = max(1, self.max_locals_bytes // envelopes_count)
        capped: dict[str, dict[str, str]] = {}
        for name, entries in envelopes.items():
            capped[name] = self._cap_values(entries, cap=per_envelope)
        return capped

    def _safe_caller_locals(self) -> dict[str, Any]:
        """Return ``f_locals`` of the frame that called ``produce``.

        Some frames (e.g. ``<string>`` snippets, C-implemented
        frames) expose ``f_locals`` that raises on access; in those
        cases we return an empty dict rather than letting the merge
        path explode.
        """
        frame = inspect.currentframe()
        if frame is None:
            return {}
        caller = frame.f_back
        if caller is None:
            return {}
        try:
            locals_dict = caller.f_locals
        except (OSError, AttributeError, KeyError, TypeError):
            return {}
        if not isinstance(locals_dict, dict):
            return {}
        return dict(locals_dict)

    @staticmethod
    def _safe_ctx_attrs(ctx: Any) -> dict[str, Any]:
        """Return a copy of ``ctx`` attributes or ``{}`` when unavailable.

        First consults ``ctx.__dict__`` for instance attributes. When
        that is empty (class-level attributes only — the common
        ``type("Ctx", (), {"token": ...})()`` shape from the brief's
        tests) it falls back to enumerating ``dir(ctx)`` and
        ``getattr``-ing each public, non-callable name. The fallback
        matters because the brief's redaction test pins a value on
        the *class*, not the instance.

        Mocks that expose neither ``__dict__`` nor useful ``dir``
        collapse to ``{}`` so the merge path never explodes.
        """
        if ctx is None:
            return {}
        dunder_dict = getattr(ctx, "__dict__", None)
        if isinstance(dunder_dict, dict) and dunder_dict:
            return dict(dunder_dict)
        # Class-level fallback. Walk ``dir(ctx)`` and pull values;
        # skip dunders and callables so we don't try to ``repr`` a
        # bound method or a meta attribute.
        attrs: dict[str, Any] = {}
        try:
            names = list(dir(ctx))
        except TypeError:
            return {}
        for name in names:
            if name.startswith("_"):
                continue
            try:
                value = getattr(ctx, name)
            except Exception:  # noqa: S112 — descriptor may raise on access.
                continue
            if callable(value):
                continue
            attrs[name] = value
        return attrs

    def _redact_mapping(self, mapping: dict[str, Any]) -> dict[str, str]:
        """Apply redaction to ``mapping`` and return a ``{key: repr_str}`` dict.

        Two layers of redaction:

        1. Pattern-based: every compiled regex from ``self._patterns``
           is matched against ``repr(value)``; matches collapse to
           ``"***"``.
        2. Key-name-based: any key containing ``KEY`` / ``SECRET`` /
           ``PASSWORD`` / ``TOKEN`` is always redacted regardless of
           the value shape.
        """
        redacted: dict[str, str] = {}
        for key, value in mapping.items():
            text = self._safe_repr(value)
            if _SECRET_KEY_FRAGMENT.search(str(key)):
                redacted[str(key)] = _REDACTED_VALUE
                continue
            if self._matches_any_pattern(text):
                redacted[str(key)] = _REDACTED_VALUE
                continue
            redacted[str(key)] = text
        return redacted

    @staticmethod
    def _safe_repr(value: Any) -> str:
        """``repr(value)`` clamped to a sensible size.

        ``repr`` can produce gigabytes for pathological inputs (e.g.
        a 100 MB ``bytes`` literal). Clamp to a hard 4 KB ceiling so a
        single bad local cannot blow the snapshot past ``max_locals_bytes``.
        """
        try:
            text = repr(value)
        except Exception:
            return "<unrepresentable>"
        if len(text) > 4096:
            text = text[:4096] + _TRUNCATION_MARKER
        return text

    def _matches_any_pattern(self, text: str) -> bool:
        """Return ``True`` if any compiled pattern matches ``text``."""
        return any(pattern.search(text) for pattern in self._patterns)

    def _cap_values(self, flat: dict[str, str], cap: int | None = None) -> dict[str, str]:
        """Enforce ``max_locals_bytes`` on the cumulative values.

        Iterates in insertion order (Python 3.7+ guarantee) and drops
        later entries once the cap would be exceeded. Partially
        fitting entries are truncated with ``"…"`` so consumers know
        the value was clipped.

        ``cap`` overrides ``self.max_locals_bytes`` for this call —
        used by :meth:`_cap_envelopes` to split the budget across
        envelopes.
        """
        limit = cap if cap is not None else self.max_locals_bytes
        used = 0
        result: dict[str, str] = {}
        marker_bytes = len(_TRUNCATION_MARKER.encode("utf-8"))
        for key, value in flat.items():
            encoded = value.encode("utf-8")
            remaining = limit - used
            if remaining <= 0:
                break
            if len(encoded) <= remaining:
                result[key] = value
                used += len(encoded)
                continue
            truncated = encoded[: max(0, remaining - marker_bytes)]
            try:
                decoded = truncated.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                decoded = ""
            result[key] = decoded + _TRUNCATION_MARKER
            used += len(result[key].encode("utf-8"))
        return result


@plugin(
    id="spine.reflector.source",
    provides=("field_producer.source",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "SourceAttacher FieldProducer — injects I17 source_location / "
        "call_frames / locals_snapshot into every spine "
        "EventRecord.payload via EmitPipeline merge. Runs at priority 8 "
        "(after spantree=5, before context=20) so source-level trace "
        "evidence lands ahead of context-derived fields."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_source_attacher",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_source",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.source",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline",),
        emits=("field_producer.source",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Register a singleton ``SourceAttacher`` instance.

    No I/O, no state, no startup work beyond ``ctx.provide``; the
    ``L0`` layer is sufficient because every profile that wants I17
    coverage just declares this plugin in its enables list.
    """
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.source", SourceAttacher())


__all__ = ["LocalsSnapshot", "SourceAttacher", "SourceLocation", "setup"]
