"""Track A: Deterministic Code Invariants Benchmark (轨 A：确定性代码不变量评测).

覆盖 7 大维度中所有硬契约、状态机、双时间线、门控与防火墙逻辑。
验收红线：100% 必须自动化断言通过（Exit code 0，零容忍）。
"""

from datetime import UTC, datetime
from pathlib import Path

from lca.cognition.memory.guards.firewall import MemoryTactFirewall
from lca.cognition.memory.guards.modality import ModalityResult, filter_ingestion_modality
from lca.cognition.memory.guards.salience import SalienceGate
from lca.cognition.memory.recall import SystemTwoRecallEngine
from lca.cognition.memory.types import SemanticClaim
from lca.infrastructure.memory.entities.store import EntityGraphStore
from lca.infrastructure.tools.shield.tool_shield import ToolPitfallShield


def test_track_a_hypothetical_examples_and_sarcasm_dropped():
    """[场景 13 & 15] 虚拟假设举例与反讽反话过滤。"""
    # 场景 13: 假设与举例不入库
    assert (
        filter_ingestion_modality("比如你有一个表弟在深圳开公司……")
        == ModalityResult.HYPOTHETICAL_DROP
    )
    assert filter_ingestion_modality("设想如果我将来移居火星……") == ModalityResult.HYPOTHETICAL_DROP
    assert (
        filter_ingestion_modality("假如我有五千万，我就去买海岛")
        == ModalityResult.HYPOTHETICAL_DROP
    )

    # 场景 15: 玩笑与反话不进偏好
    assert (
        filter_ingestion_modality("我最爱天天加班到半夜了！（明显反讽）")
        == ModalityResult.SARCASM_DROP
    )
    assert (
        filter_ingestion_modality("我真喜欢天天挤早高峰地铁，太享受了（反讽）")
        == ModalityResult.SARCASM_DROP
    )

    # 正常事实放行
    assert filter_ingestion_modality("我入职了字节跳动深圳研发中心") == ModalityResult.ADMIT_FACT


def test_track_a_salience_gate_anti_overgeneralization():
    """[场景 12] 不过度泛化：单次偶发事件禁止跃迁为 preference 长期偏好。"""
    gate = SalienceGate()

    # 单次偶发爬山申请作为 preference 偏好 -> 必须拒绝
    candidate_casual = {
        "category": "preference",
        "content": "用户偏好：户外登山爱好者",
        "confidence": 0.8,
        "dedupe_key": "preference:hobby",
    }
    verdict_low = gate.evaluate(
        task="周末跟朋友去爬了一次岳麓山",
        candidate=candidate_casual,
    )
    assert verdict_low.admitted is False
    assert verdict_low.reason == "single_casual_action_not_preference"

    # 用户明确偏好陈述 -> 放行
    candidate_explicit = {
        "category": "preference",
        "content": "用户偏好：代码必须有类型标注",
        "confidence": 1.0,
        "dedupe_key": "preference:code_style",
    }
    verdict_high = gate.evaluate(
        task="我写代码一贯要求必须有严格的类型标注",
        candidate=candidate_explicit,
    )
    assert verdict_high.admitted is True


def test_track_a_dual_timeline_supersede_and_history_preserved():
    """[场景 6 & 9] 信息更新与双时间线：以新为准，保留历史，旧条目被取代永不物理丢失。"""
    t_2023 = datetime(2023, 1, 1, tzinfo=UTC)
    t_2023_mid = datetime(2023, 6, 1, tzinfo=UTC)
    t_2024 = datetime(2024, 1, 1, tzinfo=UTC)

    # 历史条目：2023年在A公司工作
    old_claim = SemanticClaim(
        id="claim_company_a",
        claim="在A公司担任后端开发",
        confidence=1.0,
        sources=("dialogue_2023",),
        valid_from=t_2023,
        valid_to=t_2023_mid,  # 被取代时闭合有效区间
        category="fact",
        dedupe_key="career:company",
    )

    # 新条目：2023年6月入职B公司，supersedes 旧条目
    new_claim = SemanticClaim(
        id="claim_company_b",
        claim="在B公司担任架构师",
        confidence=1.0,
        sources=("dialogue_2023_mid",),
        valid_from=t_2023_mid,
        valid_to=None,  # 当前持续有效
        supersedes="claim_company_a",
        category="fact",
        dedupe_key="career:company",
    )

    # 在 2023 年初，旧条目有效，新条目尚未发生
    assert old_claim.is_valid_at(t_2023) is True
    assert new_claim.is_valid_at(t_2023) is False

    # 在 2024 年，旧条目已过期但仍存在，新条目为当前真值
    assert old_claim.is_valid_at(t_2024) is False
    assert new_claim.is_valid_at(t_2024) is True
    assert new_claim.supersedes == old_claim.id


def test_track_a_right_to_be_forgotten(tmp_path: Path):
    """[场景 10] 要求遗忘：彻底删除相关实体或关系，严禁变相保留。"""
    store = EntityGraphStore(base_dir=tmp_path)

    # 铺垫：存入前任信息
    store.save_entity(
        domain="people",
        slug="ex-partner",
        content="前任名字叫张三，曾一起在广州生活",
        tags=("relationship", "ex"),
    )
    assert store.read_entity("people", "ex-partner") is not None
    assert len(store.search_entities("广州")) > 0

    # 触发遗忘：物理删除
    deleted = store.delete_entity("people", "ex-partner")
    assert deleted is True

    # 验证：实体彻底消失，FTS 索引彻底清空
    assert store.read_entity("people", "ex-partner") is None
    assert len(store.search_entities("广州")) == 0
    assert "ex-partner" not in store.get_active_graph_index()


def test_track_a_sensitive_memory_isolation_and_on_demand_disclosure():
    """[场景 23 & 24] 敏感记忆分寸：无关轮次 100% 遮蔽，直接询问如实回答。"""
    bereavement_claim = SemanticClaim(
        id="claim_sensitive_01",
        claim="亲人因癌症去世",
        confidence=1.0,
        sources=("dialogue_sensitive",),
        valid_from=None,
        sensitivity="high",
    )
    normal_claim = SemanticClaim(
        id="claim_normal_01",
        claim="常用主力语言是 Python 和 Rust",
        confidence=1.0,
        sources=("dialogue_normal",),
        valid_from=None,
        sensitivity="normal",
    )

    firewall = MemoryTactFirewall(memories=[bereavement_claim, normal_claim])

    # 场景 23: 问天气或通用技术问题，敏感记忆 100% 遮蔽
    prompt_memories_irrelevant = firewall.filter_for_prompt(user_intent="明天北京穿什么衣服合适？")
    joined_text = " ".join(prompt_memories_irrelevant)
    assert "癌症" not in joined_text
    assert "去世" not in joined_text
    assert "Python" in joined_text

    # 场景 24: 用户主动直接询问变故
    prompt_memories_direct = firewall.filter_for_prompt(
        user_intent="我之前跟你提过我家里的变故吗？"
    )
    assert "癌症去世" in " ".join(prompt_memories_direct)


def test_track_a_voice_contract_anti_showoff():
    """[场景 25] 禁显摆声带契约：清洗‘我记得你说过’、‘根据长期记忆库’等监控感邀功式套话。"""
    firewall = MemoryTactFirewall()

    # 含有显摆套话被侦测
    assert firewall.contains_showoff_phrase("我记得你说过你对芒果过敏，所以别吃这个。") is True
    assert firewall.contains_showoff_phrase("根据我的长期记忆库记录，您在2021年毕业。") is True

    # 自然表达不报假警
    assert firewall.contains_showoff_phrase("为您推荐这道无芒果甜点。") is False

    # 清洗为自然客观表达
    sanitized = firewall.sanitize_response("我记得你说过你喜欢安静的咖啡馆，推荐去三里屯那家。")
    assert "我记得你说过" not in sanitized
    assert "你喜欢安静的咖啡馆" in sanitized


def test_track_a_tool_pitfall_shield_sub_millisecond_redline():
    """[工具避坑哨兵] 调用前毫秒级匹配 TOOLS.md 中的单行安全红线。"""
    tools_md = """# TOOLS.md
### ssh
- 宿主机远程请优先使用 ssh252 别名，且禁依赖 /root 软链。
### git
- 严禁向外部仓库直接 push，提交前务必 git diff --check。
"""
    shield = ToolPitfallShield.from_markdown(tools_md)

    # 验证命中红线
    guard_ssh = shield.get_pre_execution_guard("ssh")
    assert "ssh252" in guard_ssh
    assert "禁依赖 /root 软链" in guard_ssh

    guard_git = shield.get_pre_execution_guard("git")
    assert "git diff --check" in guard_git

    # 未配置工具无红线
    assert shield.get_pre_execution_guard("pytest") == ""



def test_track_a_system_two_multi_hop_and_anti_hallucination(tmp_path: Path):
    """[场景 2 & 5] System 2 多跳关系寻路与检索未命中诚实返回 NoRecall。"""
    store = EntityGraphStore(base_dir=tmp_path)

    # 场景 2: 铺垫人物关系链：我 -> 小杰 -> 晓雯
    store.save_entity(
        domain="people",
        slug="me",
        content="用户本人",
        relations={"xiaojie": "cousin"},
    )
    store.save_entity(
        domain="people",
        slug="xiaojie",
        content="表弟小杰，在深圳做程序员",
        relations={"xiaowen": "girlfriends_sister"},
    )
    store.save_entity(
        domain="people",
        slug="xiaowen",
        content="晓雯，小杰女朋友的姐姐",
    )

    engine = SystemTwoRecallEngine(store=store)

    # 多跳关系查询：寻找 晓雯
    result = engine.recall(query="晓雯 人际关系", start_slug="me", max_hops=2)
    assert result.has_recalled is True
    assert result.hops_count <= 2
    assert any("xiaowen" in claim for claim in result.recalled_claims)
    assert len(result.relation_chains) >= 1
    assert len(result.relation_chains[0]) == 2

    # 场景 5: 虚构事实诚实返回 NoRecall，绝不编造
    fake_result = engine.recall(query="火星殖民地避难所密码", max_hops=2)
    assert fake_result.has_recalled is False
    assert "未检索到" in fake_result.uncertainty_note


def test_track_a_entity_graph_budget_and_gc(tmp_path: Path):
    """[预算控制与 GC] 活跃实体超出预算时沉降至 archives/，微索引控制在指定 entries 范围内。"""
    store = EntityGraphStore(
        base_dir=tmp_path,
        max_active_entities=3,
        max_graph_entries=2,
    )

    for i in range(5):
        store.save_entity(
            domain="projects",
            slug=f"proj_{i}",
            content=f"项目描述 {i}",
        )

    # 活跃目录不超过 3 个
    active_files = list((tmp_path / "memory" / "entities" / "projects").glob("*.md"))
    assert len(active_files) <= 3

    # 归档目录接收沉降文件
    archived_files = list((tmp_path / "memory" / "archives" / "entities" / "projects").glob("*.md"))
    assert len(archived_files) >= 2

    # 微索引不超过 2 条
    graph_md = store.get_active_graph_index()
    entry_lines = [line for line in graph_md.splitlines() if line.startswith("- projects/")]
    assert len(entry_lines) <= 2
