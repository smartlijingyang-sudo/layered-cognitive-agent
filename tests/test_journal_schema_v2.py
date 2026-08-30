import pytest
from pydantic import ValidationError

from lca.contracts.observability.schemas.v2 import EnvelopeV2


def test_envelope_schema_version_required():
    data = {
        "schema_version": "v2.0.0",
        "event_id": "abc",
        "trace_id": "t",
        "run_id": "r",
        "run_seq": 1,
        "plan_ref": "",
        "occurred_at": 0.0,
        "descriptor": {"type": "TestEvent", "domain": "event", "audience": "domain"},
        "payload": {},
        "scope": {},
        "causation": {},
    }
    env = EnvelopeV2.model_validate(data)
    assert env.schema_version == "v2.0.0"


def test_envelope_missing_schema_version_rejected():
    data = {"event_id": "abc", "trace_id": "t", "run_id": "r", "run_seq": 1}
    with pytest.raises(ValidationError):
        EnvelopeV2.model_validate(data)
