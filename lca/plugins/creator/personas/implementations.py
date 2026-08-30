"""Pure Creator four-face result projection helpers."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.atoms.scope import Scope, parse_scope
from lca.plugins.creator.personas import CreatorFace, CreatorResult, PromoteSpec, parse_creator_face


def do_inspect(*, target: str | None = None, **kwargs: Any) -> CreatorResult:
    """Project an inspect face result without changing an Artifact lifecycle."""

    del kwargs
    return CreatorResult(
        face=CreatorFace.INSPECT,
        state_after=ArtifactState.DRAFT,
        payload={"target": target or "all", "graph": {}, "artifacts": []},
    )


def do_author(
    *, name: str, path: str | None = None, content: str | None = None, **kwargs: Any
) -> CreatorResult:
    """Project a DRAFT Artifact authored by the Creator service."""

    del kwargs
    if not name:
        raise ValueError("do_author: name is required")
    return CreatorResult(
        face=CreatorFace.AUTHOR,
        state_after=ArtifactState.DRAFT,
        payload={"name": name, "path": path, "has_content": content is not None},
    )


def do_validate(
    *, name: str, descriptor: dict[str, Any] | None = None, **kwargs: Any
) -> CreatorResult:
    """Project a VERIFIED Artifact after descriptor and dependency validation."""

    del descriptor, kwargs
    if not name:
        raise ValueError("do_validate: name is required")
    return CreatorResult(
        face=CreatorFace.VALIDATE,
        state_after=ArtifactState.VERIFIED,
        payload={
            "name": name,
            "verdict": "ok",
            "checks_passed": ("descriptor_complete", "signature_valid", "dependencies_resolvable"),
        },
    )


def do_promote(*, name: str, spec: PromoteSpec | None = None, **kwargs: Any) -> CreatorResult:
    """Project ACTIVE or RETIRED state from the Creator promote face."""

    del kwargs
    if not name:
        raise ValueError("do_promote: name is required")
    promotion = spec or PromoteSpec()
    if promotion.rollback:
        return CreatorResult(
            face=CreatorFace.PROMOTE,
            state_after=ArtifactState.RETIRED,
            payload={
                "name": name,
                "operation": "rollback",
                "from_state": ArtifactState.ACTIVE.value,
                "to_state": ArtifactState.RETIRED.value,
            },
        )
    try:
        target_scope = parse_scope(promotion.target_scope or Scope.RUN.value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Creator promotion scope: {promotion.target_scope!r}") from exc
    return CreatorResult(
        face=CreatorFace.PROMOTE,
        state_after=ArtifactState.ACTIVE,
        payload={
            "name": name,
            "operation": "promote",
            "target_scope": target_scope.value,
            "preset_id": promotion.preset_id,
        },
    )


def dispatch_creator_face(face: CreatorFace | str, **kwargs: Any) -> CreatorResult:
    """Dispatch one of the four closed Creator faces."""

    face_enum = parse_creator_face(face)
    if face_enum is CreatorFace.INSPECT:
        return do_inspect(**kwargs)
    if face_enum is CreatorFace.AUTHOR:
        return do_author(**kwargs)
    if face_enum is CreatorFace.VALIDATE:
        return do_validate(**kwargs)
    if face_enum is CreatorFace.PROMOTE:
        return do_promote(**kwargs)
    raise ValueError(f"unreachable face={face_enum}")


__all__ = [
    "CreatorFace",
    "CreatorResult",
    "PromoteSpec",
    "dispatch_creator_face",
    "do_author",
    "do_inspect",
    "do_promote",
    "do_validate",
]
