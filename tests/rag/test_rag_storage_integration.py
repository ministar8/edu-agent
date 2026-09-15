"""RAG 存储层集成测试：语义缓存 + 向量库 + 确定性假嵌入。

**为什么需要这个文件**：`rag/semantic_cache.py`（661 行）、`rag/vectorstore.py`（500 行）、
`rag/embeddings.py`（373 行）此前覆盖率 **0%**。根因不是"逻辑简单不用测"，而是它们都
依赖本地 TEI（`localhost:11435`）与真实 ChromaDB 目录，CI 里起不来 —— 于是长期无人触碰。

`settings.USE_FAKE_EMBEDDING` + 临时 Chroma 目录让这三层第一次可测。这很重要，因为
**语义缓存是静默错误的高危区**：缓存命中即跳过整条检索链，一旦归属校验或 TTL 判断出错，
系统会把 A 学生的答案、或别的知识库集合的结果，当作正确证据返回，而且**不报错**。

**隔离要求（关键）**：`semantic_cache._DATA_DIR` / `_JSONL_FILE` 是**模块级常量、import 期
即固化为真实项目路径**（`chroma_db/semantic_cache/evidence.jsonl`）。因此 fixture 必须同时
重定向它们，否则测试会写坏真实缓存文件。`isolated_rag_storage` 已处理，且为 autouse，
本文件内不存在误触真实目录的路径。
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from core.settings import settings
from rag.evidence import FusedEvidence, TextEvidence

# ── 隔离 fixture ────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_rag_storage(tmp_path, monkeypatch):
    """把 Chroma 持久化目录、语义缓存 JSONL、各单例全部指向 tmp_path。"""
    import rag.semantic_cache as sc
    import rag.vectorstore as vs

    monkeypatch.setattr(settings, "USE_FAKE_EMBEDDING", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    # 端口指向必然无人监听的端口，确保走 PersistentClient 而非连上真实 Chroma
    monkeypatch.setattr(settings, "CHROMA_PORT", 1)

    data_dir = tmp_path / "chroma" / "semantic_cache"
    # 模块级常量，必须显式重定向（见文件 docstring）
    monkeypatch.setattr(sc, "_DATA_DIR", data_dir)
    monkeypatch.setattr(sc, "_JSONL_FILE", data_dir / "evidence.jsonl")
    # 单例重置，避免跨测试串扰与残留真实目录引用
    monkeypatch.setattr(vs, "_vector_store_manager", None)
    monkeypatch.setattr(sc, "_semantic_cache", None)

    yield tmp_path


def _deletes_are_permitted(tmp_path) -> bool:
    """探测本环境是否允许删除文件。

    部分沙箱环境会在删除时抛出 ``SystemExit``（而非 OSError）。注意 ``SystemExit``
    继承自 ``BaseException``，**不会被 ``except Exception`` 捕获** —— 这正是它会在
    `clear()` 内部逃逸出来的原因。

    只在守卫确实生效时跳过，不做宽泛兜底：避免把真实缺陷伪装成"环境问题"。
    """
    probe = tmp_path / "_delete_probe"
    probe.write_text("x", encoding="utf-8")
    try:
        probe.unlink()
    except SystemExit:
        return False
    return True


def _fused(context: str, source: str = "os.md") -> FusedEvidence:
    return FusedEvidence(
        text_evidences=[TextEvidence(evidence_id="e1", content=context, source=source, score=0.9)],
        final_context=context,
        sources=[source],
        used_token_budget=12,
    )


# ── 确定性假嵌入 ────────────────────────────────────────


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class TestHashingEmbeddings:
    """假嵌入必须满足：确定性、可归一、非零、保留词汇重叠信号。"""

    def test_is_deterministic_across_calls(self):
        from rag.embeddings import HashingEmbeddings

        emb = HashingEmbeddings(dim=256)
        assert emb.embed_query("虚拟内存") == emb.embed_query("虚拟内存")

    def test_dimension_follows_setting(self):
        from rag.embeddings import HashingEmbeddings

        assert len(HashingEmbeddings(dim=128).embed_query("x")) == 128
        assert len(HashingEmbeddings(dim=settings.EMBEDDING_DIM).embed_query("x")) == (
            settings.EMBEDDING_DIM
        )

    def test_vector_is_l2_normalised(self):
        from rag.embeddings import HashingEmbeddings

        vec = HashingEmbeddings(dim=256).embed_query("进程调度算法")
        assert sum(v * v for v in vec) ** 0.5 == pytest.approx(1.0)

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_blank_text_yields_non_zero_vector(self, text):
        # Chroma 的 cosine 距离对零向量无定义 —— 空文本必须给出非零向量
        from rag.embeddings import HashingEmbeddings

        vec = HashingEmbeddings(dim=64).embed_query(text)
        assert any(v != 0.0 for v in vec)

    def test_identical_text_has_cosine_one(self):
        from rag.embeddings import HashingEmbeddings

        emb = HashingEmbeddings(dim=512)
        assert _cos(emb.embed_query("什么是虚拟内存"), emb.embed_query("什么是虚拟内存")) == (
            pytest.approx(1.0)
        )

    def test_lexical_overlap_ranks_above_unrelated(self):
        from rag.embeddings import HashingEmbeddings

        emb = HashingEmbeddings(dim=512)
        base = emb.embed_query("进程调度算法")
        overlap = emb.embed_query("进程调度算法的实现")  # 共享大量 bigram
        unrelated = emb.embed_query("二叉树的遍历")  # 几乎无重叠

        assert _cos(base, overlap) > _cos(base, unrelated)

    def test_whitespace_does_not_change_vector(self):
        from rag.embeddings import HashingEmbeddings

        emb = HashingEmbeddings(dim=256)
        assert emb.embed_query("进程 调度") == emb.embed_query("进程调度")

    @pytest.mark.asyncio
    async def test_async_variants_agree_with_sync(self):
        from rag.embeddings import HashingEmbeddings

        emb = HashingEmbeddings(dim=128)
        assert await emb.aembed_query("虚拟内存") == emb.embed_query("虚拟内存")
        assert await emb.aembed_documents(["a", "b"]) == emb.embed_documents(["a", "b"])


class TestGetEmbeddingsHonoursFlag:
    def test_returns_fake_when_enabled(self, monkeypatch):
        from rag.embeddings import HashingEmbeddings, get_embeddings

        monkeypatch.setattr(settings, "USE_FAKE_EMBEDDING", True)
        assert isinstance(get_embeddings(), HashingEmbeddings)

    def test_returns_http_client_when_disabled(self, monkeypatch):
        from rag.embeddings import OpenAICompatibleEmbeddings, get_embeddings

        monkeypatch.setattr(settings, "USE_FAKE_EMBEDDING", False)
        emb = get_embeddings()
        assert isinstance(emb, OpenAICompatibleEmbeddings)
        # 构造不得发起网络请求（仅实例化配置）
        assert emb.base_url == settings.EMBEDDING_API_BASE


class TestHashingSchemeIsPinned:
    """把哈希方案钉死。

    换掉哈希函数（例如图省事用内置 `hash()`）会让**已写入 Chroma 的向量全部失效**：
    进程内看起来一切正常，但重启后同一文本得到不同向量，表现为"刚写入就查不到"。
    这类故障极难定位，所以在此显式钉死桶分配，让算法变更有意为之且可见。
    """

    def test_bucket_assignment_is_stable(self):
        from rag.embeddings import HashingEmbeddings

        assert HashingEmbeddings._bucket("进程", 64) == 13
        assert HashingEmbeddings._bucket("调度", 64) == 2
        assert HashingEmbeddings._bucket("进程调度算法", 64) == 28

    def test_vector_layout_is_stable(self):
        from rag.embeddings import HashingEmbeddings

        vec = HashingEmbeddings(dim=64).embed_query("进程调度算法")
        nonzero = {i: v for i, v in enumerate(vec) if v}

        # 6 个 token（5 个 bigram + 整串）落入 5 个桶 —— 其中一桶发生碰撞计数为 2
        assert set(nonzero) == {1, 2, 13, 28, 63}
        assert nonzero[2] == pytest.approx(2 / (8**0.5))
        for index in (1, 13, 28, 63):
            assert nonzero[index] == pytest.approx(1 / (8**0.5))


# ── 语义缓存 ────────────────────────────────────────────


class TestSemanticCacheRoundTrip:
    def test_store_then_identical_query_hits(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        hit, similarity = cache.lookup("什么是虚拟内存", collection_name="os")
        assert hit is not None
        assert similarity == pytest.approx(1.0)
        # 证据内容必须原样取回，而不是只有个壳
        assert hit.final_context == "虚拟内存上下文"
        assert hit.text_evidences[0].source == "os.md"
        assert hit.used_token_budget == 12

    def test_unrelated_query_misses(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        hit, _ = cache.lookup("二叉树的遍历方式", collection_name="os")
        assert hit is None

    def test_collection_mismatch_misses(self):
        # 归属校验：同一 query 存在 os 集合下，不得被 ds 集合命中
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        hit, _ = cache.lookup("什么是虚拟内存", collection_name="ds")
        assert hit is None

    def test_filter_signature_mismatch_misses(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store(
            "什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os", filter_sig="a=1"
        )

        hit, _ = cache.lookup("什么是虚拟内存", collection_name="os", filter_sig="a=2")
        assert hit is None

    def test_expired_entry_misses(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache(ttl=-1)  # 负 TTL → 任何条目一存即过期
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        hit, _ = cache.lookup("什么是虚拟内存", collection_name="os")
        assert hit is None
        # 过期条目应被清理，而不是留在内存索引里
        assert cache.stats()["entries"] == 0

    def test_stats_track_hits_misses_and_entries(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")
        cache.lookup("什么是虚拟内存", collection_name="os")  # hit
        cache.lookup("完全无关的另一句话", collection_name="os")  # miss

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        assert stats["hit_rate"] == pytest.approx(50.0)

    def test_evidence_is_persisted_to_jsonl(self, isolated_rag_storage):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        jsonl = isolated_rag_storage / "chroma" / "semantic_cache" / "evidence.jsonl"
        assert jsonl.exists()
        assert "虚拟内存上下文" in jsonl.read_text(encoding="utf-8")

    def test_survives_new_instance(self):
        # 持久化：新实例应从 JSONL 重建元数据并命中旧条目
        from rag.semantic_cache import SemanticCache

        first = SemanticCache()
        first.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")

        second = SemanticCache()
        hit, _ = second.lookup("什么是虚拟内存", collection_name="os")
        assert hit is not None
        assert hit.final_context == "虚拟内存上下文"

    def test_max_entries_evicts_oldest(self):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache(max_entries=2)
        for query in ("第一个查询", "第二个查询", "第三个查询"):
            cache.store(query, _fused(f"{query} 的上下文"), collection_name="os")

        assert cache.stats()["entries"] == 2

    def test_clear_empties_entries_and_makes_lookup_miss(self, tmp_path):
        if not _deletes_are_permitted(tmp_path):
            pytest.skip("环境删除守卫拦截 unlink，无法验证 clear() 的物理删除分支")

        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")
        assert cache.lookup("什么是虚拟内存", collection_name="os")[0] is not None

        cache.clear()

        assert cache.stats()["entries"] == 0
        assert cache.lookup("什么是虚拟内存", collection_name="os")[0] is None

    def test_disabled_cache_is_a_noop(self, monkeypatch):
        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()
        monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", False)

        cache.store("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")
        hit, similarity = cache.lookup("什么是虚拟内存", collection_name="os")

        assert hit is None
        assert similarity == 0.0
        assert cache.stats()["entries"] == 0

    def test_async_store_and_lookup(self):
        import asyncio

        from rag.semantic_cache import SemanticCache

        cache = SemanticCache()

        async def _roundtrip():
            await cache.astore("什么是虚拟内存", _fused("虚拟内存上下文"), collection_name="os")
            return await cache.alookup("什么是虚拟内存", collection_name="os")

        hit, similarity = asyncio.run(_roundtrip())
        assert hit is not None
        assert similarity == pytest.approx(1.0)


# ── 向量库 ──────────────────────────────────────────────


class TestVectorStoreRoundTrip:
    def test_similarity_search_returns_lexically_matching_document(self):
        from rag.vectorstore import get_vector_store_manager

        store = get_vector_store_manager().get_store("it_coll")
        store.add_documents(
            [
                Document(
                    page_content="进程调度算法包括时间片轮转", metadata={"source_file": "os.md"}
                ),
                Document(page_content="二叉树的遍历方式", metadata={"source_file": "ds.md"}),
            ]
        )

        results = store.similarity_search_with_score("进程调度算法", k=1)
        assert results[0][0].metadata["source_file"] == "os.md"

    def test_get_store_returns_cached_instance_per_collection(self):
        from rag.vectorstore import get_vector_store_manager

        mgr = get_vector_store_manager()
        assert mgr.get_store("same_coll") is mgr.get_store("same_coll")

    def test_collections_are_isolated(self):
        from rag.vectorstore import get_vector_store_manager

        mgr = get_vector_store_manager()
        mgr.get_store("coll_a").add_documents(
            [Document(page_content="只在 A 集合里的内容", metadata={"source_file": "a.md"})]
        )

        # B 集合未写入任何内容 → 查不到 A 的数据
        assert mgr.get_store("coll_b").get()["ids"] == []

    def test_added_documents_are_queryable_after_reopen(self, monkeypatch):
        # 持久化：丢弃单例后重新打开，仍能读到已写入的数据
        import rag.vectorstore as vs

        store = vs.get_vector_store_manager().get_store("persist_coll")
        store.add_documents(
            [Document(page_content="分页存储管理", metadata={"source_file": "os.md"})]
        )
        count_before = store._collection.count()

        monkeypatch.setattr(vs, "_vector_store_manager", None)  # 模拟重新打开
        reopened = vs.get_vector_store_manager().get_store("persist_coll")

        assert count_before == 1
        assert reopened._collection.count() == count_before


class TestRetrievalPathTakesReadLock:
    """检索路径必须走 manager 的**加锁**读方法。

    **这是 HNSW「段文件不落盘」的根因所在**：`_rw_lock` 只在
    `VectorStoreManager.similarity_search_with_score` 里加了读锁，
    而 `_raw_search` 原先直接调 `store.similarity_search_with_score` —— 绕过读锁，
    与 `add_documents` 的写锁形不成互斥。Chroma 的 Rust 后端在 add 返回后
    可能仍在落盘 HNSW 段，并发查询就会打开半成品段并抛
    `Error creating hnsw segment reader: Nothing found on disk`。

    症状很有迷惑性：**就绪探测能过、首个真实查询却失败**（探测走的是加锁路径），
    命中的集合随机，且 delete+重建能修好。
    """

    def test_raw_search_goes_through_locked_manager_method(self, monkeypatch):
        from rag import retriever as R
        from rag import vectorstore as vs

        called = {}

        class FakeManager:
            def similarity_search_with_score(self, collection_name, query, k, filter=None):
                called.update(collection_name=collection_name, query=query, k=k, filter=filter)
                return [(Document(page_content="命中", metadata={}), 0.9)]

            def get_store(self, name):
                raise AssertionError("不得直接取 store 绕过读锁")

        monkeypatch.setattr(vs, "get_vector_store_manager", lambda: FakeManager())
        R._query_cache.clear()

        out = R._raw_search("什么是进程？", "operating_system", 5)

        assert called["collection_name"] == "operating_system"
        # k 会被过采样放大（见 TestSemanticOversampling）—— 这里只确认调用确实发生
        assert called["k"] >= 5
        assert len(out) == 1

    def test_filter_is_forwarded_to_locked_method(self, monkeypatch):
        from rag import retriever as R
        from rag import vectorstore as vs

        called = {}

        class FakeManager:
            def similarity_search_with_score(self, collection_name, query, k, filter=None):
                called["filter"] = filter
                return []

            def get_store(self, name):
                raise AssertionError("不得直接取 store")

        monkeypatch.setattr(vs, "get_vector_store_manager", lambda: FakeManager())
        R._query_cache.clear()

        R._raw_search("q", "coll", 3, filter={"category": "x"})

        assert called["filter"] == {"category": "x"}

    def test_collection_marker_still_injected(self, monkeypatch):
        """改走加锁方法后，`_collection` 注入不能丢 —— RRF 靠它区分跨集合同名文档。"""
        from rag import retriever as R
        from rag import vectorstore as vs

        class FakeManager:
            def similarity_search_with_score(self, collection_name, query, k, filter=None):
                return [(Document(page_content="x", metadata={}), 0.5)]

            def get_store(self, name):
                raise AssertionError("不得直接取 store")

        monkeypatch.setattr(vs, "get_vector_store_manager", lambda: FakeManager())
        R._query_cache.clear()

        out = R._raw_search("q", "my_coll", 3)

        assert out[0][0].metadata["_collection"] == "my_coll"


class TestSemanticOversampling:
    """语义检索的过采样 + 确定性截断。

    **背景（backlog #29）**：Chroma 是近似索引，top-k 边界会抖 ——
    实测偶尔少返回一个本该进 top-k 的候选，且会传导到最终结果。

    **本组测试只断言"可验证的那一半"**：给定同一批候选，
    输出顺序**不再依赖 Chroma 的返回次序**（用 (分数, 内容键) 做全序）。
    "抖动整体消失"是**未经验证**的 —— 现象太罕见，做不出可靠的 A/B，
    不能声称已修复。这一区分必须留在测试里，否则下一个人会以为 #29 已闭环。
    """

    def _patch_manager(self, monkeypatch, pairs):
        from rag import retriever as R
        from rag import vectorstore as vs

        seen = {}

        class FakeManager:
            def similarity_search_with_score(self, collection_name, query, k, filter=None):
                seen["k"] = k
                return list(pairs)

            def get_store(self, name):
                raise AssertionError("不得直接取 store 绕过读锁")

        monkeypatch.setattr(vs, "get_vector_store_manager", lambda: FakeManager())
        R._query_cache.clear()
        return seen

    @staticmethod
    def _doc(name):
        return Document(page_content=name, metadata={"content_hash": name})

    def test_requests_oversampled_candidate_count(self, monkeypatch):
        from rag import retriever as R

        seen = self._patch_manager(monkeypatch, [(self._doc("a"), 0.9)])
        R._raw_search("q", "coll", 5)
        assert seen["k"] == 5 * R._SEMANTIC_OVERSAMPLE, "必须多取候选，否则截断没有意义"

    def test_truncates_back_to_k(self, monkeypatch):
        from rag import retriever as R

        pairs = [(self._doc(chr(ord("a") + i)), 1.0 - i * 0.01) for i in range(10)]
        self._patch_manager(monkeypatch, pairs)
        out = R._raw_search("q", "coll", 3)
        assert len(out) == 3

    def test_output_order_is_independent_of_input_order(self, monkeypatch):
        """**这是本次改动的核心保证**：输出顺序只由 (分数, 内容键) 决定。

        同一批候选，无论 Chroma 以什么次序返回，最终顺序都必须一致 ——
        原先直接透传 Chroma 的返回次序，而那个次序本身不确定。
        """
        from rag import retriever as R

        base = [
            (self._doc("alpha"), 0.90),
            (self._doc("bravo"), 0.80),
            (self._doc("charlie"), 0.70),
            (self._doc("delta"), 0.60),
        ]

        outputs = []
        for ordering in (base, list(reversed(base)), [base[2], base[0], base[3], base[1]]):
            self._patch_manager(monkeypatch, ordering)
            out = R._raw_search("q", "coll", 4)
            outputs.append([d.page_content for d, _s in out])

        assert outputs[0] == outputs[1] == outputs[2]
        assert outputs[0] == ["alpha", "bravo", "charlie", "delta"], "应按分数降序"

    def test_ties_are_broken_by_content_key(self, monkeypatch):
        """分数相同时靠内容键定序 —— 否则并列项的次序仍然不确定。"""
        from rag import retriever as R

        pairs = [(self._doc("zzz"), 0.5), (self._doc("aaa"), 0.5)]
        self._patch_manager(monkeypatch, pairs)
        out = R._raw_search("q", "coll", 2)
        assert [d.page_content for d, _s in out] == ["aaa", "zzz"]

    def test_higher_score_wins_even_if_returned_last(self, monkeypatch):
        """分数更高的候选即使排在返回列表末尾，也必须被截断保留。"""
        from rag import retriever as R

        pairs = [(self._doc("low"), 0.1), (self._doc("high"), 0.9)]
        self._patch_manager(monkeypatch, pairs)
        out = R._raw_search("q", "coll", 1)
        assert out[0][0].page_content == "high"
