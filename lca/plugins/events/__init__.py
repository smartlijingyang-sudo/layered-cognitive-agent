"""事件 v2 插件族（ADR-0179 P2 试点）。

模块：
- sender.py：EventSenderImpl（唯一发送者，provider 插件）
- router.py：EventRouterImpl（按 category fanout）
- consumer_registry.py：ConsumerRegistry（订阅索引）
- consumers/console_projector.py：ConsoleProjectorConsumer（试点消费者）

不在本包：
- 事件契约（Event / EventCategory / EventSender Protocol）—— 在
  ``lca/contracts/event_v2.py``，保持 ``contracts/ → plugins/`` 单向依赖。
"""
