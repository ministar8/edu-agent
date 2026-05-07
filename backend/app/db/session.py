from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
