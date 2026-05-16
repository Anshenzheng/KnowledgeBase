"""
Database migration script to update embedding column type
"""
from app.database import get_engine
from sqlalchemy import text

engine = get_engine()

print("Starting database migration...")

with engine.connect() as conn:
    try:
        # Alter the embedding column to use TEXT instead of VARCHAR(2000)
        conn.execute(text("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE TEXT"))
        conn.commit()
        print("[OK] Successfully migrated knowledge_chunks.embedding column to TEXT type")
    except Exception as e:
        print(f"[ERROR] Migration error: {e}")
        conn.rollback()

print("Migration completed!")
