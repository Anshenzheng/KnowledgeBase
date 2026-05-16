"""
Chat API Routes - Production Ready, Async-Safe & Robust Version
"""
import uuid
import datetime
from typing import List, Optional, Dict, Any
from loguru import logger
import anyio  # FastAPI 默认集成的异步非阻塞线程桥接库

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

# 导入底层核心依赖
from app.database import get_db
from app.models import ChatMessage, ConversationSession, LLMModel
from app.llm_service import LLMServiceFactory

router = APIRouter(tags=["Chat Engine"])

# ==========================================
# 1. Pydantic 数据契约校验层
# ==========================================

class MessageRequest(BaseModel):
    content: str
    session_id: Optional[str] = None  # 外部业务端传入的会话唯一标示 UUID 字符串
    model_id: Optional[str] = None
    use_knowledge: bool = True
    top_k: int = 5


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    content: str
    citations: List[dict] = []
    model_name: str


class SessionCreate(BaseModel):
    title: Optional[str] = None
    model_id: Optional[str] = None


# ==========================================
# 2. FastAPI 安全、非阻塞路由控制层
# ==========================================

@router.post("/sessions")
async def create_session(
    session_data: SessionCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的聊天会话
    通过线程池隔离数据库写入动作，防止并发时主事件循环被同步锁卡死
    """
    session_uuid = str(uuid.uuid4())
    
    def _db_create_session() -> ConversationSession:
        try:
            session = ConversationSession(
                session_id=session_uuid,
                title=session_data.title or "New Conversation",
                model_id=session_data.model_id
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to commit new session to DB: {e}")
            raise HTTPException(status_code=500, detail="Database save failed.")
    
    # 将同步数据库 I/O 托付给外部独立线程执行
    session = await anyio.to_thread.run_sync(_db_create_session)
    
    return {
        "session_id": session.session_id,
        "title": session.title,
        "created_at": str(session.created_at) if hasattr(session, 'created_at') else str(datetime.datetime.utcnow())
    }


@router.get("/sessions")
async def list_sessions(db: Session = Depends(get_db)):
    """
    拉取所有会话列表
    """
    def _db_fetch_sessions():
        return db.query(ConversationSession).order_by(
            ConversationSession.updated_at.desc()
        ).all()
        
    sessions = await anyio.to_thread.run_sync(_db_fetch_sessions)
    
    return [
        {
            "session_id": s.session_id,
            "title": s.title,
            "created_at": s.created_at,
            "updated_at": s.updated_at
        }
        for s in sessions
    ]


@router.post("/messages", response_model=MessageResponse)
async def send_message(
    request: MessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    核心 RAG 聊天接口：接收用户提问 -> 安全落库 -> 按需检索知识库 -> 调用 LLM -> 写入助手回复
    """
    
    # --------------------------------------------------------
    # 步骤一：【独立线程执行】会话探针、模型配置检索、持久化 User 消息
    # --------------------------------------------------------
    def _prepare_context_and_save_user_msg():
        try:
            # 1. 严格校验或初始化会话元数据
            if request.session_id:
                session_obj = db.query(ConversationSession).filter(
                    ConversationSession.session_id == request.session_id
                ).first()
                if not session_obj:
                    raise HTTPException(status_code=404, detail="Requested conversation session not found")
            else:
                session_obj = ConversationSession(
                    session_id=str(uuid.uuid4()),
                    title=request.content[:47] + "..." if len(request.content) > 50 else request.content
                )
                db.add(session_obj)
                db.commit()
                db.refresh(session_obj)

            # 2. 匹配 LLM 引擎硬件驱动配置
            if request.model_id:
                model_obj = db.query(LLMModel).filter(LLMModel.id == request.model_id).first()
            else:
                model_obj = db.query(LLMModel).filter(LLMModel.is_default == True).first()
            
            if not model_obj:
                raise HTTPException(
                    status_code=400,
                    detail="No valid active LLM models configured in the core management plane."
                )

            # 3. 落地保存用户发送的消息 (关联数据库内部真实自增/物理主键 id，而非会话字符串，防御关联错误)
            user_msg_obj = ChatMessage(
                session_id=session_obj.id,
                role="user",
                content=request.content,
                model_id=model_obj.id
            )
            db.add(user_msg_obj)
            db.commit()
            db.refresh(user_msg_obj)

            # 4. 严格拉取最近 10 条历史消息作为上下文（按创建时间降序限制 10 条）
            history = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_obj.id,
                ChatMessage.id != user_msg_obj.id
            ).order_by(ChatMessage.created_at.desc()).limit(10).all()
            
            # 将拿到的 10 条历史记录反转，恢复为正常时间线顺序
            history.reverse()

            return session_obj, model_obj, user_msg_obj, history
        except HTTPException:
            db.rollback()
            raise
        except Exception as err:
            db.rollback()
            logger.error(f"Transaction collapsed during preparation segment: {err}")
            raise HTTPException(status_code=500, detail="Data layer persistence fault.")

    # 异步非阻塞等待环境和数据准备完成
    session, model, user_message, history_messages = await anyio.to_thread.run_sync(_prepare_context_and_save_user_msg)

    # --------------------------------------------------------
    # 步骤二：知识增强检索层（受 use_knowledge 布尔开关控制）
    # --------------------------------------------------------
    context = ""
    citations = []
    
    if request.use_knowledge:
        # 延迟动态导入，在架构上斩断与知识导入模块的潜在循环依赖循环
        from app.services.knowledge_retrieval import KnowledgeRetrievalService
        
        try:
            retrieval_service = KnowledgeRetrievalService(db)
            search_result = await retrieval_service.search_with_context(
                request.content,
                top_k=request.top_k
            )
            context = search_result.get("context", "")
            citations = search_result.get("citations", [])
        except Exception as ret_err:
            # 知识库偶发性崩溃不应直接导致聊天不可用，降级为普通无记忆对话并输出警报
            logger.warning(f"Vector Knowledge Base Retrieval skipped due to fault: {ret_err}")

    # --------------------------------------------------------
    # 步骤三：构建多轮对话 Prompt 上下文结构
    # --------------------------------------------------------
    messages = []
    
    # 只有当知识库中有相关背景知识被匹配出来时，才外挂 System 系统指令
    if context:
        system_prompt = f"""You are a helpful knowledge assistant. Use the following context from the knowledge base to answer questions. Always cite your sources.

Context:
{context}

Instructions:
- Answer based on the provided context when possible
- Cite sources using [1], [2], etc.
- If the context doesn't contain relevant information, say so
- Be concise and accurate"""
        messages.append({"role": "system", "content": system_prompt})
    
    # 装填多轮会话历史
    for msg in history_messages:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # 装填当前用户发送的问题
    messages.append({"role": "user", "content": request.content})

    # --------------------------------------------------------
    # 步骤四：外部大模型调用（原生的异步网络 I/O 通信，不占用工作线程池）
    # --------------------------------------------------------
    try:
        llm_service = LLMServiceFactory.create_service(
            provider=model.provider,
            api_key=model.api_key,
            base_url=model.base_url,
            model=model.model_name
        )
        
        response_content = await llm_service.chat(
            messages,
            temperature=model.temperature,
            max_tokens=model.max_tokens
        )
        
    except Exception as llm_err:
        logger.error(f"Remote upstream LLM service integration fatal failure: {llm_err}")
        
        # 联动数据回滚防御：若大模型未吐出有效结果，需要将刚存进去的无回复 User 消息予以销毁或打上异常标记
        def _purge_orphan_user_msg():
            try:
                db.delete(user_message)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.critical(f"Failed to purge orphan user text chunk: {e}")
                
        await anyio.to_thread.run_sync(_purge_orphan_user_msg)
        raise HTTPException(status_code=502, detail="Upstream LLM core engine timeout or network error.")

    # --------------------------------------------------------
    # 步骤五：【独立线程执行】将 Assistant 响应落库，更新会话生命周期
    # --------------------------------------------------------
    def _save_assistant_response_and_update_session() -> ChatMessage:
        try:
            assistant_msg_obj = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=response_content,
                model_id=model.id,
                citations=citations  # 直接存储 citations 数组，不要嵌套
            )
            db.add(assistant_msg_obj)
            
            # 明确更新会话更新时间，禁止直接设为 None 触发隐式副作用
            session.updated_at = datetime.datetime.utcnow()
            
            db.commit()
            db.refresh(assistant_msg_obj)
            return assistant_msg_obj
        except Exception as save_err:
            db.rollback()
            logger.critical(f"Database error while committing LLM response: {save_err}")
            raise HTTPException(status_code=500, detail="Failed to persist LLM response token asset.")

    assistant_message = await anyio.to_thread.run_sync(_save_assistant_response_and_update_session)

    return MessageResponse(
        message_id=str(assistant_message.id),
        session_id=session.session_id,
        content=response_content,
        citations=citations,
        model_name=model.display_name if hasattr(model, 'display_name') else model.model_name
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    拉取某个特定会话下的所有历史明细（严格按照创建时间升序排列）
    """
    def _db_fetch_messages():
        session_obj = db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        
        if not session_obj:
            raise HTTPException(status_code=404, detail="Target session reference entity not found")
        
        return db.query(ChatMessage).filter(
            ChatMessage.session_id == session_obj.id
        ).order_by(ChatMessage.created_at.asc()).all()
        
    try:
        messages = await anyio.to_thread.run_sync(_db_fetch_messages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal database telemetry error: {str(e)}")
    
    return [
        {
            "id": str(msg.id),
            "role": msg.role,
            "content": msg.content,
            # 兼容旧数据格式：如果 citations 是嵌套格式 {"citation": {...}}，则解包
            "citations": [
                c.get("citation", c) if isinstance(c, dict) and "citation" in c else c
                for c in (msg.citations or [])
            ],
            "created_at": str(msg.created_at)
        }
        for msg in messages
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    彻底级联删除某个聊天会话及其下挂的所有消息碎片
    """
    def _db_delete_session_tx():
        session_obj = db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        
        if not session_obj:
            raise HTTPException(status_code=404, detail="Target session already deleted or non-existent")
        
        db.delete(session_obj)
        db.commit()
        
    try:
        await anyio.to_thread.run_sync(_db_delete_session_tx)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cascade purge session: {e}")
        raise HTTPException(status_code=500, detail="Data execution engine failed to wipe session.")


@router.delete("/sessions")
async def delete_all_sessions(
    db: Session = Depends(get_db)
):
    """
    清空所有聊天会话及其下挂的所有消息碎片
    """
    def _db_delete_all_sessions_tx():
        sessions = db.query(ConversationSession).all()
        for session in sessions:
            db.delete(session)
        db.commit()
        return {"deleted_count": len(sessions)}
        
    try:
        result = await anyio.to_thread.run_sync(_db_delete_all_sessions_tx)
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cascade purge all sessions: {e}")
        raise HTTPException(status_code=500, detail="Data execution engine failed to wipe all sessions.")
        
    return {"message": "Session and all associated message logs deleted successfully."}