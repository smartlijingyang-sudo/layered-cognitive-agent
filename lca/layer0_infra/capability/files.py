"""file_store seam Definition — owns ctx.file_store."""

from __future__ import annotations

from lca.layer0_infra.capability.dispatch import ProviderDispatch
from lca.layer0_infra.file_store import FileStore, StoredFile


class FileStoreService:
    """Service Definition：附件/产物存储。实现 FileStore 并转发给当前 Provider。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[FileStore]("file_store")

    def register(self, name: str, provider: FileStore, *, activate: bool = False) -> None:
        self.providers.register(name, provider, activate=activate)

    def current(self) -> FileStore:
        return self.providers.current()

    def put(
        self,
        *,
        data: bytes,
        name: str,
        mime_type: str,
        conversation_id: str | None = None,
    ) -> StoredFile:
        return self.providers.current().put(
            data=data, name=name, mime_type=mime_type, conversation_id=conversation_id
        )

    def get(self, attachment_id: str) -> StoredFile | None:
        return self.providers.current().get(attachment_id)

    def read_bytes(self, attachment_id: str) -> bytes | None:
        return self.providers.current().read_bytes(attachment_id)

    def exists(self, attachment_id: str) -> bool:
        return self.providers.current().exists(attachment_id)
