"""
Migration script to add task_logs column to import_tasks table
"""
from sqlalchemy import text
from app.database import get_engine

def migrate():
    """Add task_logs column to import_tasks table"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'import_tasks' 
                AND column_name = 'task_logs'
            """))
            
            if result.fetchone():
                print("[OK] task_logs column already exists")
                return
            
            # Add task_logs column
            conn.execute(text("""
                ALTER TABLE import_tasks 
                ADD COLUMN task_logs JSONB DEFAULT '[]'
            """))
            
            conn.commit()
            print("[OK] Successfully added task_logs column to import_tasks table")
            
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        raise

if __name__ == "__main__":
    print("Running migration: Add task_logs column...")
    migrate()
    print("Migration completed!")
