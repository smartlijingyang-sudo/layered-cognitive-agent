"""Auto-generated surface skeleton for upstream ``typert/generator/src/model.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/generator/src/model.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AccessorMemberModel",
    "CrossFaceLink",
    "DocumentationModel",
    "EnumMemberModel",
    "EventModel",
    "ExportModel",
    "FaceModel",
    "InvocationModel",
    "InvocationParameterModel",
    "JsDocTagModel",
    "KeywordTypeName",
    "MemberBase",
    "MemberModel",
    "MemberVisibility",
    "MethodMemberModel",
    "ObjectModel",
    "PackageModel",
    "ParameterModel",
    "PropertyMemberModel",
    "RemoteBoundaryModel",
    "RemoteTypeImportModel",
    "SchemaModel",
    "ServiceModel",
    "SignatureMemberModel",
    "SignatureModel",
    "SourceDeclarationModel",
    "SourceLocation",
    "SymbolId",
    "TemplateSpanModel",
    "TupleElementModel",
    "TypeDeclarationModel",
    "TypeDeclarationPartModel",
    "TypeGraph",
    "TypeNodeId",
    "TypeNodeModel",
    "TypeOperatorName",
    "TypeParameterModel",
    "TypeTargetModel",
    "TypertFace",
    "WorkspaceModel",
    "childTypeNodeIds",
]

KeywordTypeName: TypeAlias = object  # port: surface stub

MemberModel: TypeAlias = object  # port: surface stub

MemberVisibility: TypeAlias = object  # port: surface stub

SymbolId: TypeAlias = object  # port: surface stub

TypeNodeId: TypeAlias = object  # port: surface stub

TypeNodeModel: TypeAlias = object  # port: surface stub

TypeOperatorName: TypeAlias = object  # port: surface stub

TypeTargetModel: TypeAlias = object  # port: surface stub

TypertFace: TypeAlias = object  # port: surface stub

def childTypeNodeIds(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``childTypeNodeIds``."""
    raise NotImplementedError("port childTypeNodeIds from typert/generator/src/model.ts")

class AccessorMemberModel(Protocol):
    """Surface stub for upstream interface ``AccessorMemberModel``."""
    pass

class CrossFaceLink(Protocol):
    """Surface stub for upstream interface ``CrossFaceLink``."""
    pass

class DocumentationModel(Protocol):
    """Surface stub for upstream interface ``DocumentationModel``."""
    pass

class EnumMemberModel(Protocol):
    """Surface stub for upstream interface ``EnumMemberModel``."""
    pass

class EventModel(Protocol):
    """Surface stub for upstream interface ``EventModel``."""
    pass

class ExportModel(Protocol):
    """Surface stub for upstream interface ``ExportModel``."""
    pass

class FaceModel(Protocol):
    """Surface stub for upstream interface ``FaceModel``."""
    pass

class InvocationModel(Protocol):
    """Surface stub for upstream interface ``InvocationModel``."""
    pass

class InvocationParameterModel(Protocol):
    """Surface stub for upstream interface ``InvocationParameterModel``."""
    pass

class JsDocTagModel(Protocol):
    """Surface stub for upstream interface ``JsDocTagModel``."""
    pass

class MemberBase(Protocol):
    """Surface stub for upstream interface ``MemberBase``."""
    pass

class MethodMemberModel(Protocol):
    """Surface stub for upstream interface ``MethodMemberModel``."""
    pass

class ObjectModel(Protocol):
    """Surface stub for upstream interface ``ObjectModel``."""
    pass

class PackageModel(Protocol):
    """Surface stub for upstream interface ``PackageModel``."""
    pass

class ParameterModel(Protocol):
    """Surface stub for upstream interface ``ParameterModel``."""
    pass

class PropertyMemberModel(Protocol):
    """Surface stub for upstream interface ``PropertyMemberModel``."""
    pass

class RemoteBoundaryModel(Protocol):
    """Surface stub for upstream interface ``RemoteBoundaryModel``."""
    pass

class RemoteTypeImportModel(Protocol):
    """Surface stub for upstream interface ``RemoteTypeImportModel``."""
    pass

class SchemaModel(Protocol):
    """Surface stub for upstream interface ``SchemaModel``."""
    pass

class ServiceModel(Protocol):
    """Surface stub for upstream interface ``ServiceModel``."""
    pass

class SignatureMemberModel(Protocol):
    """Surface stub for upstream interface ``SignatureMemberModel``."""
    pass

class SignatureModel(Protocol):
    """Surface stub for upstream interface ``SignatureModel``."""
    pass

class SourceDeclarationModel(Protocol):
    """Surface stub for upstream interface ``SourceDeclarationModel``."""
    pass

class SourceLocation(Protocol):
    """Surface stub for upstream interface ``SourceLocation``."""
    pass

class TemplateSpanModel(Protocol):
    """Surface stub for upstream interface ``TemplateSpanModel``."""
    pass

class TupleElementModel(Protocol):
    """Surface stub for upstream interface ``TupleElementModel``."""
    pass

class TypeDeclarationModel(Protocol):
    """Surface stub for upstream interface ``TypeDeclarationModel``."""
    pass

class TypeDeclarationPartModel(Protocol):
    """Surface stub for upstream interface ``TypeDeclarationPartModel``."""
    pass

class TypeGraph(Protocol):
    """Surface stub for upstream interface ``TypeGraph``."""
    pass

class TypeParameterModel(Protocol):
    """Surface stub for upstream interface ``TypeParameterModel``."""
    pass

class WorkspaceModel(Protocol):
    """Surface stub for upstream interface ``WorkspaceModel``."""
    pass
