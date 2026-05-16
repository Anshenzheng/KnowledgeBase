from app.database import get_db_session_factory
from app.models import ImportTask
from sqlalchemy import text
import json

db = get_db_session_factory()()

try:
    # 获取最近一个完成的任务
    task = db.query(ImportTask).filter(
        ImportTask.status == 'completed'
    ).order_by(ImportTask.created_at.desc()).first()
    
    if task:
        print(f"任务：{task.task_name}")
        print(f"状态：{task.status.value}")
        print(f"进度：{task.progress_percentage}%")
        print(f"处理项：{task.processed_items}/{task.total_items}")
        print(f"导入项：{task.result_summary}")
        
        print(f"\n任务日志:")
        if task.task_logs:
            for i, log in enumerate(task.task_logs[:30], 1):  # 只显示前 30 条
                if isinstance(log, str):
                    log_data = json.loads(log)
                else:
                    log_data = log
                
                timestamp = log_data.get('timestamp', '')
                level = log_data.get('level', '')
                message = log_data.get('message', '')
                detail = log_data.get('detail', {})
                
                print(f"{i}. [{level}] {message}")
                if detail:
                    print(f"   详情：{detail}")
        else:
            print("  没有日志")
    
    # 检查知识源
    print(f"\n{'='*60}")
    print("最近创建的知识源:")
    sources = db.execute(text("""
        SELECT title, source_type, source_url, 
               (SELECT COUNT(*) FROM knowledge_chunks kc 
                WHERE kc.source_id = knowledge_sources.id) as chunk_count
        FROM knowledge_sources
        ORDER BY created_at DESC
        LIMIT 10
    """)).fetchall()
    
    for source in sources:
        print(f"\n标题：{source.title}")
        print(f"  类型：{source.source_type}")
        print(f"  URL: {source.source_url}")
        print(f"  片段数：{source.chunk_count}")
    
finally:
    db.close()
