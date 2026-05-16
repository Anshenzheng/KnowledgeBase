"""
Reinitialize pgvector table with unique constraint
"""
from app.database import get_engine
from sqlalchemy import text

engine = get_engine()

print("Recreating vector table with unique constraint...")

with engine.connect() as conn:
    try:
        # Drop existing table
        conn.execute(text("DROP TABLE IF EXISTS knowledge_chunks_vector CASCADE"))
        conn.commit()
        print("[OK] Dropped existing table")
        
        # Create the vector table with 1024 dimensions and unique constraint
        conn.execute(text("""
            CREATE TABLE knowledge_chunks_vector (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chunk_id UUID UNIQUE REFERENCES knowledge_chunks(id),
                embedding vector(1024),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        print("[OK] Vector table created with unique constraint!")
        
        # Create index for faster search
        conn.execute(text("""
            CREATE INDEX idx_embedding 
            ON knowledge_chunks_vector USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        conn.commit()
        print("[OK] Vector index created!")
        
    except Exception as e:
        print(f"[ERROR] Failed to create vector table: {e}")
        conn.rollback()

print("Initialization completed!")
