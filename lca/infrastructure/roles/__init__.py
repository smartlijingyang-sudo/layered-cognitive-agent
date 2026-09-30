"""Role-library file implementation (ADR-0042)."""

from lca.infrastructure.roles.role_library import (
    AGENCY_ROLES_DIR_ENV,
    FileRoleLibrary,
    resolve_roles_dir,
)

__all__ = ["AGENCY_ROLES_DIR_ENV", "FileRoleLibrary", "resolve_roles_dir"]
