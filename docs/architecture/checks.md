# LCA 架构检查脚本总览

本文档汇总仓库中所有 `scripts/check_*.py` 与相关检查脚本，描述它们**拦什么、关联哪个 spec/ADR、阻塞状态**。新增检查脚本时同步更新本文档。

## 检查脚本索引

| 脚本 | 拦什么 | 关联 spec / ADR | CI 阻塞 | Phase |
|---|---|---|---|---|
| `check_package_contracts.py` | L1 README / L2 pyproject / L3 import-linter / 实际 import 四向一致性 | [2026-08-30-lca-modularization-design §4.5](../superpowers/specs/2026-08-30-lca-modularization-design.md) | 是（Phase 1 后） | Phase 1 |
| `check_protocol_impl.py` | Protocol 必须有实现 | ADR-0004 Protocol-First | 是 | baseline |
| `check_protocol_schema_version.py` | Envelope schema_version 不漂移 | ADR-0096 Journal Protocol Layer | 是 | baseline |
| `check_plugin_typing.py` | 插件 manifest 类型完整 | ADR-0061 plugin manifest resolve/boot | 是 | baseline |
| `check_plugin_capability.py` | 插件 capability 声明完整 | ADR-0056 plugin group contribution | 是 | baseline |
| `check_no_any.py` | 禁止 `Any` 类型滥用 | C4 Reducer / 类型纪律 | 是 | baseline |
| `check_no_bare_strings.py` | 禁止裸字符串 | 命名规范 | 是 | baseline |
| `check_no_flat_runs.py` | 禁止扁平 run 结构 | C1 闭集 / 阶段图 | 是 | baseline |
| `check_no_double_encoding.py` | 禁止双重编码 | 字符编码纪律 | 是 | baseline |
| `check_no_journal_write_in_coding_agent.py` | 禁止在 coding agent 中写 Journal | C3 Journal 唯一事实源 | 是 | baseline |
| `check_no_preview_fields.py` | 禁止 prompt_preview 等猜测字段 | C3 Journal 重建事实 | 是 | baseline |
| `check_assembly_purity.py` | 装配纯净性（无业务逻辑） | ADR-0005 L4 组合根 | 是 | baseline |
| `check_locked_surface.py` | 锁定面与端口策略 | ADR-0103 Locked Surface | 是 | baseline |
| `check_package_boundary.py` | wheel 内部文件归属 | packaging 纪律 | 是 | baseline |
| `check_doc_layering.py` | 文档分层（specs/adr/design/plans/research/history） | documentation-map.md | 是 | baseline |
| `check_adr_supervision.py` | ADR 监督 | ADR 体系 | 是 | baseline |
| `check_run_naming.py` | 运行命名规范 | naming-conventions.md | 是 | baseline |
| `check_command_envelope_required.py` | 命令必须包在 envelope | ADR-0096 command envelope | 是 | baseline |
| `check_evidence_atomic.py` | 证据原子性 | ADR-0065 recoverable evidence | 是 | baseline |
| `check_patch_integrity.py` | Patch 完整性 | lobehub patches | 是 | baseline |
| `check_gateway_no_direct_journal_new.py` | Gateway 不直接写 Journal | C3/C7 控制观察分离 | 是 | baseline |
| `check_filename_boundaries.py` | filename blacklist（`util`/`helper`/`manager`/`impl`/`common`/`misc`） | [2026-08-30-lca-modularization-design §6](../superpowers/specs/2026-08-30-lca-modularization-design.md) | warning 模式（Phase 3） | Phase 3 |
| `quarterly_legacy_cleanup.py` | legacy_blacklist stable/active 分类 | spec §6.6 | N/A | Phase 3 |
| `migrate_layer_rename.py` (planned) | Phase 2 layer 名迁移辅助 | ADR-0104 语义化 | N/A | Phase 2 |
| `quarterly_legacy_cleanup.py` (planned) | legacy_blacklist 季度清理 | Phase 3 §6.6 | N/A | Phase 3 |
| `lint-imports`（import-linter） | 5 + 10 + 1 contracts: layers + forbidden + independence | ADR-0061 plugin manifest | 是 | baseline + Phase 1 |

## 验证命令

```bash
# Phase 1 完整验证
uv run ruff check --fix . && \
uv run ruff format . && \
uv run lint-imports && \
uv run python scripts/check_package_contracts.py && \
uv run mypy lca && \
uv run pytest -q

# 仅 L4 check
uv run python scripts/check_package_contracts.py

# 仅 import-linter
uv run lint-imports
```

## 新增检查脚本的规则

1. 脚本必须实现为 `scripts/check_*.py`，可独立运行（`python scripts/check_*.py`）
2. 必须有对应单元测试 `tests/scripts/test_check_*.py`
3. 必须更新本文档的"检查脚本索引"表
4. CI 默认阻塞（除非有明确 warning 理由）
5. 不允许"实现细节放在 check 脚本里"——check 只检查，不修复

## 相关文档

- [2026-08-30-lca-modularization-design](../superpowers/specs/2026-08-30-lca-modularization-design.md)：本次重构的 spec
- [AGENTS.md §6](../../AGENTS.md)：改动范围对应的最低验证集
- [docs/specs/naming-conventions.md](../specs/naming-conventions.md)：命名规范
- [docs/specs/documentation-map.md](../specs/documentation-map.md)：文档地图
- [ADR-0004 Protocol-First](../adr/0004-protocol-first-pluggability.md)
- [ADR-0005 Composition Root L4](../adr/0005-composition-root-l4.md)
- [ADR-0037 Journal-as-Truth](../adr/0037-journal-as-truth.md)
- [ADR-0061 plugin manifest resolve/boot](../adr/0061-plugin-manifest-resolve-boot.md)
- [ADR-0072 Null 默认纪律](../adr/0072-null-default-discipline.md)
