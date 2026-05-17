"""
Vector Database Service using pgvector
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import KnowledgeChunk, KnowledgeSource
from app.config import settings
from typing import List, Optional, Dict, Any
import uuid


class VectorDatabaseService:
    """Service for vector operations with pgvector"""
    
    # 类级缓存，避免重复检测
    _pgvector_available_cache: Optional[bool] = None
    _engine_cache: Dict[str, Any] = {}
    
    def __init__(self, db: Session):
        self.db = db
        self.pgvector_available = self._check_pgvector_cached()
    
    @classmethod
    def _check_pgvector_cached(cls) -> bool:
        """Check if pgvector extension is available with caching"""
        if cls._pgvector_available_cache is not None:
            return cls._pgvector_available_cache
        
        from sqlalchemy import create_engine
        
        try:
            test_engine = create_engine(settings.DATABASE_URL)
            with test_engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            cls._pgvector_available_cache = True
            return True
        except Exception as e:
            logger = __import__('loguru').logger
            logger.warning(f"pgvector extension not available: {e}")
            logger.warning("Vector similarity search will be disabled")
            cls._pgvector_available_cache = False
            return False
        finally:
            if 'test_engine' in locals():
                test_engine.dispose()
    
    @classmethod
    def get_cached_engine(cls, db_url: str):
        """获取缓存的数据库引擎，避免重复创建"""
        if db_url not in cls._engine_cache:
            from sqlalchemy import create_engine
            cls._engine_cache[db_url] = create_engine(db_url)
        return cls._engine_cache[db_url]
    
    @classmethod
    def clear_engine_cache(cls):
        """清理引擎缓存（用于测试或重新配置）"""
        for engine in cls._engine_cache.values():
            engine.dispose()
        cls._engine_cache.clear()
    
    def create_embedding_table(self):
        """Create embedding table with pgvector extension"""
        if not self.pgvector_available:
            return
            
        # Create vector type and table (if not using ORM)
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks_vector (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    chunk_id UUID REFERENCES knowledge_chunks(id),
                    embedding vector(1024),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.commit()
        except Exception as e:
            logger = __import__('loguru').logger
            logger.warning(f"Failed to create vector table: {e}")
            self.pgvector_available = False
    
    def store_embedding(self, chunk_id: uuid.UUID, embedding: List[float]):
        """Store embedding vector for a chunk"""
        if not self.pgvector_available:
            return
            
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        try:
            # Use CAST to convert string to vector type
            self.db.execute(
                text("""
                    INSERT INTO knowledge_chunks_vector (chunk_id, embedding)
                    VALUES (:chunk_id, CAST(:embedding AS vector))
                    ON CONFLICT (chunk_id) DO UPDATE SET embedding = CAST(:embedding AS vector)
                """),
                {"chunk_id": chunk_id, "embedding": embedding_str}
            )
            self.db.commit()
        except Exception as e:
            logger = __import__('loguru').logger
            logger.error(f"Failed to store embedding: {e}")
            self.pgvector_available = False
    
    def store_batch_embeddings(self, chunk_ids: List[uuid.UUID], embeddings: List[List[float]]):
        """
        Batch store multiple embeddings in a single transaction
        
        注意：此方法不再 commit，由调用方统一 commit，避免双 commit 导致的不一致
        """
        if not self.pgvector_available or not chunk_ids:
            return
        
        try:
            params_list = []
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                params_list.append({
                    "chunk_id": chunk_id,
                    "embedding": embedding_str
                })
            
            # 批量插入，使用单次事务
            if params_list:
                self.db.execute(
                    text("""
                        INSERT INTO knowledge_chunks_vector (chunk_id, embedding)
                        VALUES (:chunk_id, CAST(:embedding AS vector))
                        ON CONFLICT (chunk_id) DO UPDATE SET embedding = CAST(:embedding AS vector)
                    """),
                    params_list
                )
                # 修复 vector_commit：移除内部 commit，由调用方统一 commit
                
        except Exception as e:
            logger = __import__('loguru').logger
            logger.error(f"Failed to store batch embeddings: {e}")
            self.pgvector_available = False
            raise
    
    def similarity_search(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        source_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity"""
        # Format embedding as array string for pgvector
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Build query
        query = text("""
            SELECT 
                kc.id,
                kc.content,
                kc.source_id,
                ks.title,
                ks.source_type,
                ks.source_url,
                ks.source_path,
                ks.file_name,
                kc.page_number,
                kc.section_title,
                kc.timestamp_start,
                kc.timestamp_end,
                kv.embedding <-> CAST(:embedding AS vector) AS similarity
            FROM knowledge_chunks kc
            JOIN knowledge_sources ks ON kc.source_id = ks.id
            JOIN knowledge_chunks_vector kv ON kc.id = kv.chunk_id
        """)
        
        params = {"embedding": embedding_str, "top_k": top_k}
        
        if source_type:
            query = text(str(query) + " WHERE ks.source_type = :source_type")
            params["source_type"] = source_type
        
        query = text(str(query) + " ORDER BY similarity ASC LIMIT :top_k")
        params["top_k"] = top_k
        
        result = self.db.execute(query, params)
        
        # 使用列表推导式分批处理结果，避免一次性加载大量数据
        batch_results = []
        batch_size = 100
        
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            batch_results.extend([
                {
                    "id": str(row.id),
                    "content": row.content,
                    "source_id": str(row.source_id),
                    "title": row.title,
                    "source_type": row.source_type,
                    "source_url": row.source_url,
                    "source_path": row.source_path,
                    "file_name": row.file_name,
                    "page_number": row.page_number,
                    "section_title": row.section_title,
                    "timestamp_start": row.timestamp_start,
                    "timestamp_end": row.timestamp_end,
                    "similarity": float(row.similarity)
                }
                for row in rows
            ])
        
        return batch_results
    
    def delete_source_embeddings(self, source_id: uuid.UUID):
        """Delete all embeddings for a source"""
        self.db.execute(
            text("DELETE FROM knowledge_chunks_vector WHERE chunk_id IN "
                 "(SELECT id FROM knowledge_chunks WHERE source_id = :source_id)"),
            {"source_id": source_id}
        )
        self.db.commit()
