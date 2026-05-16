"""
LLM Model Configuration API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID

from app.database import get_db
from app.models import LLMModel, LLMProvider

router = APIRouter()


class ModelCreate(BaseModel):
    provider: str
    model_name: str
    display_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000
    is_active: bool = True
    is_default: bool = False
    model_type: Optional[str] = "chat"


class ModelUpdate(BaseModel):
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class ModelResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    base_url: Optional[str]
    temperature: float
    max_tokens: int
    is_active: bool
    is_default: bool
    model_type: Optional[str]

    class Config:
        from_attributes = True


# IMPORTANT: /presets must be defined BEFORE /{model_id} to avoid route conflicts
@router.get("/presets")
async def get_model_presets():
    """Get predefined model configurations"""
    return [
        {
            "provider": "openai",
            "model_name": "gpt-3.5-turbo",
            "display_name": "OpenAI GPT-3.5 Turbo",
            "base_url": "https://api.openai.com/v1",
            "description": "Fast and efficient OpenAI model",
            "temperature": 0.7,
            "max_tokens": 2000
        },
        {
            "provider": "openai",
            "model_name": "gpt-4",
            "display_name": "OpenAI GPT-4",
            "base_url": "https://api.openai.com/v1",
            "description": "Most capable OpenAI model",
            "temperature": 0.7,
            "max_tokens": 4096
        },
        {
            "provider": "openai",
            "model_name": "gpt-4o",
            "display_name": "OpenAI GPT-4o",
            "base_url": "https://api.openai.com/v1",
            "description": "Latest OpenAI multimodal model",
            "temperature": 0.7,
            "max_tokens": 4096
        },
        {
            "provider": "gemini",
            "model_name": "gemini-pro",
            "display_name": "Google Gemini Pro",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "description": "Google's advanced language model",
            "temperature": 0.7,
            "max_tokens": 2048
        },
        {
            "provider": "gemini",
            "model_name": "gemini-1.5-flash",
            "display_name": "Google Gemini 1.5 Flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "description": "Google's fast and efficient model",
            "temperature": 0.7,
            "max_tokens": 8192
        },
        {
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "display_name": "DeepSeek Chat",
            "base_url": "https://api.deepseek.com/v1",
            "description": "DeepSeek conversational model",
            "temperature": 0.7,
            "max_tokens": 4096
        },
        {
            "provider": "deepseek",
            "model_name": "deepseek-coder",
            "display_name": "DeepSeek Coder",
            "base_url": "https://api.deepseek.com/v1",
            "description": "DeepSeek code-specialized model",
            "temperature": 0.7,
            "max_tokens": 4096
        }
    ]


@router.get("", response_model=List[ModelResponse])
async def list_models(db: Session = Depends(get_db)):
    """List all configured LLM models"""
    models = db.query(LLMModel).filter(LLMModel.is_active == True).all()
    
    return [
        ModelResponse(
            id=str(model.id),
            provider=model.provider.value,
            model_name=model.model_name,
            display_name=model.display_name,
            base_url=model.base_url,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            is_active=model.is_active,
            is_default=model.is_default,
            model_type=model.model_type
        )
        for model in models
    ]


@router.post("", response_model=ModelResponse)
async def create_model(
    model_data: ModelCreate,
    db: Session = Depends(get_db)
):
    """Create a new LLM model configuration"""
    # Convert provider string to enum
    provider_value = model_data.provider.lower()
    try:
        provider_enum = LLMProvider(provider_value)
    except ValueError:
        provider_enum = LLMProvider.CUSTOM
    
    # Create model data dict without provider
    model_dict = model_data.model_dump(exclude={'provider'})
    model_dict['provider'] = provider_enum
    
    model = LLMModel(**model_dict)
    
    # If setting as default, unset other defaults
    if model.is_default:
        db.query(LLMModel).update({"is_default": False})
    
    db.add(model)
    db.commit()
    db.refresh(model)
    
    return ModelResponse(
        id=str(model.id),
        provider=model.provider.value,
        model_name=model.model_name,
        display_name=model.display_name,
        base_url=model.base_url,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        is_active=model.is_active,
        is_default=model.is_default,
        model_type=model.model_type
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific model configuration"""
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    return ModelResponse(
        id=str(model.id),
        provider=model.provider.value,
        model_name=model.model_name,
        display_name=model.display_name,
        base_url=model.base_url,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        is_active=model.is_active,
        is_default=model.is_default
    )


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: UUID,
    model_data: ModelUpdate,
    db: Session = Depends(get_db)
):
    """Update a model configuration"""
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Update fields
    update_data = model_data.dict(exclude_unset=True)
    
    # If setting as default, unset other defaults
    if update_data.get("is_default"):
        db.query(LLMModel).filter(LLMModel.id != model_id).update({"is_default": False})
    
    for field, value in update_data.items():
        setattr(model, field, value)
    
    db.commit()
    db.refresh(model)
    
    return ModelResponse(
        id=str(model.id),
        provider=model.provider.value,
        model_name=model.model_name,
        display_name=model.display_name,
        base_url=model.base_url,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        is_active=model.is_active,
        is_default=model.is_default
    )


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a model configuration"""
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    db.delete(model)
    db.commit()
    
    return {"message": "Model deleted successfully"}


@router.get("/embedding/default")
async def get_default_embedding_model(db: Session = Depends(get_db)):
    """Get the default embedding model configuration"""
    from app.models import LLMModel
    
    # 优先查找标记为默认的 embedding 模型
    model = db.query(LLMModel).filter(
        LLMModel.model_type == 'embedding',
        LLMModel.is_active == True,
        LLMModel.is_default == True
    ).first()
    
    # 如果没有默认模型，查找第一个激活的 embedding 模型
    if not model:
        model = db.query(LLMModel).filter(
            LLMModel.model_type == 'embedding',
            LLMModel.is_active == True
        ).first()
    
    if not model:
        raise HTTPException(
            status_code=404,
            detail="No embedding model configured. Please add an embedding model first."
        )
    
    return {
        "id": str(model.id),
        "provider": model.provider.value if hasattr(model.provider, 'value') else model.provider,
        "model_name": model.model_name,
        "display_name": model.display_name,
        "base_url": model.base_url,
        "is_default": model.is_default
    }
