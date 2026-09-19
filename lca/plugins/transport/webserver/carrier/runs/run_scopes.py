"""Shared run-identity ambient scopes for initial execution and HIL resume."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from lca.infrastructure.search.scope.scope import search_run_scope
from lca.infrastructure.tools.run.attachment_scope import run_attachment_scope
from lca.infrastructure.tools.run.finalizer import run_id_scope


@contextmanager
def run_identity_scopes(
    run_id: str,
    attachment_ids: Sequence[str] = (),
) -> Iterator[None]:
    """Bind run identity, attachment, and search ambits.

    The initial execution path and the HIL resume path must expose the same
    run-scoped contextvars. Tools that discover their run_id from the ambient
    scope (sandbox runtime, attachment staging, search routing) otherwise fail
    on resume with ``sandbox runtime requires an active run_id scope``.
    """
    with (
        run_id_scope(run_id),
        run_attachment_scope(attachment_ids),
        search_run_scope(),
    ):
        yield


__all__ = ["run_identity_scopes"]
