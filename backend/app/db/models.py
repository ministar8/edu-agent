from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    display_name = Column(String(100), default="")
    role = Column(String(20), default="student")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(200), default="新对话")
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False, default="")
    agent_name = Column(String(50), nullable=True)
    sources = Column(Text, nullable=True, default="[]")  # JSON list
    governance = Column(Text, nullable=True)  # JSON dict
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class KnowledgePointRegistry(Base):
    """知识点注册表 — 入库时从 heading_path 预构建，运行时直接引用 ID"""
    __tablename__ = "knowledge_point_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)          # 知识点名称（=KG节点名 或 heading末段）
    category = Column(String(50), nullable=False, index=True)       # 学科: data_structure / operating_system / ...
    chapter = Column(String(100), default="")                      # 所属章（章级记录时为空串）
    heading_path = Column(String(300), default="")                 # 完整标题路径
    difficulty = Column(Float, default=1.0)                         # 默认难度 1.0~2.0
    difficulty_source = Column(String(10), default="auto")           # auto / manual
    kg_node = Column(Boolean, default=False)                        # 是否在 Neo4j 中有对应节点
    source_file = Column(String(200), default="")                  # 来源文件
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("name", "category", name="uq_kp_name_category"),
        {"sqlite_autoincrement": True},
    )


class StudentKnowledgeState(Base):
    """学生知识点掌握状态 — 运行时追踪"""
    __tablename__ = "student_knowledge_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_point_registry.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)       # 冗余学科，加速查询
    mastery = Column(Float, default=0.0)                             # 掌握度估值 0~1
    confidence = Column(Float, default=0.0)                         # 系统对估值的确信度 0~1 (Wilson下界)
    interaction_count = Column(Integer, default=0)                  # 累计交互次数
    total_positive = Column(Integer, default=0)                     # 正向信号累计
    total_negative = Column(Integer, default=0)                     # 负向信号累计
    last_interaction_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # 遗忘衰减计算用
    source = Column(String(20), default="")                        # 最近来源: qa / quiz / grading
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # 同一学生对同一知识点只有一条记录
        {"sqlite_autoincrement": True},
    )


class QuestionRecord(Base):
    """题目记录 — 生成/模板题目持久化 + 批改追踪"""
    __tablename__ = "question_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_point_registry.id"), nullable=True)
    batch_id = Column(String(36), nullable=True)                    # uuid，同批次题目共享

    question_type = Column(String(20))                              # 选择/填空/简答/综合
    difficulty = Column(Float, default=1.0)                          # 1.0-2.0，与 KnowledgePointRegistry 一致
    stem = Column(Text, nullable=False)                             # 题干
    standard_answer = Column(Text)                                   # 标准答案
    explanation = Column(Text)                                      # 解析

    source = Column(String(20), default="generated")                # generated / template
    quality_score = Column(Float, nullable=True)                     # 出题质量自动评分 0-1

    user_answer = Column(Text, nullable=True)                       # 学生提交的答案
    grading_score = Column(Float, nullable=True)                     # 批改分数 0-100
    is_wrong = Column(Boolean, default=False)                        # 是否错题

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )
