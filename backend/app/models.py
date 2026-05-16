"""
Database Models
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid
import enum

Base = declarative_base()


class TaskStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportType(enum.Enum):
    WEB = "web"
    LOCAL_FILE = "local_file"
    VIDEO = "video"
    VIDEO_AUDIO = "video_audio"


class ImportStrategy(enum.Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    ADD_NEW = "add_new"


class LLMProvider(enum.Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    CUSTOM = "custom"


class KnowledgeSource(Base):
    """知识库源数据表"""
    __tablename__ = "knowledge_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA256 hash for deduplication
    source_type = Column(Enum(ImportType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    source_url = Column(String(2000), nullable=True)
    source_path = Column(String(2000), nullable=True)
    file_name = Column(String(500), nullable=True)
    
    # Metadata
    source_metadata = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    chunks = relationship("KnowledgeChunk", back_populates="source", cascade="all, delete-orphan")
    import_tasks = relationship("ImportTask", back_populates="knowledge_source")
    
    __table_args__ = (
        Index('idx_source_type_url', 'source_type', 'source_url'),
    )


class KnowledgeChunk(Base):
    """知识向量片段表"""
    __tablename__ = "knowledge_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    # Vector embedding (using pgvector)
    # Note: In actual implementation, you'll need to use pgvector's Vector type
    embedding = Column(Text, nullable=False)  # Store as string, convert to vector in code
    
    # Metadata for citation
    page_number = Column(Integer, nullable=True)
    section_title = Column(String(500), nullable=True)
    timestamp_start = Column(Float, nullable=True)  # For video/audio
    timestamp_end = Column(Float, nullable=True)  # For video/audio
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    source = relationship("KnowledgeSource", back_populates="chunks")
    
    __table_args__ = (
        Index('idx_source_chunk', 'source_id', 'chunk_index'),
    )


class ImportTask(Base):
    """导入任务表"""
    __tablename__ = "import_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name = Column(String(500), nullable=False)
    task_type = Column(Enum(ImportType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]), default=TaskStatus.PENDING, index=True)
    
    # Input parameters
    input_url = Column(String(2000), nullable=True)
    input_path = Column(String(2000), nullable=True)
    max_depth = Column(Integer, default=5)
    strategy = Column(Enum(ImportStrategy, values_callable=lambda x: [e.value for e in x]), default=ImportStrategy.SKIP)
    
    # Progress tracking
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    progress_percentage = Column(Float, default=0.0)
    
    # Results
    result_summary = Column(JSONB, default=dict)
    error_message = Column(Text, nullable=True)
    task_logs = Column(JSONB, default=list)  # Store task execution logs
    
    # Related knowledge source (if single source)
    knowledge_source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    knowledge_source = relationship("KnowledgeSource", back_populates="import_tasks")


class LLMModel(Base):
    """LLM 模型配置表"""
    __tablename__ = "llm_models"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(Enum(LLMProvider), nullable=False)
    model_name = Column(String(200), nullable=False)
    display_name = Column(String(500), nullable=False)
    
    # Configuration
    api_key = Column(String(500), nullable=True)  # Encrypted in production
    base_url = Column(String(500), nullable=True)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    
    # Settings
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    model_type = Column(String(50), default="chat")  # 'chat' or 'embedding'
    config_params = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ChatMessage(Base):
    """聊天消息表"""
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # Model used
    model_id = Column(UUID(as_uuid=True), ForeignKey("llm_models.id"), nullable=True)
    
    # Citations from knowledge base
    citations = Column(JSONB, default=list)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
    model = relationship("LLMModel")


class ConversationSession(Base):
    """对话会话表"""
    __tablename__ = "conversation_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=True)
    
    # Model used for this session
    model_id = Column(UUID(as_uuid=True), ForeignKey("llm_models.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    model = relationship("LLMModel")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    @property
    def session(self):
        return self
