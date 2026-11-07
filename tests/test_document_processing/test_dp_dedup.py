"""document_processing.dedup 的单测：精确去重语义 / MinHash 估算 / 模糊去重降级可达性。

invariants：
- exact_dedup：先见者留存；重复记录完整（type=exact, similarity=1.0）；空文本**静默丢弃**；
- fuzzy_dedup：相同内容必删（Jaccard=1.0 恒过阈值），阈值与相似度判断在 MinHash 一致性上确定性成立。
"""

from __future__ import annotations

from langchain_core.documents import Document

from document_processing.dedup import (
    _estimate_lsh_memory,
    _select_num_perm,
    _shingle_ngrams,
    _SimpleMinHash,
    dedup_documents,
    exact_dedup,
    fuzzy_dedup,
)


def doc(text: str, source: str) -> Document:
    return Document(page_content=text, metadata={"source_path": source})


# ── shingle ──────────────────────────────────────────────────────────


def test_shingle_ngrams_char_level() -> None:
    grams = _shingle_ngrams("数据结构", n=3)
    assert grams == {"数据结", "据结构"}


def test_shingle_short_text_falls_back_to_whole() -> None:
    assert _shingle_ngrams("简", n=3) == {"简"}


def test_shingle_empty_text() -> None:
    assert _shingle_ngrams("", n=3) == set()


def test_shingle_collapses_whitespace() -> None:
    assert _shingle_ngrams("abc   def", n=5) == _shingle_ngrams("abc def", n=5)


# ── 精确去重 ─────────────────────────────────────────────────────────


def test_exact_dedup_keeps_first_and_records_duplicate() -> None:
    docs = [doc("内容甲", "a.txt"), doc("内容甲", "b.txt"), doc("内容乙", "c.txt")]
    unique, duplicates = exact_dedup(docs)
    assert [d.metadata["source_path"] for d in unique] == ["a.txt", "c.txt"]
    assert len(duplicates) == 1
    dup = duplicates[0]
    assert dup["source"] == "b.txt"
    assert dup["duplicate_of"] == "a.txt"
    assert dup["type"] == "exact"
    assert dup["similarity"] == 1.0
    assert unique[0].metadata["content_hash_md5"]


def test_exact_dedup_drops_empty_content_silently() -> None:
    # 空文本既不进 unique 也不进 duplicates——删除是确定性行为，锁死防回归
    docs = [doc("   ", "blank.txt"), doc("有效", "real.txt")]
    unique, duplicates = exact_dedup(docs)
    assert [d.metadata["source_path"] for d in unique] == ["real.txt"]
    assert duplicates == []


# ── MinHash ──────────────────────────────────────────────────────────


def test_simple_minhash_identical_texts_perfect_match() -> None:
    grams = _shingle_ngrams("学习OperatingSystem的知识要点合集", n=3)
    a = _SimpleMinHash(grams, num_perm=64)
    b = _SimpleMinHash(grams, num_perm=64)
    assert a.jaccard(b) == 1.0


def test_simple_minhash_disjoint_texts_low() -> None:
    # ★ 校准：语料必须零共享 3-gram——共用英文词（如 about）会引入真实重叠，
    # 32 位 MinHash 估计值会如实放大。两段纯中文互不共字。
    a = _SimpleMinHash(_shingle_ngrams("火车候车大厅排队乘客拥挤", n=3), num_perm=64)
    b = _SimpleMinHash(_shingle_ngrams("轮船码头卸货工人忙碌不停", n=3), num_perm=64)
    assert a.jaccard(b) <= 0.1


def test_simple_minhash_different_dims_return_zero() -> None:
    a = _SimpleMinHash({"甲乙丙"}, num_perm=32)
    b = _SimpleMinHash({"甲乙丙"}, num_perm=64)
    assert a.jaccard(b) == 0.0


# ── 模糊去重 ─────────────────────────────────────────────────────────


def test_fuzzy_dedup_removes_identical_content_regardless_of_metadata() -> None:
    docs = [doc("学习数据结构的知识要点", "x1.md"), doc("学习数据结构的知识要点", "x2.md")]
    unique, duplicates = fuzzy_dedup(docs)
    assert len(unique) == 1
    assert len(duplicates) == 1
    assert duplicates[0]["type"] == "fuzzy"
    assert duplicates[0]["source"] == "x2.md"
    assert duplicates[0]["duplicate_of"] == "x1.md"
    assert duplicates[0]["similarity"] >= 0.9


def test_fuzzy_dedup_keeps_distinct_documents() -> None:
    docs = [
        doc("图论中的最短路径算法讲解第一部分", "d1.md"),
        doc("数据库索引的叶页分裂机制解析", "d2.md"),
        doc("操作系统死锁的必要条件有四个要点", "d3.md"),
    ]
    unique, duplicates = fuzzy_dedup(docs)
    assert len(unique) == 3
    assert duplicates == []


def test_fuzzy_dedup_single_and_empty_passthrough() -> None:
    single = [doc("唯一的文档", "only.md")]
    unique, duplicates = fuzzy_dedup(single)
    assert unique == single
    assert duplicates == []


# ── 内存/参数自适应（纯算术）────────────────────────────────────────


def test_select_num_perm_reduces_for_large_sets() -> None:
    assert _select_num_perm(60_000, 128) == 64
    assert _select_num_perm(500, 128) == 128


def test_estimate_lsh_memory_arithmetic() -> None:
    # 1000 docs × 128 perm × 4B × 3(哈希表2x+开销1.5x) / 1MB ≈ 1.46MB
    est = _estimate_lsh_memory(1000, num_perm=128)
    assert abs(est - (1000 * 128 * 4 * 3 / (1024 * 1024))) < 1e-9


# ── 组合 ─────────────────────────────────────────────────────────────


def test_dedup_documents_combines_both_levels() -> None:
    docs = [
        doc(" learns about graphs ", "a1.md"),
        doc(" learns about graphs ", "a2.md"),  # exact dup of a1
        doc("图论中的独立的主题内容第一", "b1.md"),
        doc("数据库索引的完全另一段文本", "c1.md"),
    ]
    unique, all_dups = dedup_documents(docs)
    assert len(unique) == 3
    exact_dups = [d for d in all_dups if d["type"] == "exact"]
    fuzzy_dups = [d for d in all_dups if d["type"] == "fuzzy"]
    assert len(exact_dups) == 1
    assert fuzzy_dups == []  # 剩余三篇语义相异，不应产生模糊删除


def test_dedup_documents_respects_individual_switches() -> None:
    docs = [doc("same文本内容", "m1.md"), doc("same文本内容", "m2.md")]
    unique, dups = dedup_documents(docs, exact=True, fuzzy=False)
    assert len(unique) == 1 and dups

    # exact=False：不入 exact，但内容 100% 相同 → fuzzy 层照样删除一篇
    docs2 = [doc("same文本内容", "n1.md"), doc("same文本内容", "n2.md")]
    unique2, dups2 = dedup_documents(docs2, exact=False, fuzzy=True)
    assert len(unique2) == 1
    assert len(dups2) == 1
    assert dups2[0]["type"] == "fuzzy"
