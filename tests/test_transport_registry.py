"""TransportRegistry 单元测试 —— 注册/解析/校验/错误路径。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import (
    TransportNotFoundError,
    TransportRegistry,
)
from tests.support.unimplemented_transport import UnimplementedTransport


class TestTransportRegistryRegister(unittest.TestCase):
    """注册与解析。"""

    def test_register_and_resolve(self) -> None:
        registry = TransportRegistry()
        transport = InternalTransport()
        registry.register(transport)
        self.assertIs(registry.resolve("internal"), transport)

    def test_register_as_validates_name_match(self) -> None:
        registry = TransportRegistry()
        transport = InternalTransport()
        with self.assertRaises(ValueError) as ctx:
            registry.register_as("wrong_name", transport)
        self.assertIn("不匹配", str(ctx.exception))

    def test_register_as_with_matching_name(self) -> None:
        registry = TransportRegistry()
        transport = InternalTransport()
        registry.register_as("internal", transport)
        self.assertIs(registry.resolve("internal"), transport)

    def test_list_protocols(self) -> None:
        registry = TransportRegistry()
        registry.register(InternalTransport())
        registry.register(UnimplementedTransport("a2a"))
        self.assertCountEqual(registry.list_protocols(), ["internal", "a2a"])

    def test_contains(self) -> None:
        registry = TransportRegistry()
        registry.register(InternalTransport())
        self.assertIn("internal", registry)
        self.assertNotIn("a2a", registry)


class TestTransportRegistryResolve(unittest.TestCase):
    """解析错误路径。"""

    def test_resolve_unknown_raises_transport_not_found(self) -> None:
        registry = TransportRegistry()
        with self.assertRaises(TransportNotFoundError) as ctx:
            registry.resolve("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))
        self.assertEqual(ctx.exception.protocol, "nonexistent")
        self.assertEqual(ctx.exception.available, [])

    def test_resolve_unknown_lists_available(self) -> None:
        registry = TransportRegistry()
        registry.register(InternalTransport())
        with self.assertRaises(TransportNotFoundError) as ctx:
            registry.resolve("a2a")
        self.assertIn("internal", str(ctx.exception))


class TestUnimplementedTransport(unittest.IsolatedAsyncioTestCase):
    """UnimplementedTransport 所有方法抛 NotImplementedError。"""

    async def test_send_task_raises(self) -> None:
        t = UnimplementedTransport("a2a", tracking_issue="#123")
        with self.assertRaises(NotImplementedError) as ctx:
            await t.send_task("agent", "task", [])
        self.assertIn("a2a", str(ctx.exception))
        self.assertIn("#123", str(ctx.exception))

    async def test_poll_status_raises(self) -> None:
        t = UnimplementedTransport("mcp")
        with self.assertRaises(NotImplementedError):
            await t.poll_status("task_id")

    async def test_receive_result_raises(self) -> None:
        t = UnimplementedTransport("mcp")
        with self.assertRaises(NotImplementedError):
            await t.receive_result("task_id")

    async def test_no_tracking_issue(self) -> None:
        t = UnimplementedTransport("a2a")
        with self.assertRaises(NotImplementedError) as ctx:
            await t.send_task("agent", "task", [])
        self.assertNotIn("tracked in", str(ctx.exception))


class TestRegistryOverwrite(unittest.TestCase):
    """后注册的 transport 覆盖先注册的（同 protocol_name）。"""

    def test_later_register_overwrites(self) -> None:
        registry = TransportRegistry()
        t1 = InternalTransport()
        t2 = InternalTransport()
        registry.register(t1)
        registry.register(t2)
        self.assertIs(registry.resolve("internal"), t2)


if __name__ == "__main__":
    unittest.main()
