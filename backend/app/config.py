"""
Application Configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Knowledge Base Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Database
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: str = "5432"
    DATABASE_NAME: str = "knowledge_base"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    ZHIPU_API_KEY: Optional[str] = None
    
    # Model Endpoints
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    
    # Vector Database
    VECTOR_DIMENSION: int = 1024  # Match Zhipu embedding-2 dimension
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    
    # File Storage
    STORAGE_PATH: str = "./storage"
    UPLOAD_DIR: str = "./uploads"
    
    # CORS
    FRONTEND_URL: str = "http://localhost:4200"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Create storage directories
os.makedirs(settings.STORAGE_PATH, exist_ok=True)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
