from app.database import get_db_session_factory
from app.models import ImportTask, TaskStatus
import json

db = get_db_session_factory()()

try:
    # 获取最近的任务
    tasks = db.query(ImportTask).order_by(ImportTask.created_at.desc()).limit(3).all()
    
    for task in tasks:
        print(f"\n{'='*60}")
        print(f"任务：{task.task_name}")
        print(f"状态：{task.status.value}")
        print(f"类型：{task.task_type.value}")
        print(f"进度：{task.progress_percentage}%")
        print(f"处理项：{task.processed_items}/{task.total_items}")
        if task.error_message:
            print(f"错误信息：{task.error_message}")
        
        print(f"\n任务日志:")
        if task.task_logs:
            for i, log in enumerate(task.task_logs[-20:], 1):  # 只显示最后 20 条
                if isinstance(log, str):
                    try:
                        log_data = json.loads(log)
                    except:
                        log_data = {"message": log}
                else:
                    log_data = log
                
                level = log_data.get('level', '')
                message = log_data.get('message', '')
                detail = log_data.get('detail', {})
                
                if level == 'error' or '失败' in message or 'error' in message.lower():
                    print(f"{i}. [{level}] {message}")
                    if detail:
                        print(f"   详情：{detail}")
        else:
            print("  没有日志")
    
finally:
    db.close()
