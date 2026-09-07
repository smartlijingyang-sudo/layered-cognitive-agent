"""Resource ID contract — namespaced read-only content (ADR-0199 §3.1 / P4-01).

Per ADR-0199 §3.1 ``resources`` is the 4th plugin dimension:
distributable, read-only content (skills / roles / prompts). Per §3.3 #7:
"resource 不得隐式获得执行权限". Per §4 resource references use
namespaced IDs of the form ``"<kind>:<namespace>/<name>"``.

Examples:
  - ``skill:memory/retrieval``
  - ``prompt:coding_agent/system``
  - ``role:assistants/solo``

ResourceId is the SSOT for resource references in the plugin tree.
A plugin declares resources via ``PluginContract.resources: tuple[ResourceId, ...]``
(added in a future PR). At runtime, the compiled plan's ResourceRegistry
maps these IDs to actual content providers.

Per I-HPC-6: resource content is read-only and never gains execute permission.
Content providers MUST NOT register executable capabilities via resource scans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

# Closed set of resource kinds per ADR-0199 §4 table.
# Adding a new kind requires an ADR.
ResourceKind = Literal["skill", "prompt", "role"]

# Closed set of namespaces. Per ADR-0199 §4, content namespaces are:
#   - skill: namespace is the skill category (memory / coding / etc.)
#   - prompt: namespace is the agent id
#   - role: namespace is the assistant id
# The format ``"<kind>:<namespace>/<name>"`` is canonical.

# Reserved namespace strings — used to prevent user-declared resources from
# shadowing system resources.
RESERVED_NAMESPACES: Final[frozenset[str]] = frozenset(
    {
        "system",
        "internal",
        "_reserved",
    }
)

# Valid name pattern: lowercase alphanumerics + underscores + dashes, no slashes,
# no colons, no whitespace. This keeps resource refs grep-able and round-trippable.
_NAME_PATTERN: Final[str] = r"^[a-z0-9_\-]+$"
_NAME_RE: Final[re.Pattern[str]] = re.compile(_NAME_PATTERN)

# Namespace pattern: same as name (resource refs are simple).
_NAMESPACE_RE: Final[re.Pattern[str]] = re.compile(_NAME_PATTERN)


@dataclass(frozen=True, slots=True)
class ResourceId:
    """A namespaced read-only content identifier (ADR-0199 P4-01).

    Format: ``"<kind>:<namespace>/<name>"``.

    Per I-HPC-6: ResourceId is the canonical form for resource references.
    Content providers receive ResourceId and return read-only content;
    they MUST NOT register executable capabilities.
    """

    kind: ResourceKind
    namespace: str
    name: str

    def __post_init__(self) -> None:
        if not _NAMESPACE_RE.match(self.namespace):
            raise ValueError(
                f"ResourceId namespace must match {_NAME_PATTERN}; got {self.namespace!r}"
            )
        if not _NAME_RE.match(self.name):
            raise ValueError(f"ResourceId name must match {_NAME_PATTERN}; got {self.name!r}")
        if self.namespace in RESERVED_NAMESPACES:
            raise ValueError(
                f"ResourceId namespace {self.namespace!r} is reserved; "
                f"choose a non-reserved namespace. Reserved: {sorted(RESERVED_NAMESPACES)}"
            )

    def to_ref(self) -> str:
        """Return the canonical string form: ``<kind>:<namespace>/<name>``."""
        return f"{self.kind}:{self.namespace}/{self.name}"

    @classmethod
    def from_ref(cls, ref: str) -> ResourceId:
        """Parse a reference string back into a ResourceId.

        Format: ``"<kind>:<namespace>/<name>"``.
        Raises ValueError on invalid format or unrecognised kind.
        """
        if not isinstance(ref, str):
            raise ValueError(f"resource ref must be a string; got {type(ref).__name__}")

        # Split on the first ':' to separate kind from rest
        if ":" not in ref:
            raise ValueError(
                f"resource ref must contain ':' separating kind from namespace/name; got {ref!r}"
            )
        kind_str, _, rest = ref.partition(":")
        if kind_str not in ("skill", "prompt", "role"):
            raise ValueError(
                f"resource ref kind must be one of (skill, prompt, role); got {kind_str!r}"
            )

        # Split on the first '/' to separate namespace from name
        if "/" not in rest:
            raise ValueError(
                f"resource ref must contain '/' separating namespace from name; got {ref!r}"
            )
        namespace, _, name = rest.partition("/")

        return cls(
            kind=kind_str,  # type: ignore[arg-type]
            namespace=namespace,
            name=name,
        )


__all__ = (
    "RESERVED_NAMESPACES",
    "ResourceId",
    "ResourceKind",
)
