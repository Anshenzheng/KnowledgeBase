"""
Import Task Management API Routes
"""
import asyncio  # 修复 tasks_import：添加 asyncio import
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import ImportTask, TaskStatus, ImportType

router = APIRouter()


async def create_import_task(
    task_id: UUID,
    import_type: str,
    file_list: list = None,
    **kwargs
):
    """Background task handler for imports"""
    from app.database import get_db_session_factory
    from app.services.knowledge_import import KnowledgeImportService
    
    SessionLocal = get_db_session_factory()
    db = SessionLocal()
    try:
        service = KnowledgeImportService(db)
        
        if import_type == "web":
            result = await service.import_web_content(
                task_id=task_id,
                url=kwargs.get("url"),
                max_depth=kwargs.get("max_depth", 5),
                strategy=kwargs.get("strategy")
            )
        
        elif import_type == "local" or import_type == "local_file":
            # If file_list is provided, process only those files
            if file_list:
                from app.services.knowledge_import import logger
                logger.info(f"Processing {len(file_list)} files from list")
                # Process each file in the list
                all_results = []
                has_cancelled = False  # 修复 batch_cancel：跟踪是否有取消
                
                for file_path in file_list:
                    result = await service.import_local_files(
                        task_id=task_id,
                        directory_path=file_path,
                        strategy=kwargs.get("strategy")
                    )
                    all_results.append(result)
                    
                    # 修复 batch_cancel：检查是否有取消
                    if result.get("cancelled"):
                        has_cancelled = True
                
                # Aggregate results
                result = {
                    "success": all(r.get("success", False) for r in all_results),
                    "total_files": len(file_list),
                    "results": all_results
                }
                
                # 修复 batch_cancel：如果有取消，添加 cancelled 标志
                if has_cancelled:
                    result["cancelled"] = True
            else:
                result = await service.import_local_files(
                    task_id=task_id,
                    directory_path=kwargs.get("directory_path"),
                    strategy=kwargs.get("strategy")
                )
        
        elif import_type == "video":
            result = await service.import_video_content(
                task_id=task_id,
                video_url=kwargs.get("url"),
                video_path=kwargs.get("file_path"),
                strategy=kwargs.get("strategy")
            )
        
        else:
            raise ValueError(f"Unknown import type: {import_type}")
        
        # Update task with result
        task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if task:
            task.result_summary = result
            # Set task status based on result
            if result.get("cancelled"):
                # 任务被用户取消
                task.status = TaskStatus.CANCELLED
                task.error_message = result.get("message", "Task was cancelled by user")
            elif result.get("skipped") and result.get("success"):
                # 修复 video_p1_5：SKIP 重复内容时，任务显示为 COMPLETED 但添加说明
                task.status = TaskStatus.COMPLETED
                task.error_message = result.get("message", "Content already exists, skipped")
            elif result.get("success"):
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.FAILED
                task.error_message = result.get("error", "Unknown error")
            task.completed_at = datetime.now()
            db.commit()
        
    except asyncio.CancelledError:
        # 修复 task_exception：单独处理 CancelledError，避免标为 FAILED
        db = SessionLocal()
        task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if task:
            task.status = TaskStatus.CANCELLED
            task.error_message = "Task was cancelled by user"
            task.completed_at = datetime.now()
            db.commit()
    except Exception as e:
        # Handle error
        db = SessionLocal()
        task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now()
            db.commit()
    finally:
        db.close()


@router.get("")
async def list_tasks(
    status: Optional[TaskStatus] = None,
    task_type: Optional[ImportType] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all import tasks with optional filters"""
    query = db.query(ImportTask)
    
    if status:
        query = query.filter(ImportTask.status == status)
    
    if task_type:
        query = query.filter(ImportTask.task_type == task_type)
    
    tasks = query.order_by(ImportTask.created_at.desc()).limit(limit).all()
    
    return [
        {
            "id": str(task.id),
            "task_name": task.task_name,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "progress_percentage": task.progress_percentage,
            "total_items": task.total_items,
            "processed_items": task.processed_items,
            "failed_items": task.failed_items,
            "log_count": len(task.task_logs) if task.task_logs else 0,  # 只返回日志数量
            "recent_logs": (task.task_logs or [])[-10:],  # 只返回最近 10 条日志
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_message": task.error_message
        }
        for task in tasks
    ]


@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    db: Session = Depends(get_db)
):
    """Get details of a specific task"""
    task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "id": str(task.id),
        "task_name": task.task_name,
        "task_type": task.task_type.value,
        "status": task.status.value,
        "input_url": task.input_url,
        "input_path": task.input_path,
        "max_depth": task.max_depth,
        "strategy": task.strategy.value if task.strategy else None,
        "total_items": task.total_items,
        "processed_items": task.processed_items,
        "failed_items": task.failed_items,
        "progress_percentage": task.progress_percentage,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "task_logs": task.task_logs or [],
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at
    }


@router.delete("/{task_id}")
async def delete_task(
    task_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a task record"""
    task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(task)
    db.commit()
    
    return {"message": "Task deleted successfully"}


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: UUID,
    db: Session = Depends(get_db)
):
    """Cancel a running task"""
    task = db.query(ImportTask).filter(ImportTask.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status == TaskStatus.RUNNING:
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        db.commit()
        
        # 优化 web_2：同时设置内存标志，让下载/转写钩子快速响应
        from app.services.knowledge_import import KnowledgeImportService
        # 通过类实例设置取消标志（如果有实例的话）
        # 注意：这里需要获取正在运行的 service 实例
        # 简单方案：直接修改类变量
        KnowledgeImportService._cancel_flags[task_id] = True
        
        return {"message": "Task cancelled successfully"}
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status: {task.status.value}"
        )
