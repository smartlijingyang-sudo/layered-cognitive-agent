"""Public exports for ``default`` (auto-fixed)."""

from lca.infrastructure.attachment.default.provider import (
    DefaultAttachmentPromptRenderer,
    DefaultAttachmentResolver,
    DefaultAttachmentStager,
    install_attachment_default_plugins,
)

__all__ = ['DefaultAttachmentPromptRenderer', 'DefaultAttachmentResolver', 'DefaultAttachmentStager', 'install_attachment_default_plugins']
