from app.database import get_db_session_factory
from app.models import KnowledgeSource, KnowledgeChunk
from sqlalchemy import text

db = get_db_session_factory()()

try:
    # 1. 检查知识源
    sources = db.query(KnowledgeSource).all()
    print(f"知识源总数：{len(sources)}")
    
    for source in sources:
        print(f"\n{'='*60}")
        print(f"标题：{source.title}")
        print(f"类型：{source.source_type.value}")
        print(f"URL: {source.source_url}")
        print(f"创建时间：{source.created_at}")
        
        # 检查该源的片段
        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.source_id == source.id).all()
        print(f"片段数量：{len(chunks)}")
        
        if chunks:
            print(f"\n前 3 个片段预览:")
            for i, chunk in enumerate(chunks[:3], 1):
                print(f"  片段{i}: {chunk.content[:100]}...")
        else:
            print("  [WARNING] 没有片段！")
    
    # 2. 检查向量表
    result = db.execute(text("SELECT COUNT(*) FROM knowledge_chunks_vector")).fetchone()
    print(f"\n{'='*60}")
    print(f"向量表中的向量数量：{result[0]}")
    
    # 3. 检查任务状态
    from app.models import ImportTask, TaskStatus
    tasks = db.query(ImportTask).order_by(ImportTask.created_at.desc()).limit(5).all()
    print(f"\n{'='*60}")
    print("最近 5 个任务:")
    for task in tasks:
        print(f"\n任务：{task.task_name}")
        print(f"  状态：{task.status.value}")
        print(f"  类型：{task.task_type.value}")
        print(f"  进度：{task.progress_percentage}%")
        print(f"  处理项：{task.processed_items}/{task.total_items}")
        if task.error_message:
            print(f"  错误：{task.error_message}")
        if task.task_logs:
            print(f"  日志条数：{len(task.task_logs)}")
            if task.task_logs:
                print(f"  最后日志：{task.task_logs[-1]}")
    
finally:
    db.close()
