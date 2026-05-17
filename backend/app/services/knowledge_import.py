"""
Knowledge Import Service - Core import logic with deduplication (Thread-safe & Optimized)
"""
import os
import asyncio
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.models import (
    KnowledgeSource, KnowledgeChunk, ImportTask,
    ImportType, TaskStatus, ImportStrategy
)
from app.vector_db import VectorDatabaseService
from app.services.text_embedding import TextEmbeddingService, TextChunker, ContentHasher
from app.tools.web_scraper import WebScraper
from app.tools.video_downloader import VideoDownloader
from app.tools.audio_transcriber import AudioTranscriber
from app.tools.document_parser import DocumentParser


class KnowledgeImportService:
    """Service for importing knowledge with deduplication and task tracking"""
    
    # Shared thread pool for database and synchronous intensive operations
    _executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="db_worker")
    
    # 优化 3：使用线程安全的取消标志，避免反复创建事件循环
    _cancel_flags: Dict[uuid.UUID, bool] = {}
    
    # 优化 6：视频导入并发控制 semaphore（只允许 1 个视频任务同时运行）
    _video_import_semaphore: Optional[asyncio.Semaphore] = None
    
    # 内存监控阈值
    MAX_MEMORY_PERCENT = 85.0  # 内存使用率超过 85% 时告警
    MAX_EMBEDDING_BATCH_SIZE = 32  # 限制批量 embedding 的最大数量
    
    @staticmethod
    def check_memory_usage():
        """检查当前内存使用情况，超过阈值时记录警告日志"""
        try:
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_info().rss / psutil.virtual_memory().total * 100
            
            if memory_percent > KnowledgeImportService.MAX_MEMORY_PERCENT:
                logger.warning(f"High memory usage detected: {memory_percent:.1f}%")
                return memory_percent
            
            return memory_percent
        except Exception as e:
            # psutil 可能未安装，忽略错误
            pass
        return 0.0
    
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = TextEmbeddingService(db=db)  # 从数据库加载默认 embedding 模型配置
        self.chunker = TextChunker()
        self.vector_db = VectorDatabaseService(db)
        self.document_parser = DocumentParser()
    
    async def run_in_executor(self, func, *args, **kwargs):
        """Run synchronous function in thread pool to avoid blocking event loop"""
        loop = asyncio.get_running_loop()
        # Use partial to support keyword arguments in executor
        from functools import partial
        return await loop.run_in_executor(self._executor, partial(func, *args, **kwargs))
    
    def _check_duplicate_sync(
        self,
        content_hash: str,
        source_type: ImportType,
        source_url: str = None,
        source_path: str = None
    ) -> Optional[KnowledgeSource]:
        """Synchronous implementation of checking duplicate"""
        query = self.db.query(KnowledgeSource).filter(
            KnowledgeSource.content_hash == content_hash
        )
        
        # 修复 video_p1：支持 VIDEO + source_path 组合
        if source_type == ImportType.LOCAL_FILE and source_path:
            query = query.filter(KnowledgeSource.source_path == source_path)
        elif source_type == ImportType.VIDEO and source_path:
            # 本地视频：按 source_path 过滤
            query = query.filter(KnowledgeSource.source_path == source_path)
        elif source_url:
            # URL 视频或网页：按 source_url 过滤
            query = query.filter(KnowledgeSource.source_url == source_url)
        
        return query.first()

    async def check_duplicate(self, *args, **kwargs) -> Optional[KnowledgeSource]:
        """Asynchronous wrapper for check_duplicate"""
        return await self.run_in_executor(self._check_duplicate_sync, *args, **kwargs)
    
    def _create_import_task_sync(
        self,
        task_name: str,
        task_type: ImportType,
        input_url: str = None,
        input_path: str = None,
        max_depth: int = 5,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> ImportTask:
        task = ImportTask(
            task_name=task_name,
            task_type=task_type,
            input_url=input_url,
            input_path=input_path,
            max_depth=max_depth,
            strategy=strategy,
            status=TaskStatus.PENDING
        )
        try:
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
            return task
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create import task: {e}")
            raise e

    async def create_import_task(self, *args, **kwargs) -> ImportTask:
        """Create a new import task asynchronously"""
        return await self.run_in_executor(self._create_import_task_sync, *args, **kwargs)
    
    def _add_task_log_sync(self, task_id: uuid.UUID, message: str, level: str = "info", detail: dict = None, commit: bool = True):
        task = self.db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if not task:
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        }
        if detail:
            log_entry["detail"] = detail
        
        if task.task_logs is None:
            task.task_logs = []
        
        # SQLAlchemy mutation tracking helper (re-assign to trigger track if JSON type)
        current_logs = list(task.task_logs)
        current_logs.append(log_entry)
        task.task_logs = current_logs
        
        if commit:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to commit task log: {e}")

    async def add_task_log(self, *args, **kwargs):
        """Add a log entry to task asynchronously"""
        return await self.run_in_executor(self._add_task_log_sync, *args, **kwargs)
    
    def _update_task_progress_sync(
        self,
        task_id: uuid.UUID,
        status: TaskStatus = None,
        total_items: int = None,
        processed: int = None,
        processed_items: int = None,
        failed: int = None,
        error_message: str = None,
        log_message: str = None,
        log_level: str = "info",
        commit: bool = True
    ):
        task = self.db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if not task:
            return
        
        if status:
            task.status = status
            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.now()
                self._add_task_log_sync(task_id, f"任务开始执行", "info", {
                    "task_name": task.task_name,
                    "task_type": task.task_type.value,
                    "input_url": task.input_url,
                    "input_path": task.input_path
                }, commit=False)
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.completed_at = datetime.now()
                if status == TaskStatus.COMPLETED:
                    self._add_task_log_sync(task_id, f"任务执行完成", "success", {
                        "imported": task.processed_items,
                        "total": task.total_items
                    }, commit=False)
                elif status == TaskStatus.FAILED:
                    self._add_task_log_sync(task_id, f"任务执行失败", "error", {
                        "error": error_message
                    }, commit=False)
                elif status == TaskStatus.CANCELLED:
                    self._add_task_log_sync(task_id, f"任务已取消", "warning", commit=False)
        
        if total_items is not None:
            task.total_items = total_items
            self._add_task_log_sync(task_id, f"发现 {total_items} 个待处理项目", "info", commit=False)
        
        if processed is not None:
            task.processed_items = processed
        elif processed_items is not None:
            task.processed_items = processed_items
        
        if failed is not None:
            task.failed_items = failed  # Fixed: aligned to failed_items attribute name
        
        if error_message:
            task.error_message = error_message
        
        if task.total_items and task.total_items > 0 and task.processed_items is not None:
            task.progress_percentage = (task.processed_items / task.total_items) * 100
        
        if log_message:
            self._add_task_log_sync(task_id, log_message, log_level, commit=False)
        
        if commit:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to commit task progress: {e}")

    async def update_task_progress(self, *args, **kwargs):
        """Update task progress asynchronously"""
        return await self.run_in_executor(self._update_task_progress_sync, *args, **kwargs)
    
    def _check_task_cancelled_sync(self, task_id: uuid.UUID) -> bool:
        """Check if task has been cancelled (synchronous version)"""
        task = self.db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if not task:
            return False
        return task.status == TaskStatus.CANCELLED
    
    def set_task_cancelled(self, task_id: uuid.UUID, cancelled: bool = True):
        """优化 3：线程安全的取消标志设置，避免反复创建事件循环"""
        self._cancel_flags[task_id] = cancelled
    
    def is_task_cancelled(self, task_id: uuid.UUID) -> bool:
        """优化 3：快速检查取消标志，无需数据库查询"""
        return self._cancel_flags.get(task_id, False)
    
    async def check_task_cancelled(self, task_id: uuid.UUID) -> bool:
        """Check if task has been cancelled asynchronously"""
        # 优先检查内存标志（快速路径）
        if self.is_task_cancelled(task_id):
            return True
        # 后备：检查数据库状态
        return await self.run_in_executor(self._check_task_cancelled_sync, task_id)
    
    def _delete_existing_source_sync(self, existing_id):
        """Helper to cleanly delete a duplicate source and its embeddings"""
        try:
            self.vector_db.delete_source_embeddings(existing_id)
            existing = self.db.query(KnowledgeSource).filter(KnowledgeSource.id == existing_id).first()
            if existing:
                self.db.delete(existing)
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def _save_knowledge_source_and_chunks_sync(self, source_data: dict, chunks_data: List[dict]) -> int:
        """Helper to synchronously save source and chunks in a batch transaction"""
        try:
            source = KnowledgeSource(**source_data)
            self.db.add(source)
            self.db.flush()
            
            chunk_objects = []
            embedding_vectors = []
            
            for chunk_data in chunks_data:
                # 优化 video_embedding：统一 embedding 字符串格式
                embedding = chunk_data["embedding"]
                embedding_str = str(embedding) if isinstance(embedding, list) else embedding
                
                chunk = KnowledgeChunk(
                    source_id=source.id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    embedding=embedding_str,
                    timestamp_start=chunk_data.get("timestamp_start"),
                    timestamp_end=chunk_data.get("timestamp_end")
                )
                chunk_objects.append(chunk)
                embedding_vectors.append(embedding)
                
            self.db.add_all(chunk_objects)
            self.db.flush()  # 只 flush 不 commit，获取 chunk IDs
            
            # 批量存储向量 embeddings
            chunk_ids = [chunk.id for chunk in chunk_objects]
            self.vector_db.store_batch_embeddings(chunk_ids, embedding_vectors)
            
            # 修复 vector_commit：统一 commit，确保 ORM 和向量表原子性
            self.db.commit()
                
            return len(chunk_objects)
        except Exception as e:
            self.db.rollback()
            raise e
    
    def _create_knowledge_source_sync(self, source_data: dict) -> KnowledgeSource:
        """优化 4：单独创建源记录的辅助方法"""
        try:
            source = KnowledgeSource(**source_data)
            self.db.add(source)
            self.db.commit()
            self.db.refresh(source)
            return source
        except Exception as e:
            self.db.rollback()
            raise e
    
    def _save_chunks_for_source_sync(self, source_id: uuid.UUID, chunks_data: List[dict]):
        """优化 4：增量保存 chunks 到已存在的源"""
        try:
            # 批量插入 chunks
            chunk_objects = []
            for chunk_data in chunks_data:
                # 优化 fix_3 & video_embedding：创建 chunk 时就设置 embedding 字段，统一格式
                embedding = chunk_data.get("embedding", "")
                embedding_str = str(embedding) if isinstance(embedding, list) else embedding
                
                chunk = KnowledgeChunk(
                    source_id=source_id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    embedding=embedding_str,  # 设置 embedding 字段
                    timestamp_start=chunk_data.get("timestamp_start"),
                    timestamp_end=chunk_data.get("timestamp_end")
                )
                chunk_objects.append(chunk)
                self.db.add(chunk)
            
            # 修复 video_chunk_id：flush 后才生成 chunk.id
            self.db.flush()
            
            # 修复 video_chunk_id：flush 后收集 chunk_ids
            chunk_ids = [chunk.id for chunk in chunk_objects]
            
            # 优化 5 & video_1：批量存储 embeddings（使用正确的 SQLAlchemy 用法）
            if self.vector_db.pgvector_available:
                embeddings = []
                valid_chunk_ids = []
                for chunk_data, chunk_id in zip(chunks_data, chunk_ids):
                    if "embedding" in chunk_data and chunk_data["embedding"] is not None:
                        embeddings.append(chunk_data["embedding"])
                        valid_chunk_ids.append(chunk_id)
                
                if embeddings:
                    # 使用 store_batch_embeddings 批量写入
                    self.vector_db.store_batch_embeddings(valid_chunk_ids, embeddings)
                    # 修复 vector_commit：统一 commit，确保 ORM 和向量表原子性
                    self.db.commit()
            else:
                # 无 pgvector 时也需要 commit
                self.db.commit()
            # 注意：embedding 字段已在创建 chunk 时设置，无需降级处理
        except Exception as e:
            self.db.rollback()
            raise e

    async def import_web_content(
        self,
        task_id: uuid.UUID,
        url: str,
        max_depth: int = 5,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> Dict:
        """Import knowledge from web pages using producer-consumer pattern"""
        try:
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING)
            await self.add_task_log(task_id, f"开始爬取网页：{url}", "info", {"max_depth": max_depth})
            
            scraper = WebScraper(max_depth=max_depth, max_pages=100)
            
            imported_count = 0
            skipped_count = 0
            updated_count = 0
            page_index = 0
            estimated_total = 100
            
            # 进度和日志缓冲
            log_buffer = []
            progress_update_count = 0
            MAX_LOG_BUFFER = 20  # 只保留最近 20 条日志
            
            # 优化 web_lock：添加 asyncio.Lock 保护共享计数器
            counter_lock = asyncio.Lock()
            
            # 设置初始总项数
            await self.update_task_progress(task_id, total_items=estimated_total, processed_items=0)
            
            # 修复 RC-3：爬取开始时立即设置任务状态为 RUNNING，避免长时间显示 PENDING
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING, processed_items=0)
            
            # 内存中的取消标志，避免频繁查库
            # 已移除：cancel_flag = False（冗余，使用 web_cancelled 代替）
            
            # 修复 web_cancel_flag：添加任务级取消标志
            web_cancelled = False
            
            # 优化 web_3：每 worker 独立 Session，避免并发安全问题
            from app.database import get_db_session_factory
            
            # 创建 Session 工厂
            SessionLocal = get_db_session_factory()
            
            async def process_page(page: Dict) -> None:
                nonlocal imported_count, skipped_count, updated_count, page_index, log_buffer, progress_update_count, web_cancelled
                
                # 创建当前 worker 的独立 Session（更稳妥的写法）
                worker_db = SessionLocal()
                try:
                    # 创建临时的 service 实例用于当前 worker
                    worker_service = KnowledgeImportService(worker_db)
                    
                    # 优化 web_1：每页都检查取消标志（使用 worker_service 的 check_task_cancelled）
                    if await worker_service.check_task_cancelled(task_id):
                        logger.info(f"Task {task_id} cancelled, stopping import")
                        async with counter_lock:
                            web_cancelled = True  # 设置任务级取消标志
                            await self.update_task_progress(task_id, status=TaskStatus.CANCELLED, processed_items=page_index)
                        # 修复 web_cancel_flag：设置标志并返回
                        return
                    
                    try:
                        # 检查重复
                        content_hash = await worker_service.run_in_executor(ContentHasher.generate_hash, page["content"])
                        existing = await worker_service.check_duplicate(content_hash, ImportType.WEB, source_url=page["url"])
                        
                        if existing:
                            if strategy == ImportStrategy.SKIP:
                                # 修复 RC-2：跳过重复页也要更新进度
                                async with counter_lock:
                                    skipped_count += 1
                                    page_index += 1
                                    
                                    # 每页都更新进度（使用独立 Session，避免并发问题）
                                    await worker_service.update_task_progress(task_id, processed_items=page_index, commit=True)
                                
                                async with counter_lock:
                                    if skipped_count % 10 == 1:
                                        log_msg = f"跳过重复页面 (已跳过 {skipped_count} 个)"
                                        log_buffer.append((log_msg, "warning", {"skipped": skipped_count}))
                                        if len(log_buffer) > MAX_LOG_BUFFER:
                                            log_buffer.pop(0)
                                return
                            elif strategy == ImportStrategy.OVERWRITE:
                                # 优化 fix_4：使用 worker_service 的 Session 删除数据
                                await worker_service.run_in_executor(worker_service._delete_existing_source_sync, existing.id)
                                async with counter_lock:
                                    updated_count += 1
                                    if updated_count % 10 == 1:
                                        log_msg = f"更新已有内容 (已更新 {updated_count} 个)"
                                        log_buffer.append((log_msg, "info", {"updated": updated_count}))
                                        if len(log_buffer) > MAX_LOG_BUFFER:
                                            log_buffer.pop(0)
                            elif strategy == ImportStrategy.ADD_NEW:
                                async with counter_lock:
                                    if updated_count % 10 == 1:
                                        log_msg = f"添加重复内容 (已添加 {updated_count} 个)"
                                        log_buffer.append((log_msg, "info", {"added": updated_count}))
                                        if len(log_buffer) > MAX_LOG_BUFFER:
                                            log_buffer.pop(0)
                            else:
                                async with counter_lock:
                                    skipped_count += 1
                                    page_index += 1
                                return
                        
                        # 分块处理
                        chunks = await worker_service.run_in_executor(
                            worker_service.chunker.chunk_document,
                            text=page["content"], title=page["title"], source_type="web", source_url=page["url"]
                        )
                        
                        # 内存检查
                        worker_service.check_memory_usage()
                        
                        # 批量生成 embeddings - 使用最大批量 32
                        batch_size = self.MAX_EMBEDDING_BATCH_SIZE
                        all_chunks_data = []
                        
                        for batch_idx in range(0, len(chunks), batch_size):
                            batch_chunks = chunks[batch_idx:batch_idx + batch_size]
                            batch_texts = [chunk["content"] for chunk in batch_chunks]
                            
                            # 批量生成 embeddings
                            batch_embeddings = await worker_service.embedding_service.generate_batch_embeddings(batch_texts, worker_db)
                            
                            for chunk_data, embedding in zip(batch_chunks, batch_embeddings):
                                chunk_data["source_type"] = ImportType.WEB
                                chunk_data["source_url"] = page["url"]
                                chunk_data["embedding"] = embedding
                                all_chunks_data.append(chunk_data)
                        
                        if all_chunks_data:
                            # 准备源数据
                            source_data = {
                                "title": page["title"],
                                "content_hash": content_hash,
                                "source_type": ImportType.WEB,
                                "source_url": page["url"],
                                "source_metadata": {"description": page["description"]}
                            }
                            
                            # 保存源和 chunks
                            await worker_service.run_in_executor(worker_service._save_knowledge_source_and_chunks_sync, source_data, all_chunks_data)
                            async with counter_lock:
                                imported_count += 1
                                
                                # 每 10 条记录一次日志
                                if imported_count % 10 == 1:
                                    log_msg = f"成功导入：{page['title']}"
                                    log_buffer.append((log_msg, "success", {"url": page["url"], "chunks": len(chunks)}))
                                    if len(log_buffer) > MAX_LOG_BUFFER:
                                        log_buffer.pop(0)
                        
                        async with counter_lock:
                            page_index += 1
                            
                            # 修复 RC-1：每页都更新进度，不再等待 10 页
                            # 使用 worker_service 的独立 Session，避免并发问题（RC-5）
                            await worker_service.update_task_progress(task_id, processed_items=page_index, commit=True)
                            
                            # 日志仍然批量写入，减少数据库压力
                            if imported_count % 10 == 1 or skipped_count % 10 == 1 or updated_count % 10 == 1:
                                log_msg = f"已处理 {page_index} 页"
                                log_buffer.append((log_msg, "info", {"page": page_index}))
                                if len(log_buffer) > MAX_LOG_BUFFER:
                                    log_buffer.pop(0)
                    
                    except Exception as e:
                        logger.error(f"Error processing page {page.get('url', 'unknown')}: {e}")
                        # 修复 page_index_lock：失败时 page_index 也要加锁
                        async with counter_lock:
                            page_index += 1
                
                finally:
                    # 清理 worker Session
                    worker_db.close()
            
            # 使用生产者 - 消费者模式爬取，传入取消检查回调
            processed_count = await scraper.crawl_site_producer_consumer(
                url, process_page, num_workers=3,
                cancel_check_callback=lambda: web_cancelled or self.is_task_cancelled(task_id)
            )
            
            # 最终更新进度和日志
            await self.update_task_progress(task_id, total_items=page_index, processed_items=page_index)
            
            # 写入剩余的日志
            if log_buffer:
                for msg, level, meta in log_buffer:
                    await self.add_task_log(task_id, msg, level, meta)
            
            # 修复 web_cancel_flag：检查取消标志并返回正确状态
            if web_cancelled or await self.check_task_cancelled(task_id):
                await self.add_task_log(task_id, "任务已取消", "warning")
                return {
                    "success": False,
                    "cancelled": True,
                    "imported": imported_count,
                    "skipped": skipped_count,
                    "updated": updated_count,
                    "total_pages": page_index
                }
            
            await self.add_task_log(task_id, f"爬取和处理完成", "success", {
                "imported": imported_count,
                "skipped": skipped_count,
                "updated": updated_count
            })
            
            return {
                "success": True,
                "imported": imported_count,
                "skipped": skipped_count,
                "updated": updated_count,
                "total_pages": page_index
            }
            
        except asyncio.CancelledError:
            await self.update_task_progress(task_id, status=TaskStatus.CANCELLED)
            await self.add_task_log(task_id, "任务已取消", "warning")
            raise
        except Exception as e:
            await self.update_task_progress(task_id, status=TaskStatus.FAILED)
            await self.add_task_log(task_id, f"任务失败：{str(e)}", "error")
            raise
    
    async def import_local_files(
        self,
        task_id: uuid.UUID,
        directory_path: str,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> Dict:
        """Import knowledge from local files using parallel processing"""
        try:
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING)
            
            # 优化 1：一次 rglob 过滤所有扩展名
            supported_extensions = {'.txt', '.md', '.rst', '.pdf', '.docx'}  # 移除.doc，避免错误
            path = Path(directory_path)
            files = []
            
            if path.is_file() and path.suffix.lower() in supported_extensions:
                files = [path]
            elif path.is_dir():
                # 优化 2：只遍历一次目录树
                for file_path in path.rglob('*'):
                    if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                        files.append(file_path)
            
            await self.update_task_progress(task_id, total_items=len(files), processed_items=0)
            
            imported_count = 0
            skipped_count = 0
            updated_count = 0
            cancelled = False
            
            # 优化 text_session：每文件独立 Session，与网页导入一致
            from app.database import get_db_session_factory
            SessionLocal = get_db_session_factory()
            
            # 优化 text_progress：添加锁保护进度计数
            progress_lock = asyncio.Lock()
            completed_count = 0
            
            # 优化 3：多文件并行处理（Semaphore 控制并发数）
            max_concurrent_files = 3  # 同时处理 3 个文件
            semaphore = asyncio.Semaphore(max_concurrent_files)
            
            async def process_file(file_path: Path, idx: int) -> dict:
                async with semaphore:
                    # 为每个文件创建独立 Session
                    file_db = SessionLocal()
                    try:
                        file_service = KnowledgeImportService(file_db)
                        result = await file_service._process_single_file(
                            task_id, file_path, strategy, idx
                        )
                        
                        # 优化 text_progress：使用锁更新进度计数
                        async with progress_lock:
                            nonlocal completed_count
                            completed_count += 1
                            # 使用 completed_count 而非 idx，确保单调递增
                            await self.update_task_progress(
                                task_id, processed_items=completed_count, commit=False
                            )
                        
                        # 优化 text_cancel：检查是否被取消
                        if result.get('cancelled'):
                            nonlocal cancelled
                            cancelled = True
                        
                        return result
                    finally:
                        # 清理文件 Session
                        file_db.close()
            
            # 创建所有文件的处理任务
            tasks = [
                process_file(file_path, idx)
                for idx, file_path in enumerate(files)
            ]
            
            # 并发执行所有任务
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            for result in results:
                if isinstance(result, dict):
                    if result.get('success') and not result.get('cancelled'):
                        imported_count += result.get('imported', 0)
                        skipped_count += result.get('skipped', 0)
                        updated_count += result.get('updated', 0)
                    elif result.get('cancelled'):
                        cancelled = True
                    elif result.get('error'):
                        logger.error(f"File processing failed: {result['error']}")
            
            # 优化 text_cancel：根据取消标志设置状态
            if cancelled:
                await self.update_task_progress(task_id, status=TaskStatus.CANCELLED)
                return {
                    "success": False,
                    "cancelled": True,
                    "imported": imported_count,
                    "skipped": skipped_count,
                    "updated": updated_count,
                    "total": len(files)
                }
            
            await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
            return {
                "success": True,
                "imported": imported_count,
                "skipped": skipped_count,
                "updated": updated_count,
                "total": len(files)
            }
        
        except Exception as e:
            logger.error(f"Local file import failed: {e}")
            await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=str(e))
            return {"success": False, "error": str(e)}
    
    async def _process_single_file(
        self,
        task_id: uuid.UUID,
        file_path: Path,
        strategy: ImportStrategy,
        idx: int
    ) -> dict:
        """
        处理单个文件的辅助方法
        
        注意：此方法现在由每文件的独立 KnowledgeImportService 实例调用，
        使用独立的 Session，避免并发问题。
        
        修复 text_idx_progress：此方法不再更新进度，由父级统一更新
        """
        try:
            # 检查任务取消
            if await self.check_task_cancelled(task_id):
                logger.info(f"Task {task_id} cancelled, stopping import")
                # 修复 text_idx_progress：不再更新进度，由父级统一更新
                return {"success": False, "cancelled": True}
            
            try:
                # 文件解析
                if file_path.suffix.lower() in ['.pdf', '.docx']:
                    parse_result = await self.run_in_executor(
                        self.document_parser.parse_file, str(file_path)
                    )
                    content = parse_result['text']
                    metadata = parse_result.get('metadata', {})
                elif file_path.suffix.lower() in ['.txt', '.md', '.rst']:
                    # 优化 4：超大文件流式分块
                    def read_file_streaming(p: Path):
                        max_chunks = 200  # 限制最大 chunk 数，防止内存溢出
                        chunk_size = 4096  # 每 chunk 约 4KB 文本
                        content_parts = []
                        chunk_count = 0
                        
                        with open(p, 'r', encoding='utf-8') as f:
                            while True:
                                chunk = f.read(chunk_size)
                                if not chunk:
                                    break
                                content_parts.append(chunk)
                                chunk_count += 1
                                
                                # 内存保护：限制总 chunk 数
                                if chunk_count > max_chunks:
                                    logger.warning(
                                        f"File {p} exceeds {max_chunks} chunks, truncated"
                                    )
                                    break
                        
                        return ''.join(content_parts)
                    
                    content = await self.run_in_executor(read_file_streaming, file_path)
                    metadata = {}
                else:
                    logger.warning(f"Unsupported file type: {file_path.suffix}")
                    # 修复 text_idx_progress：不再更新进度，由父级统一更新
                    return {"success": False, "error": "Unsupported file type"}
                
                if not content or not content.strip():
                    logger.warning(f"Empty content in {file_path}")
                    # 修复 text_idx_progress：不再更新进度，由父级统一更新
                    return {"success": False, "error": "Empty content"}
                
                # 检查重复
                content_hash = await self.run_in_executor(
                    ContentHasher.generate_hash, content
                )
                existing = await self.check_duplicate(
                    content_hash, ImportType.LOCAL_FILE, source_path=str(file_path)
                )
                
                if existing:
                    if strategy == ImportStrategy.SKIP:
                        logger.info(f"Skipping duplicate file: {file_path}")
                        # 修复 text_idx_progress：不再更新进度，由父级统一更新
                        return {"success": True, "skipped": 1}
                    elif strategy == ImportStrategy.OVERWRITE:
                        # 使用当前实例的 Session 删除数据
                        await self.run_in_executor(
                            self._delete_existing_source_sync, existing.id
                        )
                        logger.info(f"Overwriting existing file: {file_path}")
                    elif strategy == ImportStrategy.ADD_NEW:
                        logger.info(f"Adding duplicate file as new: {file_path}")
                    else:
                        # 修复 text_idx_progress：不再更新进度，由父级统一更新
                        return {"success": True, "skipped": 1}
                
                # 分块处理
                chunks = await self.run_in_executor(
                    self.chunker.chunk_document,
                    text=content,
                    title=file_path.stem,
                    source_type="file",
                    source_path=str(file_path)
                )
                
                # 优化 5：限制 chunk 总数
                max_chunks_per_file = 100
                if len(chunks) > max_chunks_per_file:
                    logger.warning(
                        f"File {file_path} has {len(chunks)} chunks, limiting to {max_chunks_per_file}"
                    )
                    chunks = chunks[:max_chunks_per_file]
                
                # 优化 6：批量生成 embeddings（使用最大批量 32）
                batch_size = self.MAX_EMBEDDING_BATCH_SIZE
                all_chunks_data = []
                
                for batch_idx in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[batch_idx:batch_idx + batch_size]
                    batch_texts = [chunk["content"] for chunk in batch_chunks]
                    
                    # 使用当前实例的 db 和 embedding_service
                    batch_embeddings = await self.embedding_service.generate_batch_embeddings(
                        batch_texts, self.db
                    )
                    
                    for chunk_data, embedding in zip(batch_chunks, batch_embeddings):
                        all_chunks_data.append({
                            "chunk_index": chunk_data["chunk_index"],
                            "content": chunk_data["content"],
                            "embedding": embedding
                        })
                
                # 保存源和 chunks（使用批量写入）
                source_data = {
                    "title": file_path.stem,
                    "content_hash": content_hash,
                    "source_type": ImportType.LOCAL_FILE,
                    "source_path": str(file_path),
                    "file_name": file_path.name,
                    "source_metadata": metadata
                }
                
                await self.run_in_executor(
                    self._save_knowledge_source_and_chunks_sync,
                    source_data,
                    all_chunks_data
                )
                
                # 修复 text_idx_progress：不再更新进度，由父级统一更新
                
                logger.info(
                    f"Imported file {file_path.name} "
                    f"({len(chunks)} chunks, {len(all_chunks_data)} embeddings)"
                )
                
                return {"success": True, "imported": 1}
            
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                # 修复 text_idx_progress：不再更新进度，由父级统一更新
                return {"success": False, "error": str(e)}
        
        except Exception as e:
            logger.error(f"Unexpected error in _process_single_file: {e}")
            return {"success": False, "error": str(e)}
    
    async def import_video_content(
        self,
        task_id: uuid.UUID,
        video_url: str = None,
        video_path: str = None,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> Dict:
        """Import knowledge from video asynchronously"""
        try:
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING)
            
            # 优化 6：视频导入并发控制，只允许 1 个视频任务同时运行
            if self._video_import_semaphore is None:
                self._video_import_semaphore = asyncio.Semaphore(1)
            
            # 等待获取视频导入许可
            async with self._video_import_semaphore:
                return await self._import_video_content_internal(task_id, video_url, video_path, strategy)
        
        except Exception as e:
            logger.error(f"Video import failed: {e}")
            await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=str(e))
            return {"success": False, "error": str(e)}
    
    async def _import_video_content_internal(
        self,
        task_id: uuid.UUID,
        video_url: str = None,
        video_path: str = None,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> Dict:
        """视频导入内部实现（受 semaphore 保护）"""
        try:
            # Check ffmpeg availability before starting
            import shutil
            if shutil.which('ffmpeg') is None:
                error_msg = (
                    "ffmpeg is not installed. Video transcription requires ffmpeg.\n"
                    "Please install ffmpeg:\n"
                    "  Windows: winget install ffmpeg  OR  choco install ffmpeg\n"
                    "  macOS: brew install ffmpeg\n"
                    "  Linux: sudo apt-get install ffmpeg  OR  sudo yum install ffmpeg"
                )
                logger.error(error_msg)
                await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=error_msg)
                return {"success": False, "error": error_msg}
            
            # Download video via executor if url is provided
            if video_url:
                downloader = VideoDownloader()
                
                # 优化 3：使用简单的线程安全取消检查，避免反复创建事件循环
                def check_download_cancelled():
                    # 直接检查内存标志，无需事件循环
                    return self.is_task_cancelled(task_id)
                
                download_result = await self.run_in_executor(
                    lambda: downloader.download(video_url, cancel_check_callback=check_download_cancelled)
                )
                if not download_result["success"]:
                    raise Exception(f"Video download failed: {download_result['error']}")
                video_path = download_result["file_path"]
                video_title = download_result["title"]
            else:
                video_title = os.path.basename(video_path)
            
            # Transcribe video audio - use async method directly
            # 使用类级别的模型缓存避免重复加载
            transcriber = AudioTranscriber(model_size="base")
            
            # 优化 3：使用简单的取消检查回调
            def check_transcribe_cancelled():
                return self.is_task_cancelled(task_id)
            
            transcription = await transcriber.process_video(video_path, cancel_check_callback=check_transcribe_cancelled)
            if not transcription["success"]:
                raise Exception(f"Transcription failed: {transcription['error']}")
            
            # 修复 video_p0：转写完成后立即检查是否为空，避免创建空壳源
            segments = transcription.get("segments", [])
            if not segments or not transcription.get("text", "").strip():
                logger.warning(f"Video {video_url or video_path} has no valid segments/transcription")
                await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message="视频转写结果为空，可能是静音文件或转写失败")
                return {
                    "success": False,
                    "error": "视频转写结果为空",
                    "segments": 0,
                    "duration": transcription.get("duration", 0)
                }
            
            # Update total items count for progress tracking
            await self.update_task_progress(task_id, total_items=len(segments), processed_items=0)
            
            content_hash = await self.run_in_executor(ContentHasher.generate_hash, transcription["text"])
            # 修复 video_p1_4：VIDEO 类型单独处理去重参数
            if video_url:
                # URL 视频：使用 source_url 检查
                existing = await self.check_duplicate(content_hash, ImportType.VIDEO, source_url=video_url)
            else:
                # 本地视频：使用 source_path 检查
                existing = await self.check_duplicate(content_hash, ImportType.VIDEO, source_path=video_path)
            
            if existing:
                if strategy == ImportStrategy.SKIP:
                    # 修复 video_p1_5：SKIP 时返回 cancelled=False 的 skipped 结果
                    await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
                    return {"success": True, "skipped": True, "message": "Content already exists"}
                elif strategy == ImportStrategy.OVERWRITE:
                    await self.run_in_executor(self._delete_existing_source_sync, existing.id)
                elif strategy == ImportStrategy.ADD_NEW:
                    pass
                else:
                    await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
                    return {"success": True, "skipped": True, "message": "Content already exists"}
            
            # 优化 4：增量保存 segment，避免长视频数千 segment 全攒在内存
            source_data = {
                "title": video_title,
                "content_hash": content_hash,
                "source_type": ImportType.VIDEO,
                "source_url": video_url,
                "source_path": video_path,
                "source_metadata": {
                    "duration": transcription.get("duration", 0),
                    "language": transcription.get("language", "unknown")
                }
            }
            
            # 修复 video_p0_3：直接返回 source 对象，避免查询挂错源
            source = await self.run_in_executor(self._create_knowledge_source_sync, source_data)
            
            if not source:
                raise Exception("Failed to create knowledge source")
            
            # 批量处理 segments：每批生成 embedding 并立即保存
            # 优化 video_3：统一使用 MAX_EMBEDDING_BATCH_SIZE=32
            batch_size = self.MAX_EMBEDDING_BATCH_SIZE  # 32
            total_imported = 0
            
            for batch_idx in range(0, len(segments), batch_size):
                batch_segments = segments[batch_idx:batch_idx + batch_size]
                
                # 检查任务是否被取消
                if await self.check_task_cancelled(task_id):
                    logger.info(f"Task {task_id} cancelled during video embedding")
                    await self.update_task_progress(task_id, status=TaskStatus.CANCELLED, processed_items=batch_idx)
                    return {"success": False, "cancelled": True, "message": "Task was cancelled"}
                
                # 批量生成 embeddings
                batch_texts = [seg["text"] for seg in batch_segments]
                batch_embeddings = await self.embedding_service.generate_batch_embeddings(batch_texts, self.db)
                
                # 准备当前批次的 chunks 数据
                batch_chunks_data = []
                for idx, (segment, embedding) in enumerate(zip(batch_segments, batch_embeddings)):
                    chunk_idx = batch_idx + idx
                    batch_chunks_data.append({
                        "chunk_index": chunk_idx,
                        "content": segment["text"],
                        "embedding": embedding,
                        "timestamp_start": segment["start"],
                        "timestamp_end": segment["end"]
                    })
                
                # 优化 4：增量保存当前批次，避免内存累积
                await self.run_in_executor(
                    self._save_chunks_for_source_sync,
                    source.id,
                    batch_chunks_data
                )
                
                total_imported += len(batch_chunks_data)
                
                # 更新进度
                await self.update_task_progress(task_id, processed_items=min(batch_idx + batch_size, len(segments)))
                logger.debug(f"Saved batch {batch_idx // batch_size + 1}: {len(batch_chunks_data)} chunks")
            
            await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
            return {
                "success": True,
                "imported": 1,
                "segments": total_imported,
                "duration": transcription.get("duration", 0)
            }
        
        except Exception as e:
            logger.error(f"Video import internal failed: {e}")
            raise  # 重新抛出，由外部方法统一处理