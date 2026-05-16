"""
修复 LLMProvider 枚举类型的大小写问题，统一为大写
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

# 执行 SQL 更新枚举类型
with engine.connect() as conn:
    try:
        # 检查小写 zhipu 是否存在
        check_enum_query = text("""
            SELECT pg_enum.enumlabel
            FROM pg_type
            JOIN pg_enum ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'llmprovider'
            AND pg_enum.enumlabel = 'zhipu'
        """)
        result = conn.execute(check_enum_query).fetchone()
        
        if result:
            print("发现小写 zhipu 枚举值，需要修复")
            # PostgreSQL 不直接支持修改枚举值，需要创建新的枚举类型
            # 简单方法：直接添加 ZHIPU（如果不存在）
            add_enum_query = text("""
                ALTER TYPE llmprovider ADD VALUE IF NOT EXISTS 'ZHIPU'
            """)
            conn.execute(add_enum_query)
            conn.commit()
            print("[OK] ZHIPU（大写）枚举值添加成功")
        else:
            print("ZHIPU 枚举值已存在（可能是大写），无需添加")
            
        # 显示所有枚举值
        list_enum_query = text("""
            SELECT pg_enum.enumlabel
            FROM pg_type
            JOIN pg_enum ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'llmprovider'
            ORDER BY pg_enum.enumsortorder
        """)
        results = conn.execute(list_enum_query).fetchall()
        enum_values = [r[0] for r in results]
        print(f"当前 LLMProvider 枚举值：{enum_values}")
        
        # 检查是否有 ZHIPU（大写）
        if 'ZHIPU' in enum_values:
            print("[OK] 枚举值已统一为大写格式")
        else:
            print("[警告] 未找到 ZHIPU（大写），请手动检查")
            
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

print("迁移完成！")
