"""
Knowledge Import API Routes - Thread-safe & Non-blocking Optimized Version
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
import os
import shutil
import anyio
from pathlib import Path
from datetime import datetime

from app.database import get_db
from app.config import settings
from app.models import ImportType, ImportStrategy, ImportTask, TaskStatus
from loguru import logger

# 规范化：将可能引起循环引用的核心调度函数在顶部导入（确保后台任务模块已解耦）
from app.routes.tasks import create_import_task

router = APIRouter()

# --- Pydantic Schemas ---

class WebImportRequest(BaseModel):
    url: str
    max_depth: int = 5
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


class LocalImportRequest(BaseModel):
    directory_path: str
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


class VideoImportRequest(BaseModel):
    url: Optional[str] = None
    file_path: Optional[str] = None
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


# --- Helper Functions ---

def _save_file_sync(file_src, dest_path: str):
    """Synchronous file copy helper to run inside a thread pool"""
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file_src, buffer)


# --- API Endpoints ---

@router.post("/import/web")
async def import_web_knowledge(
    request: WebImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Import knowledge from web pages (async task)"""
    task_name = request.task_name or f"Web Import: {request.url}"
    
    task = ImportTask(
        task_name=task_name,
        task_type=ImportType.WEB,
        input_url=request.url,
        max_depth=request.max_depth,
        strategy=request.strategy,
        status=TaskStatus.PENDING
    )
    
    # 异步非阻塞形式提交数据库
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="web",
        url=request.url,
        max_depth=request.max_depth,
        strategy=request.strategy
    )
    
    return {
        "task_id": str(task.id),
        "message": "Import task started",
        "status": "pending"
    }


@router.post("/upload/video")
async def upload_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    task_name: str = None,
    strategy: ImportStrategy = ImportStrategy.SKIP,
    db: Session = Depends(get_db)
):
    """Upload and import a video file for transcription and knowledge extraction"""
    supported_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v']
    file_ext = Path(video.filename).suffix.lower()
    
    if file_ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {file_ext}. Supported: {', '.join(supported_extensions)}"
        )
    
    # 安全文件名处理
    safe_filename = Path(video.filename).name
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    video_filename = f"{timestamp}_{safe_filename}"
    
    # 创建隔离目录
    base_dir = Path("uploads/video_uploads")
    task_isolated_dir = base_dir / video_filename
    await anyio.to_thread.run_sync(os.makedirs, task_isolated_dir, exist_ok=True)
    
    # 保存视频文件 - 使用流式写入避免内存溢出
    file_path = task_isolated_dir / video_filename
    try:
        max_file_size = 1024 * 1024 * 1024  # 限制最大 1GB
        total_size = 0
        chunk_size = 1024 * 1024  # 每次写入 1MB
        
        with open(file_path, 'wb') as buffer:
            async for chunk in video.iter_chunked(chunk_size):
                buffer.write(chunk)
                total_size += len(chunk)
                
                # 内存保护：超过限制大小后停止写入并清理
                if total_size > max_file_size:
                    logger.warning(f"Video file exceeds {max_file_size/1024/1024:.1f}MB limit")
                    # 清理不完整的文件
                    buffer.close()
                    if os.path.exists(file_path):
                        await anyio.to_thread.run_sync(os.remove, file_path)
                    if os.path.exists(task_isolated_dir):
                        await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video file too large. Maximum size is {max_file_size/1024/1024:.0f}MB"
                    )
        
        logger.info(f"Video file saved: {file_path}, size: {total_size/1024/1024:.2f}MB")
        
    except HTTPException:
        # 重新抛出 HTTP 异常（如 413）
        raise
    except Exception as e:
        logger.error(f"Failed to save video file: {e}")
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        raise HTTPException(status_code=500, detail=f"Failed to save video file: {str(e)}")
    
    # 创建任务
    task = ImportTask(
        task_name=task_name or f"视频导入：{video.filename}",
        task_type=ImportType.VIDEO,
        status=TaskStatus.PENDING,
        input_path=str(file_path)
    )
    
    try:
        await anyio.to_thread.run_sync(db.add, task)
        await anyio.to_thread.run_sync(db.commit)
        await anyio.to_thread.run_sync(db.refresh, task)
        
    except Exception as db_err:
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="video",
        file_path=str(file_path),
        strategy=strategy
    )
    
    return {
        "task_id": str(task.id),
        "file_path": str(file_path),
        "filename": video.filename,
        "message": "Video uploaded and import task scheduled",
        "status": "pending"
    }


@router.post("/import/local")
async def import_local_knowledge(
    request: LocalImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Import knowledge from local files (async task)"""
    try:
        # 安全规范：规范化路径，防范相对路径遍历攻击 (如 ../)
        requested_path = Path(os.path.normpath(request.directory_path)).resolve()
        
        if not requested_path.is_absolute():
            raise HTTPException(status_code=400, detail="Path must be absolute")
        
        if not requested_path.exists():
            raise HTTPException(status_code=400, detail="Path does not exist")
        
        if not requested_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        
        directory_path = str(requested_path)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid directory path: {str(e)}")
    
    task_name = request.task_name or f"Local Import: {Path(directory_path).name}"
    
    task = ImportTask(
        task_name=task_name,
        task_type=ImportType.LOCAL_FILE,
        input_path=directory_path,
        strategy=request.strategy,
        status=TaskStatus.PENDING
    )
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="local_file",
        directory_path=directory_path,
        strategy=request.strategy
    )
    
    return {
        "task_id": str(task.id),
        "message": "Import task started",
        "status": "pending"
    }


@router.post("/import/video")
async def import_video_knowledge(
    request: VideoImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Import knowledge from video (async task)"""
    if not request.url and not request.file_path:
        raise HTTPException(status_code=400, detail="Either URL or file_path must be provided")
    
    task_name = request.task_name or f"Video Import: {request.url or request.file_path}"
    
    task = ImportTask(
        task_name=task_name,
        task_type=ImportType.VIDEO,
        input_url=request.url,
        input_path=request.file_path,
        strategy=request.strategy,
        status=TaskStatus.PENDING
    )
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="video",
        url=request.url,
        file_path=request.file_path,
        strategy=request.strategy
    )
    
    return {
        "task_id": str(task.id),
        "message": "Import task started",
        "status": "pending"
    }


@router.post("/upload/file")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task_name: str = None,
    strategy: ImportStrategy = ImportStrategy.SKIP,
    db: Session = Depends(get_db)
):
    """Upload and import a single file safely to knowledge base"""
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.rst']
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {file_ext}. Supported: {', '.join(supported_extensions)}"
        )
    
    # 严格的安全防御：剔除任何路径结构，仅保留纯文件名
    safe_filename = Path(file.filename).name
    
    # 异步线程中安全创建全局主目录
    await anyio.to_thread.run_sync(os.makedirs, settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    
    # 二次验证，防止逃逸
    if not str(Path(file_path).resolve()).startswith(str(Path(settings.UPLOAD_DIR).resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path trajectory detected")
    
    # 1. 采用非阻塞线程池安全写入文件
    await anyio.to_thread.run_sync(_save_file_sync, file.file, file_path)
    
    # 2. 数据库事务落库与文件清除回滚机制
    try:
        task_name = task_name or f"File Upload: {file.filename}"
        task = ImportTask(
            task_name=task_name,
            task_type=ImportType.LOCAL_FILE,
            input_path=file_path,
            strategy=strategy,
            status=TaskStatus.PENDING
        )
        await anyio.to_thread.run_sync(db.add, task)
        await anyio.to_thread.run_sync(db.commit)
        await anyio.to_thread.run_sync(db.refresh, task)
        
    except Exception as db_err:
        # 一旦数据库保存失败，立刻回滚清理刚写入的实体硬盘文件，防止残留垃圾脏数据
        if os.path.exists(file_path):
            await anyio.to_thread.run_sync(os.remove, file_path)
        raise HTTPException(status_code=500, detail=f"Database persistent failure, uploaded file rolled back: {str(db_err)}")
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="local_file",
        directory_path=file_path, # 传入单文件具体路径
        strategy=strategy
    )
    
    return {
        "task_id": str(task.id),
        "file_path": file_path,
        "filename": file.filename,
        "message": "File uploaded and import task successfully scheduled",
        "status": "pending"
    }


@router.post("/upload/files")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    task_name: str = None,
    strategy: ImportStrategy = ImportStrategy.SKIP,
    db: Session = Depends(get_db)
):
    """Upload and import multiple files using directory-level task isolation"""
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.rst']
    valid_files = []
    invalid_files = []
    
    for file in files:
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in supported_extensions:
            invalid_files.append({"filename": file.filename, "reason": f"Unsupported format: {file_ext}"})
        else:
            valid_files.append(file)
            
    if not valid_files:
        raise HTTPException(
            status_code=400, 
            detail=f"No valid files injected. Supported: {', '.join(supported_extensions)}"
        )
    
    # 核心设计缺陷修复：生成一个临时 Task ID，建立独立的物理隔离沙箱子目录
    # 避免并发时多个用户的批量文件在统一个 UPLOAD_DIR 目录中互相交织污染
    import uuid
    pre_allocated_task_id = uuid.uuid4()
    task_isolated_dir = os.path.join(settings.UPLOAD_DIR, str(pre_allocated_task_id))
    
    # 使用 lambda 包装以支持关键字参数
    await anyio.to_thread.run_sync(lambda: os.makedirs(task_isolated_dir, exist_ok=True))
    
    saved_files = []
    try:
        for file in valid_files:
            safe_filename = Path(file.filename).name
            file_path = os.path.join(task_isolated_dir, safe_filename)
            
            # 使用非阻塞线程安全执行大文件写入
            await anyio.to_thread.run_sync(_save_file_sync, file.file, file_path)
            saved_files.append(file_path)
            
    except Exception as write_err:
        # 如果文件传输/写入中途崩溃，立刻清理整个沙箱任务子文件夹
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        raise HTTPException(status_code=500, detail=f"File disk write aborted, system swept cleanup: {str(write_err)}")
        
    # 3. 隔离子目录关联至数据库 Task
    try:
        task_name = task_name or f"Batch Upload: {len(saved_files)} files"
        task = ImportTask(
            id=pre_allocated_task_id, # 显式绑定已开辟的沙箱子目录 ID
            task_name=task_name,
            task_type=ImportType.LOCAL_FILE,
            input_path=task_isolated_dir, # 关联该独立任务独占的文件夹
            strategy=strategy,
            status=TaskStatus.PENDING
        )
        await anyio.to_thread.run_sync(db.add, task)
        await anyio.to_thread.run_sync(db.commit)
        await anyio.to_thread.run_sync(db.refresh, task)
        
    except Exception as db_err:
        # 联动回滚：数据库若因连接池满、死锁等报错，自动擦除刚才上传成功的所有物理实体文件
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        raise HTTPException(status_code=500, detail=f"Database mapping broken, isolated folder purged: {str(db_err)}")
    
    # 安全契约收敛：将隔离专属文件夹路径传入后台任务消费（避免传入未约定的 file_list 参数）
    background_tasks.add_task(
        create_import_task,
        task_id=task.id,
        import_type="local_file",
        directory_path=task_isolated_dir, # 后台逻辑扫描该专属目录即可，天然实现多任务数据隔离
        strategy=strategy
    )
        
    return {
        "task_id": str(task.id),
        "uploaded_files": len(saved_files),
        "invalid_files": invalid_files,
        "message": f"Successfully uploaded {len(saved_files)} files into isolated space and scheduled task",
        "status": "pending"
    }