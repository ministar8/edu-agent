"""Data flywheel: user feedback collection + bad case storage.

Phase 5 P1-1: logs user feedback (like/dislike) to rag_metrics.jsonl,
enabling periodic bad case clustering to drive improvements.

Usage:
  from app.rag.feedback import log_feedback
  log_feedback(query, answer, rating=1, metadata={})
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default feedback log path (relative to project root)
_FEEDBACK_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"
_FEEDBACK_FILE = _FEEDBACK_DIR / "rag_metrics.jsonl"


def log_feedback(
    query: str,
    answer: str,
    rating: int = 0,
    *,
    agent_name: str = "",
    collection: str = "",
    retrieval_depth: str = "",
    evidence_count: int = 0,
    confidence: float = 0.0,
    latency_ms: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log a single user feedback entry.

    Args:
        query: Original user query
        answer: System answer text (truncated to 2000 chars)
        rating: 1=thumbs-up, -1=thumbs-down, 0=neutral/no feedback
        agent_name: Which agent handled the query
        collection: Target collection(s)
        retrieval_depth: shallow/standard/deep/code
        evidence_count: Number of evidence items retrieved
        confidence: Governance confidence score
        latency_ms: Total response latency
        metadata: Extra context (user_id, thread_id, etc.)
    """
    if rating == 0:
        return  # Don't log neutral feedback

    try:
        _FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query[:500],
            "answer_preview": answer[:2000] if answer else "",
            "rating": rating,
            "agent_name": agent_name,
            "collection": collection,
            "retrieval_depth": retrieval_depth,
            "evidence_count": evidence_count,
            "confidence": confidence,
            "latency_ms": round(latency_ms, 1),
            "metadata": metadata or {},
        }

        with open(_FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.debug(
            "Feedback logged: rating=%d agent=%s query=%s",
            rating, agent_name, query[:50],
        )

    except Exception as e:
        logger.warning("Failed to log feedback: %s", e)


def get_feedback_stats(days: int = 7) -> dict:
    """Get feedback statistics for the last N days.

    Returns:
        {"total": N, "positive": N, "negative": N, "avg_confidence": float, ...}
    """
    if not _FEEDBACK_FILE.exists():
        return {"total": 0, "positive": 0, "negative": 0}

    cutoff = time.time() - days * 86400
    total = 0
    positive = 0
    negative = 0
    confidences: list[float] = []
    bad_cases: list[dict] = []

    try:
        with open(_FEEDBACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = entry.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt.timestamp() < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                total += 1
                rating = entry.get("rating", 0)
                if rating > 0:
                    positive += 1
                elif rating < 0:
                    negative += 1
                    bad_cases.append({
                        "query": entry.get("query", ""),
                        "agent": entry.get("agent_name", ""),
                        "depth": entry.get("retrieval_depth", ""),
                    })

                conf = entry.get("confidence", 0)
                if isinstance(conf, (int, float)):
                    confidences.append(float(conf))

        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "positive_ratio": round(positive / max(total, 1), 3),
            "avg_confidence": round(sum(confidences) / max(len(confidences), 1), 4) if confidences else 0,
            "bad_case_count": len(bad_cases),
            "bad_case_samples": bad_cases[:10],
        }
    except Exception as e:
        logger.warning("Failed to read feedback stats: %s", e)
        return {"total": 0, "positive": 0, "negative": 0, "error": str(e)}


def cluster_bad_cases(days: int = 30, top_n: int = 10) -> list[dict]:
    """Simple bad case clustering: group by query type + failure pattern.

    Returns list of {pattern, count, samples} sorted by count descending.
    """
    if not _FEEDBACK_FILE.exists():
        return []

    cutoff = time.time() - days * 86400
    bad_cases: list[dict] = []

    try:
        with open(_FEEDBACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("rating", 0) >= 0:
                    continue

                ts = entry.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt.timestamp() < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                bad_cases.append(entry)
    except Exception as e:
        logger.warning("Failed to cluster bad cases: %s", e)
        return []

    if not bad_cases:
        return []

    # Cluster by (agent, depth, empty_evidence)
    clusters: dict[str, dict] = {}
    for case in bad_cases:
        agent = case.get("agent_name", "unknown")
        depth = case.get("retrieval_depth", "unknown")
        has_evidence = case.get("evidence_count", 0) > 0
        key = f"{agent}|{depth}|{'has_ev' if has_evidence else 'no_ev'}"

        if key not in clusters:
            clusters[key] = {"pattern": key, "count": 0, "samples": []}
        clusters[key]["count"] += 1
        if len(clusters[key]["samples"]) < 3:
            clusters[key]["samples"].append(case.get("query", "")[:100])

    sorted_clusters = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)
    return sorted_clusters[:top_n]
