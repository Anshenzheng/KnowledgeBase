"""
添加 model_type 字段到 llm_models 表
"""
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 从环境变量构建数据库连接字符串
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "5432")
DB_NAME = os.getenv("DATABASE_NAME", "knowledge_base")
DB_USER = os.getenv("DATABASE_USER", "postgres")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "postgres")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

print(f"使用数据库连接：{DB_HOST}:{DB_PORT}/{DB_NAME}")

# 创建数据库引擎
engine = create_engine(DATABASE_URL)

# 执行 SQL 添加字段
with engine.connect() as conn:
    try:
        # 检查字段是否已存在
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'llm_models' 
            AND column_name = 'model_type'
        """)
        result = conn.execute(check_query).fetchone()
        
        if result:
            print("model_type 字段已存在，无需添加")
        else:
            # 添加 model_type 字段
            add_column_query = text("""
                ALTER TABLE llm_models 
                ADD COLUMN model_type VARCHAR(50) DEFAULT 'chat'
            """)
            conn.execute(add_column_query)
            conn.commit()
            print("[OK] model_type 字段添加成功")
            
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

print("迁移完成！")
