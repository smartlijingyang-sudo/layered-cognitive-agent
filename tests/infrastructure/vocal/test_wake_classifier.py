from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.wake import WakeClassifier


def test_classify_user_input():
    classifier = WakeClassifier()
    ctx = classifier.classify("user_input")
    assert ctx.source == WakeSource.USER_INPUT
    assert ctx.is_silence_allowed is False
    assert ctx.requires_reply_first is True


def test_classify_routine():
    classifier = WakeClassifier()
    ctx = classifier.classify("routine")
    assert ctx.source == WakeSource.ROUTINE
    assert ctx.is_silence_allowed is True
    assert ctx.requires_reply_first is False


def test_classify_inbound_with_channel():
    classifier = WakeClassifier()
    ctx = classifier.classify("inbound", channel_target="wechat:user_123")
    assert ctx.source == WakeSource.INBOUND
    assert ctx.is_silence_allowed is False
    assert ctx.channel_target == "wechat:user_123"


def test_classify_revival():
    classifier = WakeClassifier()
    ctx = classifier.classify("revival", subagent_id="sub_worker_1")
    assert ctx.source == WakeSource.REVIVAL
    assert ctx.is_silence_allowed is True
    assert ctx.subagent_id == "sub_worker_1"
