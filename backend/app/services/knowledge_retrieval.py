"""
Knowledge Retrieval Service - Optimized with Safe Fallbacks
"""
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.vector_db import VectorDatabaseService
from app.services.text_embedding import TextEmbeddingService
from app.models import ImportType
from loguru import logger


class KnowledgeRetrievalService:
    """Service for retrieving knowledge with citations with safe fallback mechanisms"""
    
    # 类级别的缓存，避免每次初始化都请求数据库检查扩展
    _pgvector_checked: bool = False
    _pgvector_status: bool = False

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = TextEmbeddingService(db=db)  # 从数据库加载默认 embedding 模型配置
        self.vector_db = VectorDatabaseService(db)
    
    def _check_pgvector(self) -> bool:
        """Check if pgvector extension is available (Thread-safe-ish cached)"""
        if KnowledgeRetrievalService._pgvector_checked:
            return KnowledgeRetrievalService._pgvector_status
            
        try:
            result = self.db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                )
            """)).scalar()
            KnowledgeRetrievalService._pgvector_status = bool(result)
        except Exception as e:
            logger.warning(f"Error checking pgvector extension: {e}")
            KnowledgeRetrievalService._pgvector_status = False
        finally:
            KnowledgeRetrievalService._pgvector_checked = True
            
        return KnowledgeRetrievalService._pgvector_status
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_type: Optional[ImportType] = None
    ) -> List[Dict[str, Any]]:
        """Search knowledge base with safe pgvector checking"""
        if not self._check_pgvector():
            logger.warning("pgvector not available, using text-based search as fallback")
            return self._text_search(query, top_k, source_type)
        
        try:
            query_embedding = await self.embedding_service.generate_embedding(query, self.db)
            
            results = self.vector_db.similarity_search(
                query_embedding,
                top_k=top_k,
                source_type=source_type.value if source_type else None
            )
            
            formatted_results = []
            for result in results:
                # 统一上游接口返回的数据格式
                normalized_result = {
                    "source_id": str(result.get("source_id")),
                    "title": result.get("title", "Unknown"),
                    "source_type": result.get("source_type"),
                    "content": result.get("content", ""),
                    "similarity": result.get("similarity", 0.0),
                    "source_url": result.get("source_url"),
                    "file_name": result.get("file_name"),
                    "source_path": result.get("source_path"),
                    "page_number": result.get("page_number"),
                    "section_title": result.get("section_title"),
                    "timestamp_start": result.get("timestamp_start"),
                    "timestamp_end": result.get("timestamp_end"),
                }
                
                citation = self._format_citation(normalized_result)
                formatted_results.append({
                    "content": normalized_result["content"],
                    "similarity": normalized_result["similarity"],
                    "citation": citation
                })
            return formatted_results
            
        except Exception as e:
            logger.error(f"Vector search failed, attempting text fallback: {e}")
            return self._text_search(query, top_k, source_type)
    
    def _text_search(
        self,
        query: str,
        top_k: int = 5,
        source_type: Optional[ImportType] = None
    ) -> List[Dict[str, Any]]:
        """Fallback text-based search using simple LIKE matching"""
        
        # 使用简单的 LIKE 搜索，不依赖全文搜索索引
        sql_script = """
            SELECT 
                kc.id, kc.content, kc.source_id,
                ks.title, ks.source_type, ks.source_url, ks.source_path, ks.file_name,
                kc.page_number, kc.section_title, kc.timestamp_start, kc.timestamp_end,
                1.0 AS similarity
            FROM knowledge_chunks kc
            JOIN knowledge_sources ks ON kc.source_id = ks.id
            WHERE kc.content ILIKE :query_pattern
        """
        
        params: Dict[str, Any] = {
            "query_pattern": f"%{query}%",
            "top_k": top_k
        }
        
        if source_type:
            sql_script += " AND ks.source_type = :source_type"
            params["source_type"] = source_type.value
            
        sql_script += " ORDER BY kc.created_at DESC LIMIT :top_k"
        
        try:
            result = self.db.execute(text(sql_script), params)
            
            # 使用 fetchmany() 分批获取结果，避免一次性加载大量数据到内存
            batch_size = 100
            formatted_results = []
            
            while True:
                rows = result.fetchmany(batch_size)
                if not rows:
                    break
                    
                for row in rows:
                    normalized_result = {
                        "source_id": str(row.source_id),
                        "title": row.title,
                        "source_type": row.source_type,
                        "content": row.content,
                        "source_url": row.source_url,
                        "file_name": row.file_name,
                        "source_path": row.source_path,
                        "page_number": row.page_number,
                    "section_title": row.section_title,
                    "timestamp_start": row.timestamp_start,
                    "timestamp_end": row.timestamp_end,
                }
                
                citation = self._format_citation(normalized_result)
                formatted_results.append({
                    "content": row.content,
                    "similarity": float(row.similarity) if row.similarity else 0.0,
                    "citation": citation
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Text fallback search completely failed: {e}")
            return []
    
    def _format_citation(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format citation information with type safety"""
        # 兼容处理：确保比较时都是 string 类型
        current_type = str(result["source_type"])
        
        citation = {
            "source_id": result["source_id"],
            "title": result["title"],
            "source_type": current_type
        }
        
        if current_type == ImportType.WEB.value:
            citation["url"] = result.get("source_url")
            citation["access_date"] = None 
        
        elif current_type == ImportType.LOCAL_FILE.value:
            citation.update({
                "file_name": result.get("file_name"),
                "file_path": result.get("source_path"),
                "page_number": result.get("page_number"),
                "section": result.get("section_title")
            })
        
        elif current_type == ImportType.VIDEO.value:
            citation.update({
                "video_title": result["title"],
                "timestamp_start": result.get("timestamp_start"),
                "timestamp_end": result.get("timestamp_end")
            })
            
            if result.get("timestamp_start") is not None:
                try:
                    start_seconds = int(float(result["timestamp_start"]))
                    citation["timestamp_formatted"] = (
                        f"{start_seconds // 3600:02d}:"
                        f"{(start_seconds % 3600) // 60:02d}:"
                        f"{start_seconds % 60:02d}"
                    )
                except (ValueError, TypeError):
                    citation["timestamp_formatted"] = "00:00:00"
        
        return citation
    
    async def search_with_context(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Search and return formatted contexts for LLMs"""
        results = await self.search(query, top_k)
        
        context_parts = []
        citations = []
        
        for idx, result in enumerate(results, 1):
            context_parts.append(f"[{idx}] {result['content']}")
            citations.append(result["citation"])
            
        return {
            "results": results,
            "context": "\n\n".join(context_parts),
            "citations": citations,
            "query": query
        }