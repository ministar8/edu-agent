"""Semantic cache for RAG retrieval results (ChromaDB-backed).

Caches FusedEvidence by query semantic similarity using embedding vectors
stored in a dedicated ChromaDB collection ``semantic_cache``.
When a semantically similar query is received, the cached FusedEvidence is
reused, skipping the entire retrieval pipeline (vector search, BM25, KG,
fusion, verification).

Only the retrieval layer is cached — LLM generation + governance + reflection
still run on every request, ensuring answer freshness and user-profile awareness.
"""
from __future__ import annotations

import hashlib
import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.rag.evidence import FusedEvidence

logger = logging.getLogger(__name__)

# ── Defaults (overridden by settings) ──────────────────────
_COLLECTION_NAME = "semantic_cache"
_DATA_DIR = Path(settings.CHROMA_PERSIST_DIR) / "semantic_cache"
_JSONL_FILE = _DATA_DIR / "evidence.jsonl"
_TTL = 1800          # 30 minutes
_MAX_ENTRIES = 500
_SIMILARITY_THRESHOLD = 0.88


# ── Helpers ────────────────────────────────────────────────

def _cache_key(query: str, collection_name: str = "", filter_sig: str = "") -> str:
    """Deterministic key from normalized query + collection + filter signature.

    Different collections or filters should NOT share cache entries,
    even if queries are semantically similar.
    """
    normalized = query.strip().lower()
    raw = f"{normalized}|{collection_name}|{filter_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _serialize_evidence(fused: FusedEvidence) -> str:
    """Serialize FusedEvidence to JSON string for disk storage."""
    return fused.model_dump_json()


def _deserialize_evidence(data: str) -> FusedEvidence:
    """Deserialize FusedEvidence from JSON string."""
    return FusedEvidence.model_validate_json(data)


# ── SemanticCache ─────────────────────────────────────────

class SemanticCache:
    """ChromaDB-backed semantic cache for FusedEvidence.

    - Vector index: ChromaDB collection ``semantic_cache`` (cosine similarity)
    - Evidence data: JSONL file ``semantic_cache/evidence.jsonl``
    - In-memory metadata: dict for TTL / LRU / hit tracking
    """

    def __init__(
        self,
        similarity_threshold: float = _SIMILARITY_THRESHOLD,
        ttl: int = _TTL,
        max_entries: int = _MAX_ENTRIES,
    ):
        self._similarity_threshold = similarity_threshold
        self._ttl = ttl
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # In-memory metadata: key → {timestamp, hit_count, query}
        self._meta: dict[str, dict[str, Any]] = {}

        # JSONL offset index: key → file byte offset for O(1) lookup
        self._jsonl_offsets: dict[str, int] = {}

        # ChromaDB collection (lazy init)
        self._collection = None
        self._embedding_fn = None

        # JSONL storage
        self._jsonl_path = _JSONL_FILE
        self._data_dir = _DATA_DIR

        # Stats
        self._hits = 0
        self._misses = 0

    # ── Lazy initialization ────────────────────────────────

    def _ensure_init(self):
        """Lazily initialize ChromaDB collection and JSONL storage."""
        if self._collection is not None:
            return

        for attempt in range(3):
            try:
                from app.rag.vectorstore import get_vector_store_manager
                mgr = get_vector_store_manager()
                self._embedding_fn = mgr.embeddings

                # Get or create a dedicated cache collection
                self._collection = mgr.client.get_or_create_collection(
                    name=_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                # 触发一次 count() 验证 HNSW 索引可读
                _count = self._collection.count()
                logger.info(
                    "Semantic cache collection '%s' initialized, existing entries=%d",
                    _COLLECTION_NAME, _count,
                )

                # Load metadata from JSONL
                self._data_dir.mkdir(parents=True, exist_ok=True)
                self._load_meta_from_jsonl()
                return

            except Exception as e:
                err_msg = str(e).lower()
                is_hnsw_corrupt = "hnsw" in err_msg or "segment reader" in err_msg
                if is_hnsw_corrupt:
                    # HNSW 索引损坏：删除损坏集合并重建（重试无意义）
                    logger.warning("Semantic cache HNSW index corrupted, deleting and rebuilding: %s", e)
                    try:
                        mgr.client.delete_collection(_COLLECTION_NAME)
                        logger.info("Deleted corrupted semantic_cache collection, will recreate on next attempt")
                    except Exception as del_err:
                        logger.warning("Failed to delete corrupted semantic_cache: %s", del_err)
                    # 清空 JSONL 避免孤儿数据
                    try:
                        if self._jsonl_path.exists():
                            self._jsonl_path.unlink()
                    except Exception:
                        pass
                    self._meta.clear()
                    self._jsonl_offsets.clear()
                    continue  # 立即重试创建新集合
                if attempt < 2:
                    logger.warning("Semantic cache init attempt %d failed: %s, retrying...", attempt + 1, e)
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("Semantic cache init failed after %d attempts, cache disabled: %s", attempt + 1, e)
                    self._collection = None

    async def _aensure_init(self):
        """Async lazy initialization wrapper; avoids blocking the event loop on retry waits."""
        if self._collection is not None:
            return

        for attempt in range(3):
            try:
                from app.rag.vectorstore import get_vector_store_manager
                mgr = await asyncio.to_thread(get_vector_store_manager)
                self._embedding_fn = mgr.embeddings
                self._collection = await asyncio.to_thread(
                    mgr.client.get_or_create_collection,
                    name=_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                existing_count = await asyncio.to_thread(self._collection.count)
                logger.info(
                    "Semantic cache collection '%s' initialized, existing entries=%d",
                    _COLLECTION_NAME, existing_count,
                )
                await asyncio.to_thread(self._data_dir.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(self._load_meta_from_jsonl)
                return
            except Exception as e:
                err_msg = str(e).lower()
                is_hnsw_corrupt = "hnsw" in err_msg or "segment reader" in err_msg
                if is_hnsw_corrupt:
                    logger.warning("Semantic cache HNSW index corrupted (async), deleting and rebuilding: %s", e)
                    try:
                        await asyncio.to_thread(mgr.client.delete_collection, _COLLECTION_NAME)
                        logger.info("Deleted corrupted semantic_cache collection (async)")
                    except Exception as del_err:
                        logger.warning("Failed to delete corrupted semantic_cache (async): %s", del_err)
                    try:
                        if self._jsonl_path.exists():
                            self._jsonl_path.unlink()
                    except Exception:
                        pass
                    self._meta.clear()
                    self._jsonl_offsets.clear()
                    continue
                if attempt < 2:
                    logger.warning("Semantic cache async init attempt %d failed: %s, retrying...", attempt + 1, e)
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("Semantic cache async init failed after %d attempts, cache disabled: %s", attempt + 1, e)
                    self._collection = None

    def _load_meta_from_jsonl(self):
        """Load metadata entries from JSONL file on startup.

        Since time.monotonic() resets on restart, we cannot trust stored
        monotonic timestamps. Instead, we use wall-clock `stored_at` from
        ChromaDB metadata to decide if entries are still valid.
        """
        if not self._jsonl_path.exists():
            return
        try:
            count = 0
            now_wall = time.time()
            with open(self._jsonl_path, "r", encoding="utf-8") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    key = entry.get("key", "")
                    query = entry.get("query", "")
                    if not key:
                        continue
                    # Use wall-clock stored_at if available, else treat as expired
                    stored_at = entry.get("stored_at", 0)
                    if stored_at and (now_wall - stored_at) < self._ttl:
                        self._meta[key] = {
                            "query": query,
                            "timestamp": time.monotonic(),  # Reset to current monotonic
                            "hit_count": entry.get("hit_count", 0),
                        }
                        self._jsonl_offsets[key] = pos
                        count += 1
            logger.info("Semantic cache loaded %d valid metadata entries from JSONL", count)
        except Exception as e:
            logger.warning("Failed to load semantic cache JSONL: %s", e)

    # ── Public API ─────────────────────────────────────────

    def lookup(self, query: str, collection_name: str = "", filter_sig: str = "") -> tuple[FusedEvidence | None, float]:
        """Look up a semantically similar cached result.

        Returns (fused_evidence, similarity_score).
        If no match above threshold, returns (None, 0.0).
        """
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None, 0.0

        self._ensure_init()
        if self._collection is None:
            return None, 0.0

        start = time.perf_counter()

        try:
            # Embed the query
            query_embedding = self._embedding_fn.embed_query(query)

            # Search ChromaDB for similar queries
            results = self._query_collection(query_embedding)

            if not results or not results["distances"] or not results["distances"][0]:
                self._misses += 1
                return None, 0.0

            # ChromaDB cosine distance → similarity = 1 - distance
            distance = results["distances"][0][0]
            similarity = 1.0 - distance

            if similarity < self._similarity_threshold:
                self._misses += 1
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.debug(
                    "Semantic cache miss: query='%s' best_sim=%.4f threshold=%.2f %.1fms",
                    query[:50], similarity, self._similarity_threshold, elapsed_ms,
                )
                return None, similarity

            # Found a match — verify same collection context
            match_id = results["ids"][0][0]
            match_meta = (results["metadatas"] or [[]])[0]
            match_meta = match_meta[0] if match_meta else {}
            # Verify collection context matches (avoid cross-collection hits)
            match_collection = match_meta.get("collection_name", "")
            if collection_name and match_collection and collection_name != match_collection:
                self._misses += 1
                return None, similarity
            with self._lock:
                meta = self._meta.get(match_id)
                if meta is None:
                    # Metadata missing (stale), treat as miss
                    self._misses += 1
                    return None, similarity

                if time.monotonic() - meta["timestamp"] > self._ttl:
                    # TTL expired, evict
                    self._evict(match_id)
                    self._misses += 1
                    return None, similarity

                # Update access time and hit count
                meta["timestamp"] = time.monotonic()
                meta["hit_count"] = meta.get("hit_count", 0) + 1

            # Load FusedEvidence from JSONL
            fused = self._load_evidence(match_id)
            if fused is None:
                self._misses += 1
                return None, similarity

            self._hits += 1
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Semantic cache HIT: query='%s' matched='%s' sim=%.4f hits=%d %.1fms",
                query[:50], meta["query"][:50], similarity, self._hits, elapsed_ms,
            )
            return fused, similarity

        except Exception as e:
            logger.warning("Semantic cache lookup error: %s", e)
            self._misses += 1
            return None, 0.0

    async def alookup(self, query: str, collection_name: str = "", filter_sig: str = "") -> tuple[FusedEvidence | None, float]:
        """Async lookup wrapper that avoids blocking initialization on the event loop."""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None, 0.0
        await self._aensure_init()
        if self._collection is None:
            return None, 0.0
        return await asyncio.to_thread(self.lookup, query, collection_name, filter_sig)

    def store(self, query: str, fused: FusedEvidence, collection_name: str = "", filter_sig: str = "") -> None:
        """Store a retrieval result in the semantic cache."""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return

        self._ensure_init()
        if self._collection is None:
            return

        try:
            key = _cache_key(query, collection_name, filter_sig)
            wall_now = time.time()
            query_embedding = self._embedding_fn.embed_query(query)

            # Check collection validity before upsert
            if not self._check_collection_alive():
                return

            with self._lock:
                # Evict if at capacity
                if len(self._meta) >= self._max_entries and key not in self._meta:
                    self._evict_oldest()

                # Store metadata
                self._meta[key] = {
                    "query": query,
                    "timestamp": time.monotonic(),
                    "hit_count": 0,
                    "stored_at": wall_now,
                }

                # Upsert into ChromaDB
                self._collection.upsert(
                    ids=[key],
                    embeddings=[query_embedding],
                    metadatas=[{"query": query, "stored_at": wall_now, "collection_name": collection_name}],
                )

                # Write evidence to JSONL (append)
                self._save_evidence(key, query, fused)

            logger.debug("Semantic cache STORE: query='%s' key=%s", query[:50], key)

        except Exception as e:
            logger.warning("Semantic cache store error: %s", e)

    async def astore(self, query: str, fused: FusedEvidence, collection_name: str = "", filter_sig: str = "") -> None:
        """Async store wrapper that avoids blocking initialization on the event loop."""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return
        await self._aensure_init()
        if self._collection is None:
            return
        await asyncio.to_thread(self.store, query, fused, collection_name, filter_sig)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(100 * self._hits / max(total, 1), 1),
            "entries": len(self._meta),
            "max_entries": self._max_entries,
        }

    # ── Internal ───────────────────────────────────────────

    def _is_stale_error(self, err: Exception) -> bool:
        """Check if an error indicates the collection was deleted/corrupted externally."""
        msg = str(err).lower()
        return "does not exist" in msg or "nothing found on disk" in msg

    def _reinit_if_stale(self, err: Exception) -> bool:
        """Attempt to reinitialize collection after a stale-reference error.

        Returns True if reinit succeeded (self._collection is now valid),
        False if cache remains disabled.
        """
        if not self._is_stale_error(err):
            return False
        logger.warning("Semantic cache collection stale, re-initializing: %s", err)
        self._collection = None
        self._ensure_init()
        return self._collection is not None

    def _query_collection(self, query_embedding: list[float]) -> dict:
        """Query the cache collection, auto-reinitializing if stale."""
        try:
            return self._collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["distances", "metadatas"],
            )
        except Exception as e:
            if self._reinit_if_stale(e):
                return self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=1,
                    include=["distances", "metadatas"],
                )
            raise

    def _check_collection_alive(self) -> bool:
        """Verify the collection is still accessible; reinit if stale.

        Returns True if collection is alive, False if cache is now disabled.
        """
        try:
            _ = self._collection.count()
            return True
        except Exception as e:
            return self._reinit_if_stale(e)

    def _load_evidence(self, key: str) -> FusedEvidence | None:
        """Load FusedEvidence for a given key from JSONL file.

        Uses an in-memory key→offset index for O(1) lookup instead of
        linear scan. Falls back to linear scan if index is stale.
        """
        # Fast path: use offset index
        offset = self._jsonl_offsets.get(key)
        if offset is not None:
            try:
                with open(self._jsonl_path, "r", encoding="utf-8") as f:
                    f.seek(offset)
                    line = f.readline().strip()
                    if line:
                        entry = json.loads(line)
                        if entry.get("key") == key and "evidence" in entry:
                            return _deserialize_evidence(entry["evidence"])
            except Exception:
                pass  # Fall through to linear scan

        # Slow path: linear scan (and rebuild offset index)
        if not self._jsonl_path.exists():
            return None
        try:
            found = None
            with open(self._jsonl_path, "r", encoding="utf-8") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    entry_key = entry.get("key", "")
                    # Track all offsets while scanning
                    if entry_key not in self._jsonl_offsets:
                        self._jsonl_offsets[entry_key] = pos
                    if entry_key == key and "evidence" in entry:
                        found = _deserialize_evidence(entry["evidence"])
            return found
        except Exception as e:
            logger.warning("Failed to load evidence for key=%s: %s", key, e)
            return None

    def _save_evidence(self, key: str, query: str, fused: FusedEvidence) -> None:
        """Append evidence entry to JSONL file. Must be called under _lock."""
        try:
            meta = self._meta.get(key, {})
            entry = {
                "key": key,
                "query": query,
                "stored_at": meta.get("stored_at", time.time()),
                "evidence": _serialize_evidence(fused),
            }
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                offset = f.tell()
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._jsonl_offsets[key] = offset
        except Exception as e:
            logger.warning("Failed to save evidence for key=%s: %s", key, e)

    def _evict(self, key: str) -> None:
        """Evict a single entry from cache."""
        self._meta.pop(key, None)
        try:
            if self._collection is not None:
                self._collection.delete(ids=[key])
        except Exception as e:
            logger.debug("Failed to delete cache entry from ChromaDB: %s", e)
        # Note: JSONL entries are not deleted (append-only); stale entries
        # are filtered by TTL at lookup time. Periodic compaction can be
        # added later if needed.

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently accessed) entry."""
        if not self._meta:
            return
        oldest_key = min(self._meta, key=lambda k: self._meta[k]["timestamp"])
        self._evict(oldest_key)

    def compact_jsonl(self) -> int:
        """Compact JSONL file by removing TTL-expired entries.

        Returns number of entries removed.
        """
        if not self._jsonl_path.exists():
            return 0

        now_monotonic = time.monotonic()
        kept: list[str] = []
        removed = 0

        try:
            with open(self._jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    key = entry.get("key", "")
                    meta = self._meta.get(key)
                    # Keep if metadata exists and not expired
                    if meta and (now_monotonic - meta["timestamp"] < self._ttl):
                        kept.append(line)
                    else:
                        removed += 1

            if removed > 0:
                with open(self._jsonl_path, "w", encoding="utf-8") as f:
                    for line in kept:
                        f.write(line + "\n")
                logger.info("Semantic cache JSONL compacted: removed=%d kept=%d", removed, len(kept))

        except Exception as e:
            logger.warning("Semantic cache JSONL compaction failed: %s", e)

        return removed


# ── Module-level singleton ────────────────────────────────

_semantic_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    """Get or create the global SemanticCache singleton."""
    global _semantic_cache
    if _semantic_cache is None:
        threshold = settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD
        _semantic_cache = SemanticCache(similarity_threshold=threshold)
    return _semantic_cache
