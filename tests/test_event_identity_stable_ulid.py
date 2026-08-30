import inspect
import re

from lca.plugins.providers.event_identity.stable_ulid import StableUlidIdentity


def test_derive_returns_ulid_format():
    identity = StableUlidIdentity()
    eid = identity.derive(run_id="r1", seq=1, event_type="StepTextDelta")
    # ULID = 26 chars Crockford Base32 (no I/L/O/U)
    assert re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", eid), f"not ULID: {eid}"


def test_derive_distinct_calls_produce_distinct_ids():
    """ULID 的随机分量保证同 (run_id, seq, event_type) 多次调用产不同 id。"""
    identity = StableUlidIdentity()
    eids = {identity.derive(run_id="r1", seq=1, event_type="A") for _ in range(100)}
    assert len(eids) == 100  # 100 distinct IDs from same args


def test_derive_does_not_accept_ts_parameter():
    """I3: 派生不接 float ts。"""
    identity = StableUlidIdentity()
    sig = inspect.signature(identity.derive)
    assert "ts" not in sig.parameters
    assert "occurred_at" not in sig.parameters
    assert "float_ts" not in sig.parameters


def test_derive_returns_string():
    identity = StableUlidIdentity()
    eid = identity.derive(run_id="r", seq=0, event_type="X")
    assert isinstance(eid, str)
    assert len(eid) == 26
