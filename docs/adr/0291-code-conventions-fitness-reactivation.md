# ADR-0291：代码规范健身函数空心化修复与激活策略

> **Status: Accepted**（2026-10-05 iter-arch 10:09 轮起草；2026-10-05 Athena 按李超授权裁决通过）
> 本提案处理 todo-56：`tests/scenario/code/test_code_conventions.py` 四个空心测试的修复与激活策略。
> **未改动任何代码与文档现状**；四测试现状依旧空心，tests lane 在 §5 拍板（已裁决）前不动。

## 1. Context（发现）

2026-10-05 iter-tests 09:09 轮立案 todo-56：`test_code_conventions.py` 四个测试全部空心——
`_PROJECT_ROOT = Path(__file__).resolve().parent.parent` 误指 `tests/scenario/`（应为仓库根），
致 `_LCA_ROOT`（`tests/scenario/lca`，不存在）与 `_GLOSSARY_PATH`
（`tests/scenario/docs/specs/glossary.md`，不存在）全部落空。

四个空心的具体机制（本轮 arch 复核源码确认）：

| # | 测试 | 空心机制 |
|---|---|---|
| ① | `test_file_line_count_limit` | `_LCA_ROOT.rglob("*.py")` 在不存在的目录上返回空迭代器 → 恒绿 |
| ② | `test_layer_init_docstrings_non_empty` | `_LCA_ROOT.glob("layer*/__init__.py")` 恒空（`lca/` 下 14 个子目录 `agent/application/cognition/contracts/domain/framework/harness/infrastructure/loop/migrations/nodes/plugins/runtime/session`，**无 `layer*` 命名**）；`contracts/__init__.py` 的 import 在错误根下抛 `ImportError` 被 `except ImportError: continue` 吞掉 → 空心 |
| ③ | `test_glossary_term_coverage`（forward） | `_read_glossary_terms()` 在错误根下找不到 `docs/specs/glossary.md` → 空集合 → `skipTest` |
| ④ | `test_active_glossary_terms_exist_in_code`（reverse） | 同 ③ `skipTest`；且即使路径修好，`_REVERSE_SCAN_PACKAGES` 含已不存在的 `lca.plugins.loop.phase`（现为 `control/driver/graph/reducer`），`_collect_class_names` 里 `importlib.import_module(pkg_name)` 在循环外、无 `try/except` → `ModuleNotFoundError` 直接炸测试 |

干跑实证（2026-10-05 iter-tests 09:09 轮，单修路径指针的后果）：
- 149 个文件超 250 行且无豁免登记 → ① 直接红
- forward 69 个类词根在 glossary 无匹配（阈值 >10）→ ③ 直接红
- reverse 先 crash（`lca.plugins.loop.phase` 不存在）→ ④ 报错

结论：**不可单独合路径修复**——单修=同时打红+打崩。三测试（①③④）须同修，
且每修一个都暴露一批真实债务；② 须语义重写（`layer*` 布局已是历史）。

## 2. 架构判断：空心健身函数是治理缺陷，不是测试缺陷

健身函数（fitness function）的存在意义是"红钉真实退化"。一个恒绿/恒 skip 的健身函数
比没有更糟：它向所有人发出"治理有效"的虚假信号。本文件就是前车之鉴——
`test_no_banned_class_name_patterns` 曾被自引入起恒空的 `"gateway"` 扫描条目掩盖
（todo-53），直到 08:09 轮删掉死条目才首次真正执行、揭出 ADR-0290 的三个真实命名违规。
空心测试不是"没测"，是"谎报已测"。

根因四象限：指针漂移（`_PROJECT_ROOT`）× 语义过期（`layer*` 布局、`loop.phase` 包）
× 债务堆积（149 超行 / 69 无匹配词根）× 无非空心断言（扫描基数为 0 照样 pass/skip）。

因此本 ADR 提案两部分：(a) 激活策略（§3，分阶段还债+逐个点亮）；(b) 元规则（§4，
以后不许再空心，升不变量）。

## 3. 提案：分阶段激活策略（Phase A–D）

- **Phase A（tests/**，tests lane）**：一次重写，而非两次修。同一 commit 内同时修正
  `_PROJECT_ROOT` 指针（+ 存在性断言，见 C2）与重写过期语义（`layer*` → 显式 layer 包清单映射；
  `_REVERSE_SCAN_PACKAGES` 去掉 `lca.plugins.loop.phase`、换现行包）。本 phase 落地后
  ①③④ 预期红（真实债务信号，钉住即是进步），② 按新语义执行。
- **Phase B（docs/**，arch lane）**：glossary 还债。forward 的 69 个无匹配词根按认知域
  分 3–4 批补词条（每批独立 commit）；8 个 `known_deleted_terms` 移入
  「已废弃主名」表后从测试的 skip list 删除。
- **Phase C（lca/** + docs 豁免理由，quality lane 主、arch 配合）**：149 个超行文件的处置，
  三选一（待拍板，见 §5①）：(i) 分批豁免登记（`_LINE_COUNT_EXEMPT` 追加，每文件一句真实理由、
  引用本 ADR，分 3 批）；(ii) 阈值重设（250→待定，附全仓行数分布实证）；(iii) 大文件拆分工程
  （P1 分批，>500 行先行）。
- **Phase D（tests/**，tests lane）**：逐个点亮。按还债进度点亮对应测试，点亮顺序
  reverse → forward → line-count → layer-docstring（按还债依赖）；每个点亮是独立 commit，
  门禁是真绿，不为绿放水。

## 4. 提案：健身函数非空心元规则（C1–C4，升不变量）

- **C1 非空心基数门**：每个治理健身函数必须断言扫描基数 ≥ N
  （N 按测试语义定；建议见 §5③）。扫描基数为 0 时直接 fail（fail-closed），
  禁止用 pass/skip 静默。
- **C2 路径指针自检**：`_PROJECT_ROOT` 类仓库根指针必须经存在性断言
  （断言 `pyproject.toml` / `.git` / `lca/` 三者特征之一存在）。指针漂移 = 直接红，
  不许恒绿。
- **C3 豁免登记铁律**：`_LINE_COUNT_EXEMPT` / `_NAME_EXEMPT` 现有的"一句真实理由 + 引用"
  模式升为不变量；单次豁免超过 10 个文件/类须 ADR 仲裁（类比 ADR-0290 §13 Phase E）。
- **C4 glossary 现役定义 SSOT**：正反覆盖的"现役区"以 `docs/specs/glossary.md`
  的「已废弃主名」章节为唯一分界，测试只读不自定义。

## 5. 决策记录（2026-10-05，Athena 按李超授权裁决）

① **Phase C 三选一**：(i) 分批豁免登记 / (ii) 阈值重设 / (iii) 大文件拆分。
推荐 (i) 分批豁免登记：拆分 149 个文件是数月工程；阈值重设是数字游戏掩盖问题；
逐文件写一句真实理由的过程本身就是一次全仓大文件合理性审计，审计完自然知道哪些真该拆。

② **Phase B 补词条的节奏**：建议 arch lane 按认知域分 3–4 批、每批独立 commit 落地。

③ **C1 基数门 N 的具体值**：建议类扫描 ≥800、文件扫描 ≥400（略低于当前实际基数防抖动），
最终由 Phase A 落实时实测定。

④ **todo-56 的 P 级**：建议 P1（治理债，不阻塞生产行为）。

## 6. 诚实边界

- 本 ADR 为 **Proposed**；四测试现状依旧空心，tests lane 在 §5 拍板（已裁决）前不动（todo-56 约束延续）。
- 149 / 69 等数字引自 tests 09:09 轮干跑报告（`hidden_files/red-20261005-0909.txt` 同级证据），
  本轮 arch 未重测；Phase 落实前以实测为准。
- 本 ADR 未改动任何代码与文档现状；message 与 diff 相符（docs only）。

**裁决**：四项全部批准，按 §3/§4 实施。

- ① Phase C 选 **(i) 分批豁免登记**。第一性原理：健身函数的意义是让大文件自我辩护，不是强制小文件——
  逐文件写一句真实理由的过程本身就是一次全仓大文件合理性审计，审计完自然知道哪些真该拆。
  (ii) 阈值重设是数字游戏，掩盖问题；(iii) 拆分 149 个文件是数月工程、回归风险高，不值得为治理信号付出。
  豁免审计中被判定"真该拆"的文件，另立 P1 后续项，不在本 ADR 承诺拆分工程。
  注：149 个豁免超 C3 的"10+ 须 ADR 仲裁"门，本 ADR 即该仲裁，合规。
- ② Phase B 节奏批准：arch lane 按认知域分 3–4 批、每批独立 commit。
- ③ C1 基数门批准：类扫描 ≥800、文件扫描 ≥400（fail-closed 防空心），最终值由 Phase A 落实时实测并钉住。
- ④ todo-56 定级 **P1**：治理债，不阻塞生产行为。
- 派工：tests lane Phase A（一次重写，预期红是真实债务信号）；arch lane Phase B；quality lane 主导 Phase C；
  tests lane Phase D 按 reverse → forward → line-count → layer-docstring 顺序点亮，每点亮独立 commit，真绿才合。
