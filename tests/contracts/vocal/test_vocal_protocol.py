from lca.contracts.protocols.vocal.protocol import VocalGateProtocol, VocalStrategy


def test_protocols_runtime_checkable():
    assert hasattr(VocalGateProtocol, "deliver")
    assert hasattr(VocalGateProtocol, "handle_text_chunk")
    assert hasattr(VocalGateProtocol, "is_awaiting_widget")
    assert hasattr(VocalStrategy, "mode")
    assert hasattr(VocalStrategy, "create_gate")
