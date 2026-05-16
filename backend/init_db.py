from sqlalchemy import create_engine, text

# Connect to postgres database
engine = create_engine('postgresql://postgres:root@localhost:5432/postgres')

# Create knowledge_base database
try:
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(text('CREATE DATABASE knowledge_base'))
    print('Database created successfully!')
except Exception as e:
    print(f'Database might already exist: {e}')

# Enable pgvector extension
engine2 = create_engine('postgresql://postgres:root@localhost:5432/knowledge_base')
with engine2.connect() as conn:
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    conn.commit()
print('pgvector extension enabled!')
