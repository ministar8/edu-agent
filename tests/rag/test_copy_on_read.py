"""缓存命中时的 copy-on-read 保护。

_query_cache / _rerank_cache 存的是 Document 列表，下游会往 Document.metadata 写东西
（`_collection`、窗口展开、噪声降级等）。若命中时直接返回缓存里的原对象，这些写入会
污染缓存，后续命中就会拿到被别人改过的数据。
"""

from langchain_core.documents import Document

from rag.reranker import _copy_ranked
from rag.retriever import _copy_results


class TestCopyRanked:
    def test_returns_distinct_documents(self):
        docs = [Document(page_content="a", metadata={"k": 1})]
        copied = _copy_ranked(docs)

        assert copied is not docs
        assert copied[0] is not docs[0]
        assert copied[0].page_content == "a"
        assert copied[0].metadata == {"k": 1}

    def test_mutating_copy_does_not_touch_source(self):
        docs = [Document(page_content="a", metadata={"k": 1})]
        copied = _copy_ranked(docs)
        copied[0].metadata["k"] = 999

        assert docs[0].metadata["k"] == 1

    def test_empty(self):
        assert _copy_ranked([]) == []


class TestCopyResults:
    def test_returns_distinct_documents(self):
        results = [(Document(page_content="a", metadata={"k": 1}), 0.5)]
        copied = _copy_results(results)

        assert copied is not results
        assert copied[0][0] is not results[0][0]
        assert copied[0][1] == 0.5

    def test_mutating_copy_does_not_touch_source(self):
        results = [(Document(page_content="a", metadata={}), 0.5)]
        copied = _copy_results(results)
        copied[0][0].metadata["_collection"] = "os"

        assert results[0][0].metadata == {}

    def test_empty(self):
        assert _copy_results([]) == []
