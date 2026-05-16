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
        
        if source_type == ImportType.LOCAL_FILE and source_path:
            query = query.filter(KnowledgeSource.source_path == source_path)
        elif source_url:
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
        task = self.db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if not task:
            return False
        return task.status == TaskStatus.CANCELLED

    async def check_task_cancelled(self, task_id: uuid.UUID) -> bool:
        """Check if task has been cancelled asynchronously"""
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
            self.db.flush()  # Get source.id without full commit
            
            chunk_objects = []
            for chunk_data in chunks_data:
                chunk = KnowledgeChunk(
                    source_id=source.id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    embedding=str(chunk_data["embedding"]),
                    timestamp_start=chunk_data.get("timestamp_start"),
                    timestamp_end=chunk_data.get("timestamp_end")
                )
                chunk_objects.append(chunk)
                
            self.db.add_all(chunk_objects)
            self.db.commit()
            
            # Sync to Vector DB after SQL transaction success
            for chunk_obj, chunk_data in zip(chunk_objects, chunks_data):
                self.vector_db.store_embedding(chunk_obj.id, chunk_data["embedding"])
                
            return len(chunk_objects)
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
        """Import knowledge from web pages asynchronously"""
        try:
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING)
            await self.add_task_log(task_id, f"开始爬取网页：{url}", "info", {"max_depth": max_depth})
            
            scraper = WebScraper(max_depth=max_depth, max_pages=100)
            pages = await scraper.crawl_site(url)
            
            await self.add_task_log(task_id, f"爬取完成，共获取 {len(pages)} 个页面", "success")
            await self.update_task_progress(
                task_id,
                total_items=len(pages),
                processed_items=0,
                log_message=f"开始处理 {len(pages)} 个页面"
            )
            
            imported_count = 0
            skipped_count = 0
            updated_count = 0
            
            for idx, page in enumerate(pages):
                if await self.check_task_cancelled(task_id):
                    logger.info(f"Task {task_id} cancelled, stopping import")
                    await self.update_task_progress(task_id, status=TaskStatus.CANCELLED, processed_items=idx)
                    return {
                        "success": False, "cancelled": True, "message": "Task was cancelled by user",
                        "imported": imported_count, "skipped": skipped_count, "updated": updated_count
                    }
                
                try:
                    content_hash = await self.run_in_executor(ContentHasher.generate_hash, page["content"])
                    existing = await self.check_duplicate(content_hash, ImportType.WEB, source_url=page["url"])
                    
                    if existing:
                        if strategy == ImportStrategy.SKIP:
                            skipped_count += 1
                            if skipped_count % 10 == 1:
                                await self.add_task_log(task_id, f"跳过重复页面 (已跳过 {skipped_count} 个)", "warning", commit=False)
                            await self.update_task_progress(task_id, processed_items=idx + 1, commit=False)
                            continue
                        elif strategy == ImportStrategy.OVERWRITE:
                            await self.run_in_executor(self._delete_existing_source_sync, existing.id)
                            updated_count += 1
                            if updated_count % 10 == 1:
                                await self.add_task_log(task_id, f"更新已有内容 (已更新 {updated_count} 个)", "info", commit=False)
                        elif strategy == ImportStrategy.ADD_NEW:
                            if updated_count % 10 == 1:
                                await self.add_task_log(task_id, f"添加重复内容 (已添加 {updated_count} 个)", "info", commit=False)
                        else:
                            skipped_count += 1
                            await self.update_task_progress(task_id, processed_items=idx + 1, commit=False)
                            continue
                    
                    if imported_count == 0 or (imported_count + 1) % 10 == 0:
                        await self.add_task_log(task_id, f"创建知识源：{page['title']}", "success", {"url": page["url"]}, commit=False)
                    
                    chunks = await self.run_in_executor(
                        self.chunker.chunk_document,
                        text=page["content"], title=page["title"], source_type="web", source_url=page["url"]
                    )
                    
                    if imported_count == 0 or (imported_count + 1) % 10 == 0:
                        await self.add_task_log(task_id, f"分割为 {len(chunks)} 个片段", "info", commit=False)
                    
                    # Batch generate embeddings and transform chunk structures inside executor
                    # 内存检查：处理大量数据前检查内存状态
                    self.check_memory_usage()
                    
                    chunks_data = []
                    for chunk_idx, chunk_data in enumerate(chunks):
                        # 每处理 10 个 chunk 检查一次内存
                        if chunk_idx % 10 == 0:
                            self.check_memory_usage()
                        
                        embedding = await self.embedding_service.generate_embedding(chunk_data["content"], self.db)
                        chunks_data.append({
                            "chunk_index": chunk_data["chunk_index"],
                            "content": chunk_data["content"],
                            "embedding": embedding
                        })
                    
                    source_data = {
                        "title": page["title"],
                        "content_hash": content_hash,
                        "source_type": ImportType.WEB,
                        "source_url": page["url"],
                        "source_metadata": {"description": page["description"]}
                    }
                    
                    # Transactional batch save
                    await self.run_in_executor(self._save_knowledge_source_and_chunks_sync, source_data, chunks_data)
                    imported_count += 1
                    
                    if imported_count % 10 == 0 or imported_count == len(pages):
                        await self.add_task_log(task_id, f"进度：{idx + 1}/{len(pages)} (已导入 {imported_count} 个)", "info", commit=True)
                    else:
                        await self.update_task_progress(task_id, processed_items=idx + 1, commit=False)
                
                except Exception as e:
                    logger.error(f"Failed to import page {page['url']}: {e}")
                    await self.add_task_log(task_id, f"导入失败：{page.get('title', 'Unknown')} - {str(e)}", "error", commit=False)
                    
                    # Fixed blocking state queries
                    task = await self.run_in_executor(lambda: self.db.query(ImportTask).filter(ImportTask.id == task_id).first())
                    current_failed = task.failed_items if task else 0
                    await self.update_task_progress(task_id, processed_items=idx + 1, failed=(current_failed or 0) + 1, commit=False)
            
            await self.run_in_executor(lambda: self.db.commit())
            await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
            
            return {"success": True, "imported": imported_count, "skipped": skipped_count, "updated": updated_count, "total": len(pages)}
        
        except Exception as e:
            logger.error(f"Web import failed: {e}")
            await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=str(e))
            return {"success": False, "error": str(e)}
    
    async def import_local_files(
        self,
        task_id: uuid.UUID,
        directory_path: str,
        strategy: ImportStrategy = ImportStrategy.SKIP
    ) -> Dict:
        """Import knowledge from local files asynchronously"""
        try:
            await self.update_task_progress(task_id, status=TaskStatus.RUNNING)
            
            supported_extensions = ['.txt', '.md', '.rst', '.pdf', '.docx', '.doc']
            files = []
            path = Path(directory_path)
            
            if path.is_file() and path.suffix.lower() in supported_extensions:
                files = [path]
            elif path.is_dir():
                for ext in supported_extensions:
                    files.extend(path.rglob(f"*{ext}"))
            
            await self.update_task_progress(task_id, total_items=len(files), processed_items=0)
            
            imported_count = 0
            skipped_count = 0
            updated_count = 0  # Fixed: initialized missing variable to avoid NameError on cancellation
            
            for idx, file_path in enumerate(files):
                if await self.check_task_cancelled(task_id):
                    logger.info(f"Task {task_id} cancelled, stopping import")
                    await self.update_task_progress(task_id, status=TaskStatus.CANCELLED, processed_items=idx)
                    return {
                        "success": False, "cancelled": True, "message": "Task was cancelled by user",
                        "imported": imported_count, "skipped": skipped_count, "updated": updated_count
                    }
                
                try:
                    # Offload local file parsing to thread pool
                    if file_path.suffix.lower() in ['.pdf', '.docx']:
                        parse_result = await self.run_in_executor(self.document_parser.parse_file, str(file_path))
                        content = parse_result['text']
                        metadata = parse_result.get('metadata', {})
                    else:
                        def read_file_sync(p):
                            # 分块读取大文件，避免内存溢出
                            max_size = 10 * 1024 * 1024  # 限制最大 10MB
                            content_parts = []
                            current_size = 0
                            
                            with open(p, 'r', encoding='utf-8') as f:
                                while True:
                                    chunk = f.read(8192)  # 每次读取 8KB
                                    if not chunk:
                                        break
                                    content_parts.append(chunk)
                                    current_size += len(chunk.encode('utf-8'))
                                    
                                    # 内存保护：超过限制大小后停止读取
                                    if current_size > max_size:
                                        logger.warning(f"File {p} exceeds {max_size/1024/1024:.1f}MB limit, truncated")
                                        break
                            
                            return ''.join(content_parts)
                        
                        content = await self.run_in_executor(read_file_sync, file_path)
                        metadata = {}
                    
                    if not content or not content.strip():
                        logger.warning(f"Empty content in {file_path}")
                        await self.update_task_progress(task_id, processed_items=idx + 1)
                        continue
                    
                    content_hash = await self.run_in_executor(ContentHasher.generate_hash, content)
                    existing = await self.check_duplicate(content_hash, ImportType.LOCAL_FILE, source_path=str(file_path))
                    
                    if existing:
                        if strategy == ImportStrategy.SKIP:
                            skipped_count += 1
                            await self.update_task_progress(task_id, processed_items=idx + 1)
                            continue
                        elif strategy == ImportStrategy.OVERWRITE:
                            await self.run_in_executor(self._delete_existing_source_sync, existing.id)
                            updated_count += 1
                        elif strategy == ImportStrategy.ADD_NEW:
                            pass
                        else:
                            skipped_count += 1
                            await self.update_task_progress(task_id, processed_items=idx + 1)
                            continue
                    
                    chunks = await self.run_in_executor(
                        self.chunker.chunk_document,
                        text=content, title=file_path.stem, source_type="file", source_path=str(file_path)
                    )
                    
                    # Batch collect embedding execution inside loop efficiently
                    chunks_data = []
                    for chunk_data in chunks:
                        embedding = await self.embedding_service.generate_embedding(chunk_data["content"], self.db)
                        chunks_data.append({
                            "chunk_index": chunk_data["chunk_index"],
                            "content": chunk_data["content"],
                            "embedding": embedding
                        })
                    
                    source_data = {
                        "title": file_path.stem,
                        "content_hash": content_hash,
                        "source_type": ImportType.LOCAL_FILE,
                        "source_path": str(file_path),
                        "file_name": file_path.name,
                        "source_metadata": metadata
                    }
                    
                    # Fixed Performance Bug: Bulk add and batch commit chunks per file rather than one-by-one commit
                    await self.run_in_executor(self._save_knowledge_source_and_chunks_sync, source_data, chunks_data)
                    
                    imported_count += 1
                    await self.update_task_progress(task_id, processed_items=idx + 1)
                
                except Exception as e:
                    logger.error(f"Failed to import file {file_path}: {e}")
                    task = await self.run_in_executor(lambda: self.db.query(ImportTask).filter(ImportTask.id == task_id).first())
                    current_failed = task.failed_items if task else 0  # Fixed: aligned property name from task.failed -> task.failed_items
                    await self.update_task_progress(task_id, processed_items=idx + 1, failed=(current_failed or 0) + 1)
            
            await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
            return {"success": True, "imported": imported_count, "skipped": skipped_count, "updated": updated_count, "total": len(files)}
        
        except Exception as e:
            logger.error(f"Local file import failed: {e}")
            await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=str(e))
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
                download_result = await self.run_in_executor(downloader.download, video_url)
                if not download_result["success"]:
                    raise Exception(f"Video download failed: {download_result['error']}")
                video_path = download_result["file_path"]
                video_title = download_result["title"]
            else:
                video_title = os.path.basename(video_path)
            
            # Transcribe video audio - use async method directly
            transcriber = AudioTranscriber(model_size="base")
            transcription = await transcriber.process_video(video_path)
            if not transcription["success"]:
                raise Exception(f"Transcription failed: {transcription['error']}")
            
            segments = transcription.get("segments", [])
            
            # Update total items count for progress tracking
            await self.update_task_progress(task_id, total_items=len(segments), processed_items=0)
            
            content_hash = await self.run_in_executor(ContentHasher.generate_hash, transcription["text"])
            existing = await self.check_duplicate(content_hash, ImportType.VIDEO, video_url or video_path)
            
            if existing:
                if strategy == ImportStrategy.SKIP:
                    await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
                    return {"success": True, "skipped": True, "message": "Content already exists"}
                elif strategy == ImportStrategy.OVERWRITE:
                    await self.run_in_executor(self._delete_existing_source_sync, existing.id)
                elif strategy == ImportStrategy.ADD_NEW:
                    pass
                else:
                    await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
                    return {"success": True, "skipped": True, "message": "Content already exists"}
            
            chunks_data = []
            
            # Batch generate segment embeddings efficiently via executor loops
            for idx, segment in enumerate(segments):
                chunk_text = segment["text"]
                embedding = await self.embedding_service.generate_embedding(chunk_text, self.db)
                chunks_data.append({
                    "chunk_index": idx,
                    "content": chunk_text,
                    "embedding": embedding,
                    "timestamp_start": segment["start"],
                    "timestamp_end": segment["end"]
                })
                
                # Update progress after processing each segment
                await self.update_task_progress(task_id, processed_items=idx + 1)
            
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
            
            # Fixed Performance Bug: Atomic batch commit segments instead of calling commit() line by line in inner loops
            await self.run_in_executor(self._save_knowledge_source_and_chunks_sync, source_data, chunks_data)
            
            await self.update_task_progress(task_id, status=TaskStatus.COMPLETED)
            return {
                "success": True,
                "imported": 1,
                "segments": len(segments),
                "duration": transcription.get("duration", 0)
            }
        
        except Exception as e:
            logger.error(f"Video import failed: {e}")
            await self.update_task_progress(task_id, status=TaskStatus.FAILED, error_message=str(e))
            return {"success": False, "error": str(e)}