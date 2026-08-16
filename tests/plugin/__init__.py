"""Plugin 系统全景测试 —— 用「共享美食广场」的故事讲透整个架构。

.. contents:: 测试分层地图
   :depth: 2

═══════════════════════════════════════════════════════════
整体隐喻：一家共享美食广场
═══════════════════════════════════════════════════════════

想象你在管理一家**共享美食广场**（类似美食城）。

- 美食广场的公共区域和基础设施 = **PluginHost（宿主）**
- 每个档口（炸鸡店、奶茶店、麻辣烫）= **一个 Plugin（插件）**
- 每个档口的营业状态（筹备中 / 装修中 / 营业中 / 停业 / 已关门）= **PluginState 状态机**
- 档口的运营日志和清理清单 = **PluginHandle（运行时句柄）**
- 公共设备和服务（点餐系统、油炸设备、收银系统、冰箱）= **Service（服务）**
- 广场广播系统（消防演习通知、促销广播）= **EventBus（事件总线）**
- 档口与广场的交互界面（开店申请、设备使用）= **PluginContext（插件上下文）**
- 美食广场的招商手册（哪些档口入驻、什么顺序开业）= **Loader（拓扑加载器）**
- 美食广场的楼层规划图（YAML 配置 → 档口列表）= **Profile（组合配置）**
- 每个档口的「能力三角」（菜单定义 / 厨师实现 / 食客消费）= **Seam 三角色**

═══════════════════════════════════════════════════════════
测试文件索引 —— 从底层到顶层，逐步拼出完整故事
═══════════════════════════════════════════════════════════

**第一层：契约（Contracts）—— 美食广场的规章制度**

``test_contracts.py``
    PluginConfig / Plugin Protocol / SeamRole / SeamRegistry / consume 门。
    相当于美食广场的「入驻规范」：档口必须叫什么名字、声明什么依赖、
    提供什么服务。Seam 三角色就像「菜单 / 厨师 / 食客」缺一不可。

**第二层：内核（Kernel）—— 美食广场的基础设施**

``test_event_bus.py``
    广场广播系统的 5 种分发模式（emit / parallel / serial / bail / waterfall）。
    就像广场广播可以是「通知一下就行」(emit)，也可以是「所有档口同时响应」(parallel)，
    也可以是「依次确认直到有人拦截」(serial/bail)，也可以是「层层审批链」(waterfall)。

``test_host.py``
    美食广场管理处的核心职责：维护服务台账（谁提供了什么设备）、
    档口登记簿（谁入驻了）、事件广播（广场通知）。
    管理处**不做**经营决策——那是生命周期层的事。

``test_context.py``
    档口与广场的交互界面。档口通过 ctx 来：
    - mount（在广场登记一台设备）
    - require（领取自己声明需要的设备）
    - effect（「我走的时候记得帮我关灯」）
    - on（「有消防广播时通知我」）
    - child（给今天的营业开一个子上下文）

``test_lifecycle.py``
    **最关键的状态机**。美食广场的运营逻辑全在这里：
    - reconcile：检查所有等待中的档口，依赖满足了就让他们开业
    - activate：PENDING → LOADING → ACTIVE（筹备 → 装修 → 开业）
    - deactivate：ACTIVE → UNLOADING → PENDING（停业 → 清理 → 等待）
    - cascade：油炸机坏了 → 炸鸡档口和薯条档口自动停业
    - shutdown：美食广场打烊，所有档口逆序关门

``test_handle_and_spec.py``
    档口的「运营日志」和「入驻申请表」。
    PluginHandle 记录每个档口的状态、效果清单、提供的服务。
    DisposableList 是「关灯清单」——走的时候逆序执行。

**第三层：加载（Loader / Profile）—— 招商入驻流程**

``test_loader.py``
    招商办的工作：审核档口资质（name/inject/apply/provides 齐全吗？）、
    检测冲突（两个档口抢同一台设备？）、拓扑排序（先开没有依赖的）、
    驱动 reconcile 直到所有能开业的都开业。

``test_profile.py``
    美食广场的「楼层规划图」：
    YAML bundle = 一批档口的招商方案，
    profile = 多个 bundle 的组合 + patch（临时调整），
    ProfileLoader = 从 YAML 到实际 Python 模块的完整解析。

**第四层：集成测试 —— 完整故事线**

``test_integration_lifecycle.py``
    从 PENDING 到 DISPOSED 的完整生命周期，包含 FAILED 恢复。
    就像跟踪一个档口从「申请入驻」到「关门走人」的全过程。

``test_integration_dependencies.py``
    档口之间的依赖链：钻石依赖、级联停业、自动恢复。
    就像美食广场里油炸设备坏了，所有用到它的档口会怎样。

``test_integration_e2e.py``
    从 YAML 配置文件到活跃档口的完整流程。
    就像从「美食广场招商手册」到「所有档口正常营业」。

``test_integration_capability.py``
    CapabilityHub + Seam 三角色 + Plugin 系统的协同。
    就像美食广场的「公共服务台」+「能力三角验证」+「档口运营」三位一体。

**第五层：边界测试 —— 异常天气演练**

``test_edge_cases.py``
    各种极端情况：空美食广场、重复入驻、设备抢占、
    配置校验失败、级联雪崩、清理异常……
    就像消防演习——测试系统在异常情况下是否依然健壮。

═══════════════════════════════════════════════════════════
架构一览：依赖方向（单向，从下到上）
═══════════════════════════════════════════════════════════

::

    contracts/          ← 规章制度（纯 Protocol + dataclass，零行为）
        ↑
    kernel/             ← 基础设施（EventBus + Host + Context + Lifecycle）
        ↑
    loader/             ← 招商流程（拓扑排序 + 校验）
        ↑
    include/ (profile)  ← 楼层规划（YAML → entries → modules）
        ↑
    capability/         ← 公共服务台（CapabilityHub + 各 Service）
        ↑
    layer4_app/         ← 组合根（boot_capabilities + register_seam_catalog）
"""
