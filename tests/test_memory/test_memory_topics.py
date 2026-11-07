"""memory.topics 的归一化单测：canonical 保真 / 别名表纪律 / rag 兜底契约。

依据（2026-11-07 实测探针 .tmp/syn_probe.json，跑完即删）：
- canonical 全集 164 个，其中 21 个含空格（`B 树` / `Cache 映射方式` / `TCP 流量控制` …）；
- `AVL树 → 平衡二叉树`：key 非 canonical、target ∈ canonical ⇒ 采纳；
- `BST → 二叉搜索树`：target ∉ canonical ⇒ **不得采纳**（落 ④ 压缩空白）；
- `二叉搜索树` 本身非 canonical（canonical 是 `二叉排序树`）。
"""

from __future__ import annotations

from memory.topics import (
    _TOPIC_ALIASES,
    canonical_names,
    normalize_topic,
    normalize_topics,
)

# 实测存在的含空格 canonical sample（若词表漂移，测试会明确指出是词表变了）
SPACED_CANONICAL = ("B 树", "Cache 映射方式", "TCP 流量控制")


def test_spaced_canonical_names_preserved_verbatim() -> None:
    canonical = canonical_names()
    for name in SPACED_CANONICAL:
        assert name in canonical, f"词表漂移：{name!r} 已不在 canonical"
        assert normalize_topic(name) == name


def test_alias_table_maps_to_canonical() -> None:
    assert normalize_topic("deadlock") == "死锁"
    assert normalize_topic("belady") == "页面置换算法"
    assert normalize_topic("虚存") == "虚拟内存"
    assert normalize_topic("信号量") == "进程同步"


def test_alias_lookup_is_case_insensitive() -> None:
    assert normalize_topic("DEADLOCK") == "死锁"
    assert normalize_topic("Belady") == "页面置换算法"


def test_every_alias_target_is_canonical() -> None:
    # gate ⑪f 的单测化：历史上"归一到不可达值"（deadlock→进程死锁）的纪律锁。
    # 目标若不在 canonical，等于造出永远命不中的归一方向，且不报错不丢数据。
    canonical = canonical_names()
    bad = {k: v for k, v in _TOPIC_ALIASES.items() if v not in canonical}
    assert not bad, f"别名表目标值漂移出 canonical：{bad}"


def test_rag_synonym_adopted_only_when_target_canonical() -> None:
    # 'AVL树' 不在 _TOPIC_ALIASES；SYNONYM_MAP['AVL树']='平衡二叉树' ∈ canonical ⇒ 兜底采纳
    assert normalize_topic("AVL树") == "平衡二叉树"
    assert normalize_topic("Hash表") == "散列表"


def test_rag_synonym_rejected_when_target_not_canonical() -> None:
    # 'BST' → '二叉搜索树'，但 '二叉搜索树' ∉ canonical ⇒ 不得采纳，稳定化原样
    assert normalize_topic("BST") == "BST"


def test_non_canonical_synonym_value_stays_stable_not_renamed() -> None:
    # 逆向危险案例：SYNONYM_MAP 里存在与 kp_index 方向相反的映射
    # （'二叉排序树'→'二叉搜索树'，canonical 恰是 '二叉排序树'）。
    # canonical 输入必须走 ① 原样；非 canonical 的 '二叉搜索树' 也不得被改写。
    assert normalize_topic("二叉排序树") == "二叉排序树"
    assert normalize_topic("二叉搜索树") == "二叉搜索树"


def test_empty_and_whitespace_return_empty() -> None:
    assert normalize_topic("") == ""
    assert normalize_topic("   ") == ""
    assert normalize_topic(None) == ""  # type: ignore[arg-type] — 防御路径（raw or ""）


def test_normalize_topics_dedups_keeps_order_and_drops_empty() -> None:
    assert normalize_topics(["AVL树", "AVL树", " ", "deadlock", ""]) == ["平衡二叉树", "死锁"]
    assert normalize_topics(None) == []
    assert normalize_topics([]) == []
