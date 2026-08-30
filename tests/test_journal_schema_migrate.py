from lca.contracts.observability.schemas.migrate import migrate_v1_to_v2


def test_v1_data_field_becomes_payload():
    v1 = {"schema": "lca.journal/1", "event": {"foo": "bar"}, "seq": 1}
    v2 = migrate_v1_to_v2(v1)
    assert v2["schema_version"] == "v2.0.0"
    assert v2["payload"] == {"foo": "bar"}
    assert "event" not in v2


def test_migrate_idempotent():
    v1 = {"schema": "lca.journal/1", "event": {"x": 1}, "seq": 2}
    v2 = migrate_v1_to_v2(v1)
    assert migrate_v1_to_v2(v2) == v2
