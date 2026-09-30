"""Doctor.v3 step-tree 主路径(ADR-0164 草案 Phase 4)。

输入: JournalDocument(或直接 path)。
输出: DoctorReport(schema="doctor.v3", mode=backend|ui)。

Hops:
  - H1: journal.json 是否存在 + 可读
  - H2: step 闭合完整性(所有 step.outcome 非 None)
  - H3: 步骤顺序连续(step_index 1..N 无跳号)
  - H4: ui-mode 才检查(前端是否能到达 run)
  - H5: ui-mode 才检查(前端能否渲染产出)
  - H6: 是否有可观察 output / file
  - H7: 工具成功率 +是否有失败 step
  - H8 (新): 步骤因果链完整性——每 step 的 prior_summary_chain
    末元素 == 上 step 的 reflect.summary;不一致 → ok=False
  - H-xref (ADR-0176 D5): journal ⇄ spine 跨源一致性 hop
    (body.tool.execute.start 数 > 0 但 journal.steps[*].tool_call 为 0,
     llm.call.end 数 > 0 但 journal.totals.steps == 0,等)
  - H-fold (ADR-0185 PR-4): doctor fold-only 检查——
    诊断是否每 step 都能通过 :func:`fold_model_visible` 从 spine ledger
    重建;无 fold 时 ok=None(unavailable),不再读 model_visible sidecar。

不做的事:
    - 不读 evidence(由 reader 按需 fetch)。
    - 不发请求(doctor 是 passive 检查)。
    - 不执行 LLM / tool(只读 fold 模块 + spine ledger)。

实现已拆到 ``doctor/steps/`` 包(scan / hops / diagnose);本文件是公共 barrel。
"""

from lca.plugins.transport.webserver.doctor.steps.diagnose import diagnose_step_tree

__all__ = ["diagnose_step_tree"]
