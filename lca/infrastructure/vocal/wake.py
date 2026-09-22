from lca.contracts.models.vocal.wake import WakeContext, WakeSource


class WakeClassifier:
    """根据入站线索与触发方式分类生成强类型 WakeContext。"""

    def classify(
        self,
        source: str | WakeSource,
        channel_target: str | None = None,
        subagent_id: str | None = None,
        priority: bool = False,
    ) -> WakeContext:
        src = WakeSource(source) if isinstance(source, str) else source

        if src == WakeSource.ROUTINE:
            return WakeContext(
                source=src,
                is_silence_allowed=True,
                requires_reply_first=False,
                priority=priority,
            )
        elif src == WakeSource.USER_INPUT:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                priority=priority,
            )
        elif src == WakeSource.FIRST_RUN:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                priority=priority,
            )
        elif src == WakeSource.INBOUND:
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=True,
                channel_target=channel_target,
                priority=priority,
            )
        elif src == WakeSource.REVIVAL:
            return WakeContext(
                source=src,
                is_silence_allowed=True,
                requires_reply_first=False,
                subagent_id=subagent_id,
                priority=priority,
            )
        else:  # PEER_AGENT
            return WakeContext(
                source=src,
                is_silence_allowed=False,
                requires_reply_first=False,
                priority=priority,
            )
