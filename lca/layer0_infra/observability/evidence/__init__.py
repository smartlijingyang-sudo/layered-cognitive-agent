"""Evidence plane —— 受治理证据后端实现(ADR-0065 PR-2 / §四)。

``FilesystemEvidenceStore`` 把 CAS + policy 封装成符合 ``EvidenceStore``
契约的实现,默认走 fs;``DefaultEvidencePolicy`` 给出``restricted`` 永不
内联 / 64 KiB 阈值 / 关键字触发升级分类 的默认决策。
"""
