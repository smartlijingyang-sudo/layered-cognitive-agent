from lca.application.collaboration.fold import DelegationFoldAggregator


def test_fold_aggregator_unanimous():
    aggregator = DelegationFoldAggregator()
    receipts = {
        "architecture/guanlan": "边界清晰，符合领域契约，Does NOT own 负向清单完备。",
        "architecture/hengyue": "满足 C4 Reducer 单写不变量，六分类判定准确。",
        "architecture/jingchuan": "无 AP-01~06 反模式违例，代码工程卫生达标。",
    }
    result = aggregator.fold(task_id="task_001", receipts=receipts)
    assert result.task_id == "task_001"
    assert result.consensus_status == "unanimous"
    assert "架构三角已形成完全共识" in result.synthesized_verdict
    assert len(result.member_findings) == 3
    assert result.member_findings["architecture/guanlan"] == receipts["architecture/guanlan"]


def test_fold_aggregator_with_timeout_and_error_degradation():
    aggregator = DelegationFoldAggregator()
    receipts = {
        "architecture/guanlan": "边界划分通过",
        "architecture/hengyue": "满足状态机不变量",
        "architecture/jingchuan": "[TIMEOUT] 分析耗时超过 60s 触发熔断截断",
    }
    result = aggregator.fold(task_id="task_002", receipts=receipts)
    assert result.consensus_status == "concerns_noted"
    assert "镜川分析超时" in result.synthesized_verdict or "超时" in result.synthesized_verdict
    assert "基于就绪专家" in result.synthesized_verdict and "结论综合" in result.synthesized_verdict


def test_fold_aggregator_anti_context_pollution():
    aggregator = DelegationFoldAggregator()
    # 模拟专家沙箱内残留的大量命令行噪声与长日志
    noisy_receipt = (
        "$ git log -n 100\n"
        "commit 1234567890abcdef\n"
        "Author: test <test@test>\n"
        "DEBUG: [transport] connection pool created (pid=9999)\n"
        "TRACE: fiber 1234 yield\n"
        "...\n"
        "结论：经代码检索，所有分层契约均无反向依赖，符合规范。"
    )
    receipts = {
        "architecture/guanlan": noisy_receipt,
    }
    result = aggregator.fold(task_id="task_003", receipts=receipts)
    cleaned = result.member_findings["architecture/guanlan"]
    assert "DEBUG:" not in cleaned
    assert "TRACE:" not in cleaned
    assert "结论：经代码检索，所有分层契约均无反向依赖，符合规范。" in cleaned
