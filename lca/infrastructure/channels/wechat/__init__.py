"""WeChat channel package."""

from lca.infrastructure.channels.wechat.client import WechatIlinkClient
from lca.infrastructure.channels.wechat.formatter import WechatMessageFormatter
from lca.infrastructure.channels.wechat.manager import WechatChannelManager
from lca.infrastructure.channels.wechat.worker import WechatChannelWorker, derive_wechat_session_id

__all__ = [
    "WechatChannelManager",
    "WechatChannelWorker",
    "WechatIlinkClient",
    "WechatMessageFormatter",
    "derive_wechat_session_id",
]
