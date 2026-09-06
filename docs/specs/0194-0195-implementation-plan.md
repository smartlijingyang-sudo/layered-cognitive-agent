# ADR-0194 / ADR-0195 完整 PR 实施计划

> **状态：** Proposed（执行 SSOT）  
> **权威：** [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) · [ADR-0195](../adr/0195-platform-architecture-convergence.md) · [platform-directory-architecture.md](platform-directory-architecture.md)  
> **用法：** 每个 PR 标题格式 `feat(scope): subject` 或 `refactor(scope): subject`；正文必须引用 PR-ID 与 ADR 条目。

---

## 0. 总览

| 阶段 | PR 数 | 周期（估） | 硬依赖 |
|---|---|---|---|
| **P0** 文档与门禁 | 12 | 2 周 | — |
| **P1** 事实单轨 + FactGateway | 18 | 4–6 周 | P0 |
| **P2** 观测收敛 | 22 | 4 周 | P1-01（FactGateway Protocol） |
| **P3** Transport 瘦身 | 14 | 4 周 | P1-03（session re-export） |
| **P4** 目录与插件重组 | 35 | 8 周 | P1 部分；与 P2/P3 并行 |
| **P5** 退役与验收 | 12 | 2 周 | P1–P4 各轨完成 |
| **合计** | **113 PR** | ~20–24 周（多轨并行） | |

### 0.1 并行轨道（Lane）

```text
Lane A  Foundation    P0 → P1 (FactGateway, session, cognition isolation)
Lane B  Observability P1 → P2 (reflector, yaml SSOT, deriver split)
Lane C  Transport     P1 → P3 (carrier/read, resume, terminal)
Lane D  Loop/Graph    P1 → P4-loop (loop package, phase move, harness/graph)
Lane E  Plugins/Org   P0 → P4-plugins (seam tree, package-org, domain move)
Lane F  Kernel        P0 → P4-kernel (boot unify, harness/composition)
Lane G  State/DSH     P1 → P4-dsh (RunCommitter, ModelContext, history)
Lane H  Cleanup       P5 (delete COMPAT, doc, acceptance)

可并行示例（同一 Lane 内串行，跨 Lane 看依赖）:
  Week 1–2:  P0 全轨
  Week 3–6:  Lane A + Lane F + Lane E(文档) 并行
  Week 4–8:  Lane B + Lane C + Lane D 并行（等 P1-01 合并）
  Week 8–16: Lane D + Lane E + Lane G 并行
  Week 16–20: Lane H
```

### 0.2 PR 命名约定

```text
PR-{phase}-{seq}  例: PR-P1-03
branch: adr0194/p1-03-session-append-reexport
```

---

## 1. P0 — 文档、门禁、ADR Accepted（12 PR）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 并行 |
|---|---|---|---|---|---|
| **P0-01** | docs(adr): Accept ADR-0194 Proposed→Accepted | 0194 全文 | ADR 状态 + 索引 | notes-check | 与 P0-02 并行 |
| **P0-02** | docs(adr): Accept ADR-0195 Proposed→Accepted | 0195 全文 | 同上 | 同上 | 与 P0-01 并行 |
| **P0-03** | docs(specs): platform-directory-architecture + 实施计划 | 0195 §2, 0194 §2 | 本文 + directory spec | verify_md_links | P0-01 后 |
| **P0-04** | docs: 全栈 README 网络（kernel/loop/transport/session/plugins） | 0194 §0.5, 0195 §2.2–2.4 | 各 README | 人工 45min 读通 | 与 P0-03 并行 |
| **P0-05** | docs(agents): 六 phase 闭集；Gate⊂Think 正名 | 0194 §1.3, §4 G2 文档面 | AGENTS.md, ADR-0002 引用 | verify_doc_slop | P0-01 后 |
| **P0-06** | test(arch): platform directory 门禁 | 0195 §7 P-L5 部分 | test_platform_directory + check script | pytest + script | 已完成可标记 done |
| **P0-07** | test(arch): cognition fact isolation 骨架（xfail→strict 路线图） | 0194 §7 L1, 0195 §5 cognition | test_cognition_no_emit_imports 占位 | xfail 清单 | 与 P0-06 并行 |
| **P0-08** | test(arch): transport isolation 骨架 | 0195 §7 P-L2,P-L3 | transport 无 append/reducer | xfail 清单 | 与 P0-06 并行 |
| **P0-09** | test(arch): obs journal hotpath 禁止清单 | 0195 O6, 0194 G1 | rg 基线测试 | 记录 baseline | 与 P0-06 并行 |
| **P0-10** | docs(observability): platform-readme 四段链 | 0195 §2.3 | platform-readme.md | doc test P-L8 骨架 | P0-04 后 |
| **P0-11** | chore(plugins): seam 树锚点 README + ARCHITECTURE | 0195 §2.5, 0190 | cognitive/loop/…/meta README | P0-06 | 已完成可标记 done |
| **P0-12** | docs: SSOT 矩阵链入 documentation-map + AGENTS 入口 | 0195 §4 | 导航链接 | verify_md_links | P0-03 后 |

**P0 出口：** ADR Accepted；门禁骨架存在；新人可读 README 网络。

---

## 2. P1 — 事实单轨 + FactGateway（18 PR）

> **0194 Wave A + 0195 P1 + 0191/0192 加速**

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P1-01** | feat(contracts): FactGateway + AppendReceipt Protocol | 0194 §3.1, 0195 G0 Fact append | `contracts/protocols/loop/fact_gateway.py` | mypy + 契约测试 | P0-01 | — |
| **P1-02** | feat(loop): DefaultFactGateway 实现 | 0194 §3.1 | `lca/loop/fact_gateway.py` | test_fact_gateway_single_entry | P1-01 | — |
| **P1-03** | feat(session): append.py 公共 API + plugins shim | 0194 §2.1 session, 0195 §2.1 | `lca/session/append.py` re-export | session 单元测试 | P1-02 | 与 P1-04 并行 |
| **P1-04** | feat(session): catalog.py 词表 re-export | 0195 Fact plane | `lca/session/catalog.py` | catalog 测试 | P1-03 | 与 P1-03 并行 |
| **P1-05** | feat(session): bind.py 从 plugins 提升 | 0195 §2.1, O8 前置 | `lca/session/bind.py` + COMPAT import | bind 集成测试 | P1-03 | P1-04 后 |
| **P1-06** | refactor(loop): cognitive_emit 经 FactGateway | 0194 §3.1, G12 | `cognitive_emit` → gateway | test_cognitive_emit | P1-02 | 与 P1-07 并行 |
| **P1-07** | refactor(loop): lifecycle_emit 经 FactGateway | 0195 四段链 | lifecycle_emit 委托 gateway | lifecycle 测试 | P1-02 | 与 P1-06 并行 |
| **P1-08** | refactor(loop): fact_committer 经 FactGateway | 0192, 0194 Observer | fact_committer 委托 | fact_plane 测试 | P1-02 | 与 P1-06 并行 |
| **P1-09** | feat(flags): LCA_FACT_GATEWAY 回退开关 | 0194 §8 风险 | env 开关 + 文档 | 双路径 smoke | P1-02 | P1-06 后 |
| **P1-10** | refactor(cognition): tool_journal_emit → DTO + 上层 emit | 0194 G1,G12, L1 | body 返回 receipt DTO；act 路径 gateway | test_tool_journal | P1-02 | Lane A |
| **P1-11** | refactor(cognition): safe_executor 去 journal | 0194 G1 | 同上模式 | body 测试 | P1-10 | 串行 |
| **P1-12** | refactor(cognition): llm_turn/executor 去 journal | 0194 G1, O6 | telemetry 经 gateway | llm 测试 | P1-02 | 与 P1-10 并行 |
| **P1-13** | refactor(cognition): memory/simple_memory 去 spine import | 0194 G12, L1 | 去 reflector import | memory 测试 | P1-02 | 与 P1-10 并行 |
| **P1-14** | refactor(cognition): modular_brain 去 spine_reflector | 0194 G12 | brain.think EP 经 gateway | brain 测试 | P1-02 | 与 P1-10 并行 |
| **P1-15** | refactor(cognition): reasoner 去 spine/hook 直 emit | 0194 G12, 0191 model | ModelVisible 边界保留 adapter | reasoner 测试 | P1-02 | 与 P1-14 并行 |
| **P1-16** | test(arch): cognition fact isolation strict | 0194 §7 L1, §9.2 | P0-07 xfail→pass | pytest | P1-10–15 | — |
| **P1-17** | refactor(infra): meta_event_emit 经 FactGateway | 0195 §2.3 Gateway | meta_event_emit 委托 | meta taxonomy 测试 | P1-02 | 与 P1-10 并行 |
| **P1-18** | chore: manifest.py EXECUTION_POINTS 冻结 COMPAT | 0194 B3, 0195 O1 | 注释 + 禁止新增 EP | rg + test | P0-09 | Lane B 前置 |

**P1 出口：** FactGateway 生产；cognition 零 journal/spine import；Session 公共 API 存在。

---

## 3. P2 — 观测收敛（22 PR）

> **0194 Wave B + 0195 §2.3 O1–O8 + §7 P-L4,P-L6,P-L7**

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P2-01** | refactor(contracts): PhaseName 移除 gate | 0194 §1.3, G2, L3,L5 | loop_cursor.py, taxonomy | test_meta_event_taxonomy | P1-01 | Lane B |
| **P2-02** | refactor(obs): meta_event_taxonomy 6 phase | 0194 G2, 0195 §5 | taxonomy 三平面 | taxonomy 测试 | P2-01 | 串行 |
| **P2-03** | refactor(cursor): advance 仅 6 phase | 0194 B4, L3 | std.py, coordinator | loop_cursor 测试 | P2-01 | 与 P2-02 并行 |
| **P2-04** | refactor(cursor): 删除 phase.gate.fold 生产路径 | 0194 G2, L5 | rg 0 | execution_point 测试 | P2-03 | 串行 |
| **P2-05** | refactor(spine.yaml): 退役 brain.gate.* 或 wire think 子 span | 0194 G3 | yaml 变更 | coverage 测试 | P2-01 | 与 P2-03 并行 |
| **P2-06** | refactor(gateway): publish_ep 内聚 spine_enrich | 0194 §3.1, 0195 Observer | enrich 移入 gateway | spine_enrich 测试 | P1-02 | Lane B |
| **P2-07** | refactor(obs): EmitPipeline 仅 hook-less 测试 | 0194 G5, O3 | 生产路径删除 | test_session_ssot | P2-06 | 串行 |
| **P2-08** | refactor(kernel): EventBus → EnvelopeBus 别名收敛 | 0194 G6, O4 | bus.py COMPAT 删除计划 | test_event_bus | P2-06 | 与 P2-07 并行 |
| **P2-09** | refactor(obs): WritableMatrix coordinator 删 stub | 0194 G7, O5 | coordinator 清理 | writable 测试 | P2-03 | 与 P2-07 并行 |
| **P2-10** | refactor(reflector): spine_reflector_runtime → gateway | 0194 G4, O2 | runtime EP 迁移 | runtime envelope 测试 | P1-02 | **可 10–16 并行** |
| **P2-11** | refactor(reflector): spine_reflector_cognition → gateway | G4 | cognition EP | cognition spine 测试 | P1-02 | 并行 |
| **P2-12** | refactor(reflector): spine_reflector_phase → gateway | G4 | phase EP | phase 测试 | P1-02 | 并行 |
| **P2-13** | refactor(reflector): spine_reflector_body_llm → gateway | G4 | body/llm EP | body 测试 | P1-02 | 并行 |
| **P2-14** | refactor(reflector): spine_reflector_kernel_loop → gateway | G4 | loop EP | kernel loop 测试 | P1-02 | 并行 |
| **P2-15** | refactor(reflector): 其余 reflector 批量（batch 2） | G4, O2 | assistant/team/transport/… | EP coverage | P2-10–14 | 串行 |
| **P2-16** | chore(plugins): 删除 spine_reflector_* 目录 | G4, §9.5 | 删目录 + bundle | audit-plugin | P2-10–15 | — |
| **P2-17** | refactor(manifest): 删除 EXECUTION_POINTS 副本 | B3, O1 | manifest.py 删 tuple | test_execution_point_coverage | P2-15 | — |
| **P2-18** | feat(plugins/obs): deriver/step_tree 首包试点 | 0195 §2.3, O7 | observability/deriver/step_tree/ | deriver 测试 | P2-16 | Lane E 交叉 |
| **P2-19** | feat(plugins/obs): exporter/otel 首包试点 | 0195 §2.3 | observability/exporter/otel/ | otel 测试 | P2-18 | 串行 |
| **P2-20** | refactor(infra): 双份 deriver 合并到 plugins | O7 | step_tree_accumulator 迁或薄化 | fold 测试 | P2-18 | — |
| **P2-21** | test(arch): emit single entry strict (L2,P-L7) | 0194 §7 L2 | test_emit_single_entry 扩展 | pytest | P2-16 | — |
| **P2-22** | test(arch): yaml-only EP registry (P-L4) | 0195 §7 | registry drift | test_registry | P2-17 | — |

**P2 出口：** 6 phase 观测；reflector 删除；yaml 唯一 EP；四段链首包 deriver/exporter。

---

## 4. P3 — Transport 瘦身（14 PR）

> **0194 G9 + 0195 §2.4 + §7 P-L2,P-L3 + O8**

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P3-01** | refactor(transport): 建立 carrier/read/wire 目录骨架 | 0195 §2.4 | 空壳 + README | P0-08 更新 | P0-08 | Lane C |
| **P3-02** | refactor(transport): execute → carrier/runs/execute | 0195 carrier | 文件迁移 + shim | e2e runs | P3-01 | 串行 |
| **P3-03** | refactor(transport): loop_drivers 瘦身 | 0195 Loop driver | driver 仅 Agent.run | loop_drivers 测试 | P3-02 | 串行 |
| **P3-04** | refactor(transport): lifecycle → carrier 合流 | 0195 禁止 duplicate 装配 | 调 application 单入口 | lifecycle 测试 | P3-02 | 与 P3-03 并行 |
| **P3-05** | feat(transport): resume → carrier/runs/resume durable | 0194 G9, 0195 §5 | recover_live_agent 唯一 | transport resume 测试 | P1-05 | 与 P3-02 并行 |
| **P3-06** | refactor(transport): 删 RunSession 内存 resume SSOT | G9, 0073 | COMPAT + 迁移 | resume 测试 | P3-05 | 串行 |
| **P3-07** | refactor(transport): observability handlers → read/runs | O8, P-L3 | 只读 fold | read API 测试 | P2-18 | 与 P3-05 并行 |
| **P3-08** | refactor(transport): terminal → read/runs/terminal | 0195 禁止写 state | materialization 只读 | terminal 测试 | P3-07 | 串行 |
| **P3-09** | refactor(transport): live/SSE → read/runs/live | 0195 read | SSE fold only | live 测试 | P3-07 | 与 P3-08 并行 |
| **P3-10** | refactor(transport): doctor 只读化 | 0195 doctor | 无修复副作用 | doctor 测试 | P3-01 | 与 P3-07 并行 |
| **P3-11** | refactor(transport): wire 层集中 DTO | 0195 Adapter 模式 | handlers/runs/wire 迁 | wire 测试 | P3-02 | 并行 |
| **P3-12** | refactor(transport): inbox 双写退役 | 0195 §5 inbox | 单 session emit | inbox 测试 | P1-07 | 与 P3-05 并行 |
| **P3-13** | test(arch): transport isolation strict | P-L2,P-L3 | P0-08 xfail→pass | pytest | P3-02–12 | — |
| **P3-14** | refactor(transport): RunStatus/JournalRunStatus COMPAT 清 | transport COMPAT | status 枚举 SSOT | terminal 测试 | P3-08 | Lane C 末 |

**P3 出口：** carrier/read 分离；durable resume；transport 零 append/fold 混写。

---

## 5. P4 — 目录、Loop、Graph、插件重组（35 PR）

> **0194 Wave C/D + 0195 §2 + §2.5 + package-org**

### 5.1 Loop 机制（Lane D）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-L01** | refactor(loop): driver.py ← declarative_runtime | 0194 §2.1, C1 | 迁移 + runtime shim | declarative 测试 | P1-02 | Lane D |
| **P4-L02** | refactor(loop): transaction.py ← phase_transaction | 0194 C1, §3.2 Template | 迁移 + harness shim | phase_transaction 测试 | P4-L01 | 串行 |
| **P4-L03** | feat(loop): phases/ 注册表读模型 | 0194 §2.1 phases | phase registry | 单元测试 | P4-L02 | 串行 |
| **P4-L04** | feat(loop): control/ 契约 | 0194 §2.1 control | control 协议文档化 | — | P4-L02 | 并行 |
| **P4-L05** | refactor(loop): phase_fact_emitter 迁入 loop | 0194 emit | loop/phase_fact_emitter | perceive 测试 | P4-L02 | 并行 |

### 5.2 Harness Graph MTK（Lane D）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-G01** | refactor(harness): graph/ ← declarative/graph | 0194 C5, 0195 G0 MTK | 迁移 + shim | graph 测试 | P0-06 | 与 P4-L01 并行 |
| **P4-G02** | refactor(harness): interpreter 边界收拢 | 0194 §3.2 Graph SSOT | harness/graph/execute | interpreter 测试 | P4-G01 | 串行 |
| **P4-G03** | refactor(harness): phase_governance 迁入 graph | 0194 §2.3 controls | graph/governance | governance 测试 | P4-G01 | 并行 |
| **P4-G04** | test(arch): MTK 无 business plugin id (L6) | 0194 §7 L6 | test_mtk_no_business_ids | pytest | P4-G01 | — |

### 5.3 Harness Composition + Kernel（Lane F）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-K01** | refactor(harness): composition/ ← profile compile | 0195 §2.2 | 迁移 plan_compiler 等 | resolve 测试 | P0-04 | Lane F |
| **P4-K02** | refactor(kernel): boot 单入口收拢 harness boot | 0195 §2.2, §5 kernel | 删双 boot 链 | test_boot | P4-K01 | 串行 |
| **P4-K03** | refactor(harness): boot_products 纯数据类 | 0195 G0 K3 | harness 薄化 | boot 测试 | P4-K02 | 串行 |

### 5.4 Session 提升（Lane A）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-S01** | refactor(session): repair.py 提升 | 0194 C3, 0191 | lca/session/repair.py | repair 测试 | P1-05 | 与 P4-L01 并行 |
| **P4-S02** | refactor(session): checkpoint.py 提升 | 0191 三边界 | checkpoint policy | checkpoint 测试 | P4-S01 | 串行 |
| **P4-S03** | refactor(session): fold.py 公共 fold 入口 | 0195 §2.1 | re-export kernel fold | fold 测试 | P1-04 | 并行 |
| **P4-S04** | refactor(session): transport_recovery 单路径 | C3, 0191 B3 | recovery 整合 | recovery 测试 | P3-05, P4-S01 | — |

### 5.5 Phase 插件竖切（Lane E）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-P01** | refactor(plugins): loop/phase/perceive/standard | 0194 G11, §2.2 | 从 phase_graph 迁 | plugin shape | P4-L03 | Lane E |
| **P4-P02** | refactor(plugins): loop/phase/think/standard | G11 | 同上 | 同上 | P4-P01 | 可 P02–P06 并行 |
| **P4-P03** | refactor(plugins): loop/phase/act/standard | G11 | 同上 | 同上 | P4-P01 | 并行 |
| **P4-P04** | refactor(plugins): loop/phase/reflect/standard | G11 | 同上 | 同上 | P4-P01 | 并行 |
| **P4-P05** | refactor(plugins): loop/phase/remember/standard | G11 | 同上 | 同上 | P4-P01 | 并行 |
| **P4-P06** | refactor(plugins): loop/phase/stop/standard | G11 | 同上 | 同上 | P4-P01 | 并行 |
| **P4-P07** | chore(plugins): 删除 phase_graph/ 空壳 | §9.5 | delete_when bundles 0 | grep | P4-P01–06 | — |
| **P4-P08** | refactor(plugins): loop/control 竖切 control_contributions | 0194 §2.1 act-chain | 12→loop/control/* | 替换测试 | P4-P01 | 与 P4-P02 并行 |
| **P4-P09** | refactor(plugins): loop/control/act-chain 五合一 | 0194 C4 | 单包多 slot | act 测试 | P4-P08 | 串行 |
| **P4-P10** | refactor(plugins): loop/driver ← loop_drivers | 0195 §2.5 | driver registry | driver 测试 | P3-03 | 并行 |
| **P4-P11** | refactor(plugins): loop/reducer ← plugins/runtime | 0194 §3.3 | reducer plugin 迁 | reducer 测试 | P4-G02 | 并行 |

### 5.6 Cognitive 插件竖切（Lane E）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-C01** | refactor(plugins): cognitive/gate/* ← gates/ | 0195 §2.5 | 薄注册包 | gate 测试 | P1-16 | 并行 |
| **P4-C02** | refactor(plugins): cognitive/brain ← plugins/brain | 0195 cognitive | 迁包 | brain 测试 | P4-C01 | 并行 |
| **P4-C03** | refactor(plugins): cognitive/body ← plugins/body | 同上 | 迁包 | body 测试 | P4-C01 | 并行 |
| **P4-C04** | refactor(plugins): cognitive 其余批量（think/reasoner/memory/sensors/perceive） | 0195 §2.5 | batch 迁 | e2e | P4-C02 | — |

### 5.7 Domain / Composition / Meta（Lane E）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-D01** | refactor(plugins): domain/assistant 试点 | 0195 §2.5 | 首域迁移 | assistant 测试 | P0-11 | 并行 |
| **P4-D02** | refactor(plugins): domain/tools + integrations | 同上 | batch | tools 测试 | P4-D01 | — |
| **P4-M01** | refactor(plugins): composition/composer 等 | 0195 composition | 迁包 | compose 测试 | P4-K01 | 并行 |
| **P4-O01** | chore(plugins): package-org 超标目录拆分计划 | 0194 L4, 0195 P-L5 | ADR 豁免或拆 PR 列表 | check script | P4-P07 | Lane H 输入 |

### 5.8 DSH / RunCommitter（Lane G）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P4-R01** | refactor(contracts): RunCommitter Protocol 别名 | 0194 §3.3, 0191 | run_committer.py | mypy | P1-01 | Lane G |
| **P4-R02** | refactor(reducer): history → control_turns 命名 | 0194 §3.3, G10 | state 字段 + COMPAT | reducer 测试 | P4-R01 | 串行 |
| **P4-R03** | refactor(runtime): 删 build_tool_history 调用 | G10, 0191 | 仅 ModelContextAssembler | model_context_parity | P4-R02, P4-S03 | — |
| **P4-R04** | refactor(reducer): 删 manifest_digest extra COMPAT | 0194 G8 | apply_perception | perceive fold 测试 | P4-R02 | 并行 |
| **P4-R05** | refactor(control): ThinkGuard 读 Decision artifact | 0194 §3.4, D3 | think_guard 简化 | gate 测试 | P1-06, P4-P02 | — |
| **P4-R06** | test(arch): SemanticPhase == cursor fold set (L3) | 0194 §7 L3 | strict | pytest | P2-03 | — |

**P4 出口：** loop/session/harness/graph 目标树；phase 竖切；RunCommitter/ModelContext 单轨。

---

## 6. P5 — 退役、文档、总验收（12 PR）

| PR-ID | 标题 | ADR 覆盖 | 交付 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|
| **P5-01** | chore: 删除 LCA_FACT_GATEWAY 回退开关 | 0194 §8 delete-when | 删 flag | grep 0 | P2-16 | Lane H |
| **P5-02** | chore: 删 plugins/session/runtime 空壳 | 0195 §2.5 | delete_when | grep | P4-S04 | 串行 |
| **P5-03** | chore: 删 harness/declarative 已迁 shim | 0194 C5 | COMPAT 清 | import 测试 | P4-G02,P4-L02 | 并行 |
| **P5-04** | docs(obs): 更新 architecture-overview 四段链 | 0195 §5, §9.6 | 退役 journal 写入叙述 | P-L8 doc test | P2-22 | 并行 |
| **P5-05** | docs: ADR-0169/0168 gate phase Superseded 修订 | 0194 §6 0169 | ADR 修订 | notes-check | P2-04 | 并行 |
| **P5-06** | chore: COMPAT grep CI 全库 | 0194/0195 delete-when | scripts + CI | CI green | P5-01–03 | — |
| **P5-07** | test: 0194 §9 验收 1–6 自动化 | 0194 §9 | acceptance 测试套件 | pytest | P4,P3,P2 | — |
| **P5-08** | test: 0195 §9 验收 1–7 自动化 | 0195 §9 | platform acceptance | pytest | P5-07 | 串行 |
| **P5-09** | docs: 0194/0195 标记 Implemented + Note | 流程 | implemented note | notes-check | P5-08 | — |
| **P5-10** | chore(plugins): legacy 顶层目录删除（batch） | 0195 §2.5 | 43→seam 完成 | audit-plugin | P4 全系 | — |
| **P5-11** | ci: package-org 全绿或 ADR 豁免登记 | L4, P-L5 | pyproject/脚本 | CI | P4-O01 | — |
| **P5-12** | docs: AGENTS.md 链入 SSOT + 删除迁移态 disclaimer 更新 | 0191 迁移态 | AGENTS 更新 | wc -l AGENTS | P5-09 | — |

---

## 7. ADR 条目 → PR 全覆盖追溯矩阵

### 7.1 ADR-0194 决策摘要（§0 五条）

| 条目 | PR-ID |
|---|---|
| 图是执行 SSOT | P4-G01–G04, P4-L01–L05, P4-P01–P07 |
| 事实是 Session SSOT | P1-01–P5, P2-06–P2-21, P4-S01–S04 |
| 认知原语零 emit | P1-10–P1-16, P1-14–P1-15 |
| 可替换皆插件 / 机制 G0 | P4-P*, P4-C*, P4-O01, P0-11 |
| 人读入口 loop README | P0-04, P4-L01（完善链接） |

### 7.2 ADR-0194 §1 第一性原理

| 条目 | PR-ID |
|---|---|
| §1.1 四类状态 | P4-R01–R04, P4-R03 (ModelContext), P1-02 (Fact) |
| §1.2 三层环 R0–R4 | P4-G*, P4-L*, P1-10 (R2), P3-* (R4) |
| §1.3 六步 + Gate 正名 | P0-05, P2-01–P2-05, P4-R05 |
| AGENTS 七步修正 | P0-05, P5-12 |

### 7.3 ADR-0194 §2 目录结构

| 条目 | PR-ID |
|---|---|
| §2.1 顶层 9 包 + loop/session | P0-04, P0-06, P1-03, P4-S*, P4-L* |
| §2.2 插件一包一 manifest | P4-P*, P4-C*, P4-D*, P4-O01 |
| §2.3 harness/declarative 处置 | P4-G*, P4-K*, P5-03 |
| cognition 子包 perceive/think/gate | P4-C*, P1-10（gate 在 brain 内文档） |

### 7.4 ADR-0194 §3 设计模式

| 条目 | PR-ID |
|---|---|
| §3.1 FactGateway | P1-01, P1-02, P2-06, P2-10–P2-16 |
| §3.2 Graph-as-SSOT | P4-G01–G04, P4-L02 |
| §3.3 RunCommitter | P4-R01–R04 |
| §3.4 ThinkGuard 收敛 | P4-R05 |

### 7.5 ADR-0194 §4 退役 G1–G12

| ID | PR-ID |
|---|---|
| G1 journal 热路径 | P1-10–P1-12, P1-16, P5-07 |
| G2 PhaseName.gate | P2-01–P2-04, P5-05 |
| G3 brain.gate.* | P2-05 |
| G4 spine_reflector | P2-10–P2-16, P5-01 |
| G5 EmitPipeline 生产 | P2-07 |
| G6 EventBus | P2-08 |
| G7 WritableMatrix stub | P2-09 |
| G8 manifest_digest | P4-R04 |
| G9 RunSession resume | P3-05–P3-06, P4-S04 |
| G10 build_tool_history | P4-R03 |
| G11 phase_graph 平铺 | P4-P01–P4-P07 |
| G12 cognition spine import | P1-13–P1-16 |

### 7.6 ADR-0194 §5–§9 Waves / CI / 验收

| 条目 | PR-ID |
|---|---|
| Wave A | P1-01–P1-09, P0-05, P0-04 |
| Wave B | P2-* |
| Wave C | P4-L*, P4-G*, P4-P*, P4-S* |
| Wave D | P4-R*, P3-05–P3-06, P4-R05 |
| L1–L6 | P1-16, P2-21, P2-04, P4-O01, P2-04, P4-G04 |
| §8 风险 flag | P1-09, P5-01 |
| §9 验收 1–6 | P5-07 |

### 7.7 ADR-0195 独有条目

| 条目 | PR-ID |
|---|---|
| §1.1 三时态 | P4-K*, P4-L*, P2-18–P2-20, P3-* |
| §1.2 五平面 | P1-03 (Fact), P4-R* (Control/Model), P3 (Carrier) |
| §1.3 G0 内核闭集 | P4-K02–K03, P4-G*, P2-22, P0-06 |
| §2.2 Kernel 迁移 | P4-K01–K03 |
| §2.3 Observability O1–O8 | P2-* , P3-07, P1-18 |
| §2.4 Transport 终态 | P3-* |
| §2.5 Plugins seam 树 | P4-P*, P4-C*, P4-D*, P4-M01, P5-10 |
| §3 设计模式（全栈） | 分布在 P1 Facade, P4 Strategy, P3 Adapter 等 |
| §4 SSOT 矩阵 10 行 | 每行见上表对应 PR |
| §5 全栈退役扩展 | P3-12 inbox, P5-04 doc, P4-K02 boot |
| §7 P-L1–P-L8 | P0-08, P3-13, P2-22, P4-O01, P2-16, P2-21, P5-04 |
| §9 验收 1–7 | P5-08 |

---

## 8. 关键路径（Critical Path）

```text
P0-01/02 → P1-01 → P1-02 → P1-06..15 → P1-16
                ↓
         P2-06 → P2-10..16 → P2-21 → P5-07
                ↓
P1-03 → P1-05 → P3-05 → P3-06 → P4-S04 → P5-08

最长路径（单线程）≈ 16–18 周；8 Lane 并行 ≈ 20–24 周总日历（含 review）。
```

---

## 9. 并行执行日历（建议）

| 周 | Lane A Foundation | Lane B Obs | Lane C Transport | Lane D Loop/Graph | Lane E Plugins | Lane F Kernel | Lane G DSH |
|---|---|---|---|---|---|---|---|
| 1–2 | P0, P1-01–02 | P0, P1-18 | P0, P3-01 | P0 | P0-11 | P0 | — |
| 3–4 | P1-03–09 | P2-01–09 | P3-02–04 | P4-G01 | P4-P01 | P4-K01 | P4-R01 |
| 5–6 | P1-10–16 | P2-10–14 | P3-05–07 | P4-L01–03 | P4-P02–06 | P4-K02 | P4-R02–04 |
| 7–8 | P4-S01–03 | P2-15–18 | P3-08–10 | P4-G02–04 | P4-P08–11 | P4-K03 | P4-R05–06 |
| 9–12 | P4-S04 | P2-19–22 | P3-11–14 | P4-L04–05 | P4-C*, D*, M* | — | — |
| 13–16 | — | — | — | P4-P07 | P4-O01 | — | — |
| 17–20 | P5 全轨 | P5 | P5 | P5 | P5-10 | P5 | P5-07–09 |

---

## 10. 每个 PR 必填 Checklist（模板）

```markdown
## PR-Px-xx

### ADR
- [ ] 0194: §…
- [ ] 0195: §…

### 交付
- …

### delete-when
- rg "…" → 0

### 测试
- [ ] pytest …
- [ ] ruff
- [ ] 区分既有 lint-imports 失败 vs 本次

### 并行
- 可与 PR-Px-yy 并行（无 import 冲突）
```

---

## 11. 风险与 cut-line

| 风险 | 缓解 PR | 可裁剪 |
|---|---|---|
| 113 PR 过多 | 合并 reflector PR P2-10–15 为 2 batch | P4-D02 domain 批量可延后 |
| bundle $module 全改 | 每 PR 保持旧路径 shim 1 release | — |
| 既有 CI 红 | 报告区分 baseline | 不阻塞 P0/P1 |
| 功能回归 | 每 PR 最小 diff + 回归测试 | P4-D* 域迁移可最后 |

**最小可交付（MVP）闭包：** P0 + P1 + P2-01–07,16,21 + P3-01–06,13 + P4-R03 + P5-07 = **约 45 PR**，达成事实单轨 + 6 phase + durable resume + cognition 隔离。

---

## 12. 维护

- 每合并 PR 更新本文 PR-ID 状态列（Done/In Progress）
- 新增 ADR 条目必须先追加 §7 追溯行再编码
- 权威目录：`docs/specs/platform-directory-architecture.md`
