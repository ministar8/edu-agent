from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(settings.KNOWLEDGE_DIR).resolve().parent / "edu_agent.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db() -> None:
    from app.db.models import Base as ModelsBase

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ModelsBase.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "conversations" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("conversations")}
        if "summary" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN summary TEXT DEFAULT ''"))

    # ── knowledge_point_registry: 确保 (name, category) 唯一索引 ──
    if "knowledge_point_registry" in inspector.get_table_names():
        idx_names = {idx["name"] for idx in inspector.get_indexes("knowledge_point_registry")}
        if "ix_kp_name_category" not in idx_names:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_kp_name_category "
                    "ON knowledge_point_registry (name, category)"
                ))
        # 迁移：添加 difficulty_source 列
        kp_columns = {column["name"] for column in inspector.get_columns("knowledge_point_registry")}
        if "difficulty_source" not in kp_columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE knowledge_point_registry ADD COLUMN difficulty_source VARCHAR(10) DEFAULT 'auto'"
                ))

    # ── messages: 添加 parent_id + siblings_order 列（对话分支） ──
    if "messages" in inspector.get_table_names():
        msg_columns = {column["name"] for column in inspector.get_columns("messages")}
        if "parent_id" not in msg_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE messages ADD COLUMN parent_id INTEGER REFERENCES messages(id)"))
                conn.execute(text("ALTER TABLE messages ADD COLUMN siblings_order INTEGER DEFAULT 0"))
                # Backfill: set parent_id chain for existing linear conversations
                conn.execute(text("""
                    UPDATE messages SET parent_id = (
                        SELECT m2.id FROM messages m2
                        WHERE m2.conversation_id = messages.conversation_id
                          AND m2.id < messages.id
                        ORDER BY m2.id DESC LIMIT 1
                    )
                    WHERE parent_id IS NULL
                """))

    # ── student_knowledge_state: 确保 (user_id, knowledge_point_id) 唯一索引 ──
    if "student_knowledge_state" in inspector.get_table_names():
        idx_names = {idx["name"] for idx in inspector.get_indexes("student_knowledge_state")}
        if "ix_sks_user_kp" not in idx_names:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_sks_user_kp "
                    "ON student_knowledge_state (user_id, knowledge_point_id)"
                ))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
