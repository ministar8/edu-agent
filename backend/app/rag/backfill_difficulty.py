"""回填 KnowledgePointRegistry.difficulty — 从 heading_path 关键词推断难度

只更新 difficulty_source='auto' 且 heading_path 非空且匹配到关键词的记录。
跳过 heading_path 为空（手动创建）和 difficulty_source='manual' 的记录。

用法：
    python -m app.rag.backfill_difficulty
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)")
logger = logging.getLogger(__name__)


def main() -> None:
    from app.db.session import SessionLocal, init_db
    from app.db.models import KnowledgePointRegistry
    from app.rag.knowledge_tagger import infer_difficulty_from_heading

    init_db()

    db = SessionLocal()
    try:
        records = db.query(KnowledgePointRegistry).filter(
            KnowledgePointRegistry.difficulty_source == "auto",
            KnowledgePointRegistry.heading_path != "",
        ).all()

        updated = 0
        for rec in records:
            difficulty, matched = infer_difficulty_from_heading(rec.heading_path)
            if matched and rec.difficulty != difficulty:
                logger.info(
                    "  %s: %.1f → %.1f  (path=%s)",
                    rec.name, rec.difficulty, difficulty, rec.heading_path[:60],
                )
                rec.difficulty = difficulty
                updated += 1

        if updated > 0:
            db.commit()
            logger.info("Updated %d records", updated)
        else:
            logger.info("No records to update")

    except Exception as e:
        logger.error("Backfill failed: %s", e)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
