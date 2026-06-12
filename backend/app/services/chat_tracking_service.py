from __future__ import annotations

import logging
import re

from app.events import TrackingEvent, emit, extract_kp_ids_from_docs, extract_kp_ids_from_steps

logger = logging.getLogger(__name__)


class ChatTrackingService:
    @staticmethod
    def build_document_qa_event(
        *,
        user_id: int,
        docs: list,
        governance: dict | None,
    ) -> TrackingEvent | None:
        kp_ids = extract_kp_ids_from_docs(docs)
        if not kp_ids:
            return None

        confidence = (governance or {}).get("confidence", "low")
        return TrackingEvent(
            event_type="qa_high_confidence" if confidence == "high" else "qa_low_confidence",
            user_id=user_id,
            knowledge_point_ids=kp_ids,
            category=(docs[0].metadata.get("category") or docs[0].collection or "") if docs else "",
            difficulty=1.0,
            outcome=1.0 if confidence == "high" else 0.3,
        )

    @staticmethod
    def build_multi_agent_event(
        *,
        user_id: int,
        current_agent: str,
        agent_steps: list[dict],
        governance: dict | None,
        final_answer: str,
    ) -> TrackingEvent | None:
        kp_ids = extract_kp_ids_from_steps(agent_steps)
        if not kp_ids or current_agent not in ("knowledge_agent", "grading_agent", "path_agent"):
            return None

        confidence = (governance or {}).get("confidence", "low")
        if current_agent == "grading_agent":
            event_type, outcome, difficulty = _grading_event_values(final_answer)
            kp_ids = _resolve_grading_kp_ids(final_answer, kp_ids)
        else:
            event_type = "qa_high_confidence" if confidence == "high" else "qa_low_confidence"
            outcome = 1.0 if confidence == "high" else 0.3
            difficulty = 1.0

        return TrackingEvent(
            event_type=event_type,
            user_id=user_id,
            knowledge_point_ids=kp_ids,
            category="",
            difficulty=difficulty,
            outcome=outcome,
        )

    @staticmethod
    async def emit_document_qa_event(
        *,
        user_id: int,
        docs: list,
        governance: dict | None,
        context: str,
    ) -> None:
        event = ChatTrackingService.build_document_qa_event(
            user_id=user_id,
            docs=docs,
            governance=governance,
        )
        if event is None:
            return
        try:
            await emit(event)
        except Exception as exc:
            logger.warning("Tracking event emission failed (%s): %s", context, exc)

    @staticmethod
    async def emit_multi_agent_event(
        *,
        user_id: int,
        current_agent: str,
        agent_steps: list[dict],
        governance: dict | None,
        final_answer: str,
    ) -> None:
        event = ChatTrackingService.build_multi_agent_event(
            user_id=user_id,
            current_agent=current_agent,
            agent_steps=agent_steps,
            governance=governance,
            final_answer=final_answer,
        )
        if event is None:
            return
        try:
            await emit(event)
        except Exception as exc:
            logger.warning("Tracking event emission failed (multi-agent): %s", exc)


def _grading_event_values(final_answer: str) -> tuple[str, float, float]:
    score_match = re.search(r"评分[：:]\s*(\d+)\s*/\s*100", final_answer)
    score = int(score_match.group(1)) if score_match else 50
    if score >= 80:
        event_type = "grading_excellent"
    elif score >= 50:
        event_type = "grading_pass"
    else:
        event_type = "grading_fail"
    outcome = score / 100.0

    difficulty_match = re.search(r"难度[：:]\s*(基础|理解|综合|创新)", final_answer)
    difficulty_map = {"基础": 1.0, "理解": 1.3, "综合": 1.6, "创新": 2.0}
    difficulty = difficulty_map.get(difficulty_match.group(1), 1.3) if difficulty_match else 1.3
    return event_type, outcome, difficulty


def _resolve_grading_kp_ids(final_answer: str, kp_ids: list[int]) -> list[int]:
    kp_match = re.search(r"知识点[：:]\s*(.+)", final_answer)
    if not kp_match or kp_ids:
        return kp_ids

    kp_name = kp_match.group(1).strip()
    try:
        from app.repositories.knowledge_registry_repository import KnowledgeRegistryRepository

        kp_id = KnowledgeRegistryRepository.find_id_by_name_with_managed_session(kp_name)
        if kp_id:
            return [kp_id]
    except Exception as exc:
        logger.debug("Knowledge point registry lookup skipped: %s", exc)
    return kp_ids
