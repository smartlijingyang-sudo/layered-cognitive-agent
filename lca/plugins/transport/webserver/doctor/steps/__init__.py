"""Doctor.v3 step-tree 内部实现包(scan / hops / diagnose)。

``step_check.py`` 是公共 barrel,只 re-export ``diagnose_step_tree``;
实现按职责拆分到本包:
  - ``scan``:StepScan 事实收集(journal / spine / fold 扫描)
  - ``hops``:H1..H8 / H-seg / H-phase / H-xref / H-ssot / H-mv-journal / H-fold 判定
  - ``diagnose``:``diagnose_step_tree`` 装配入口
"""
