# ADR-0018: L4 对象图工厂以 assembly 为准（修订 ADR-0005 措辞）

## 状态
Accepted  
Relates-to: ADR-0005

## 背景
ADR-0005 将组合根描述为 `defaults.py`。落地后发现型注册（`ensure_defaults` / `register_defaults`）与对象图组装（`assemble_base_agent` / `assemble_team`）职责分离。

## 决定
- **`lca/layer4_app/assembly.py`**：唯一对象图工厂（Agent / Team 共享管线）。
- **`lca/layer4_app/defaults.py`**：发现型组件注册与 transport/team 辅助构建；不再作为完整对象图入口。
- **`lca/layer4_app/api.py`**：薄门面，委托 assembly。

## 后果
- 正面：与 registry-catalog 文档一致；新人只找 assembly。
- 负面：旧文档/ADR-0005 标题仍提 defaults，以本 ADR 为准。
