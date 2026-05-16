"""
Database Connection and Session Management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from loguru import logger

# Database engine - lazy initialization
_engine = None
SessionLocal = None


def get_engine():
    """Get or create database engine (lazy loading)"""
    global _engine
    if _engine is None:
        try:
            logger.info("Creating database engine...")
            _engine = create_engine(
                settings.DATABASE_URL,
                pool_pre_ping=True,
                pool_size=20,  # Increased from 10
                max_overflow=40,  # Increased from 20
                pool_timeout=30,  # Increased timeout
                pool_recycle=3600  # Recycle connections after 1 hour
            )
            # Test connection
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database engine created successfully")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise
    return _engine


def get_db_session_factory():
    """Get or create session factory (lazy loading)"""
    global SessionLocal
    if SessionLocal is None:
        engine = get_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal


def get_db() -> Session:
    """Dependency for getting database session"""
    SessionLocal = get_db_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    from app.models import Base
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def check_db_connection():
    """Check if database connection is available"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
