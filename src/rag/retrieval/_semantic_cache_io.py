"""语义缓存的 JSONL 证据读写（从 semantic_cache.py 拆出，行为等价）。

★ 以 mixin 形式拆出：方法以 `self.` 访问同一实例的 `_jsonl_path` / `_jsonl_offsets` /
  `_meta`；不回调其它实例方法，故可独立成 mixin。属性注解供类型检查用。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from rag.retrieval._semantic_cache_codec import _deserialize_evidence, _serialize_evidence
from rag.retrieval.evidence import FusedEvidence

logger = logging.getLogger(__name__)


class _EvidenceIoMixin:
    """JSONL 证据读写：快路径偏移索引 + 慢路径线性扫描。"""

    _jsonl_path: Path
    _jsonl_offsets: dict[str, int]
    _meta: dict[str, dict[str, Any]]

    def _read_evidence_at_offset(self, key: str, offset: int) -> FusedEvidence | None:
        """快路径：按偏移读取并解析；失败/不匹配返回 None（调用方退回线性扫描）。"""
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                f.seek(offset)
                line = f.readline().strip()
                if line:
                    entry = json.loads(line)
                    if entry.get("key") == key and "evidence" in entry:
                        return _deserialize_evidence(entry["evidence"])
        except Exception:  # noqa: S110 — 有意忽略：读偏移索引失败即退回线性扫描
            # 必须留痕（§2.2 规范 2：禁止无日志的 pass）。
            # 偏移索引若**持续**失效，每次 lookup 都会退化成线性扫描 ——
            # 这是**性能退化、不影响正确性**，所以用 DEBUG 而不是 WARNING；
            # 但完全不记的话，这个退化在日志里就彻底不可见。
            logger.debug("偏移索引读取失败，退回线性扫描 key=%s", key, exc_info=True)
        return None

    def _scan_evidence_jsonl(self, key: str) -> FusedEvidence | None:
        """慢路径：线性扫描 JSONL（并重建偏移索引），跳过损坏行。"""
        if not self._jsonl_path.exists():
            return None
        found = None
        corrupt = 0
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        # **单行损坏不能让整个扫描失败。**
                        # 坏行的现实来源：上次 append 写到一半进程被杀。
                        # 原实现让 json.loads 的异常冒到外层 except，于是**一条坏行
                        # 使所有未进偏移索引的键全部查不到** —— 缓存静默变空，
                        # 只表现为"重启后命中率变低"，没有任何错误可见。
                        # 跳过坏行、继续扫描，并在最后统一告警。
                        corrupt += 1
                        continue
                    entry_key = entry.get("key", "")
                    # 扫描时顺带登记偏移
                    if entry_key not in self._jsonl_offsets:
                        self._jsonl_offsets[entry_key] = pos
                    if entry_key == key and "evidence" in entry:
                        try:
                            found = _deserialize_evidence(entry["evidence"])
                        except Exception:
                            logger.warning("Semantic cache 条目反序列化失败 key=%s，已跳过", key)
        except Exception as e:
            logger.warning("Failed to load evidence for key=%s: %s", key, e)
            return None
        if corrupt:
            logger.warning("Semantic cache JSONL 有 %d 行损坏，已跳过", corrupt)
        return found

    def _load_evidence(self, key: str) -> FusedEvidence | None:
        """从 JSONL 文件按键加载 FusedEvidence。

        用内存里的 key→offset 索引做 O(1) 查找而非线性扫描；索引失效时退回线性扫描。
        """
        # 快路径：走偏移索引
        offset = self._jsonl_offsets.get(key)
        if offset is not None:
            found = self._read_evidence_at_offset(key, offset)
            if found is not None:
                return found
        # 慢路径：线性扫描（并重建偏移索引）
        return self._scan_evidence_jsonl(key)

    def _save_evidence(self, key: str, query: str, fused: FusedEvidence) -> None:
        """把证据条目追加到 JSONL 文件。必须在 `_lock` 持有下调用。"""
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
