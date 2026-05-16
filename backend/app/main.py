"""
FastAPI Application Main Entry Point
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.database import init_db, get_engine, check_db_connection
from app.models import Base
from app.routes import chat, models, knowledge, tasks

# Import pgvector extensions
from sqlalchemy import text


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print("Starting Knowledge Base Agent...")
    
    # Initialize database synchronously but with timeout
    import threading
    import time
    
    db_initialized = False
    db_error = None
    
    def init_database():
        """数据库初始化函数，包含完整的异常处理"""
        nonlocal db_initialized, db_error
        try:
            # Check if database is available
            if not check_db_connection():
                db_error = "Database connection failed"
                print("Warning: Database connection failed. Some features may not work.")
                print("Please ensure PostgreSQL is running.")
                return
            
            # Initialize database tables
            init_db()
            print("Database initialized successfully")
            
            # Try to enable pgvector extension (optional)
            try:
                engine = get_engine()
                with engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()
                print("pgvector extension enabled")
            except Exception as e:
                print(f"Warning: pgvector extension not available: {e}")
                print("Vector database features will be limited")
            
            db_initialized = True
                
        except Exception as e:
            db_error = str(e)
            print(f"Error during database initialization: {e}")
            print("Application will start with limited functionality")
        finally:
            # 确保无论如何都标记完成
            if not db_initialized and not db_error:
                db_error = "Initialization incomplete"
    
    # Run database initialization in background thread with timeout
    # 使用守护线程，确保主进程退出时线程也会退出
    init_thread = threading.Thread(target=init_database, daemon=True)
    init_thread.start()
    init_thread.join(timeout=15)  # Wait up to 15 seconds
    
    # 如果线程还在运行但超时了，记录日志
    if init_thread.is_alive():
        print("Warning: Database initialization is still running after 15s timeout")
    
    # Log final status
    if not db_initialized and not db_error:
        print("Database initialization timed out (15s). Application starting with limited functionality.")
    elif db_initialized:
        print("Database initialization completed")
    
    print("Application started successfully!")
    print("API Documentation: http://localhost:8000/docs")
    
    yield
    
    # Shutdown
    print("Shutting down Knowledge Base Agent...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Intelligent Knowledge Base Agent with Multi-LLM Support",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])

# Health check
@app.get("/health")
async def health_check():
    from app.database import check_db_connection
    db_status = "connected" if check_db_connection() else "disconnected"
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": db_status
    }

@app.get("/")
async def root():
    return {
        "message": "Knowledge Base Agent API",
        "docs": "/docs",
        "version": settings.APP_VERSION
    }
