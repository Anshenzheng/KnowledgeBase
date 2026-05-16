"""
Knowledge Base Engine - Combined & Fully Optimized Core Module
Includes: Async Text Processing, Secure Zhipu Embedding Service, and Non-blocking Router.
"""
import os
import re
import jwt
import uuid
import time
import shutil
import anyio
import httpx
import hashlib
from pathlib import Path
from loguru import logger
from typing import List, Dict, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session

# 假定项目的配置、数据库及模型依赖如下，请根据实际路径调整导入
from app.database import get_db
from app.config import settings
from app.models import ImportType, ImportStrategy, ImportTask, TaskStatus
from app.routes.tasks import create_import_task  # 异步后台实际执行器

router = APIRouter()

# ==========================================
# 模块一：文本处理与智谱 AI 向量服务层
# ==========================================

class TextEmbeddingService:
    """Generate embeddings for text chunks using configured Embedding API safely and asynchronously"""
    
    def __init__(self, db: Optional[Session] = None, model_id: Optional[str] = None):
        self.db = db
        self.model_id = model_id
        self._api_key = None
        self._cached_token = None
        self._token_expiry = 0
        self._api_base_url = None
        self.model_name = "embedding-2"
        self.dimension = 1024
        self.provider = "zhipu"
        
        # 如果提供了数据库会话，从数据库加载模型配置
        if db and model_id:
            self._load_model_config()
        elif db:
            # 没有指定 model_id，使用默认的 embedding 模型
            self._load_default_model_config()
    
    def _load_model_config(self):
        """从数据库加载指定模型配置"""
        from app.models import LLMModel
        model = self.db.query(LLMModel).filter(
            LLMModel.id == self.model_id,
            LLMModel.is_active == True
        ).first()
        
        if not model:
            logger.error(f"Embedding model {self.model_id} not found or inactive")
            raise ValueError(f"Embedding model {self.model_id} not found")
        
        if model.model_type != 'embedding':
            logger.warning(f"Model {self.model_id} is not an embedding model")
        
        self.model_name = model.model_name
        self._api_base_url = model.base_url
        self.provider = model.provider.value if hasattr(model.provider, 'value') else model.provider
        
        # 自动适配模型维度
        if 'embedding-2' in self.model_name or 'embedding-2' == self.model_name:
            self.dimension = 1024
        elif 'text-embedding' in self.model_name:
            self.dimension = 1536  # OpenAI embedding 维度
        else:
            self.dimension = 1024  # 默认维度
        
        logger.info(f"Loaded embedding model config: {self.model_name} ({self.provider})")
    
    def _load_default_model_config(self):
        """从数据库加载默认 embedding 模型配置"""
        from app.models import LLMModel
        # 优先查找标记为默认的 embedding 模型
        model = self.db.query(LLMModel).filter(
            LLMModel.model_type == 'embedding',
            LLMModel.is_active == True,
            LLMModel.is_default == True
        ).first()
        
        # 如果没有默认模型，查找第一个激活的 embedding 模型
        if not model:
            model = self.db.query(LLMModel).filter(
                LLMModel.model_type == 'embedding',
                LLMModel.is_active == True
            ).first()
        
        if not model:
            logger.warning("No embedding model configured in database, using default Zhipu config")
            # 回退到默认配置（兼容旧版本）
            self._api_base_url = "https://open.bigmodel.cn/api/paas/v4"
            return
        
        self.model_name = model.model_name
        self._api_base_url = model.base_url
        self.provider = model.provider.value if hasattr(model.provider, 'value') else model.provider
        
        # 自动适配模型维度
        if 'embedding-2' in self.model_name or 'embedding-2' == self.model_name:
            self.dimension = 1024
        elif 'text-embedding' in self.model_name:
            self.dimension = 1536  # OpenAI embedding 维度
        else:
            self.dimension = 1024  # 默认维度
        
        logger.info(f"Loaded default embedding model config: {self.model_name} ({self.provider})")
    
    def _get_api_key(self, db: Session) -> str:
        """从数据库获取 API Key"""
        if self._api_key is None:
            from app.models import LLMModel
            
            # 查找激活的 embedding 模型
            if self.model_id:
                model = db.query(LLMModel).filter(
                    LLMModel.id == self.model_id,
                    LLMModel.is_active == True
                ).first()
            else:
                # 优先默认模型
                model = db.query(LLMModel).filter(
                    LLMModel.model_type == 'embedding',
                    LLMModel.is_active == True,
                    LLMModel.is_default == True
                ).first()
                
                if not model:
                    model = db.query(LLMModel).filter(
                        LLMModel.model_type == 'embedding',
                        LLMModel.is_active == True
                    ).first()
            
            if not model or not model.api_key:
                logger.error("No API key found for embedding model")
                raise ValueError("Embedding model API key not configured")
            
            self._api_key = model.api_key
            logger.info(f"Loaded API key for embedding model: {model.model_name}")
        
        return self._api_key
    
    def _generate_jwt_token(self, db: Session) -> str:
        """根据智谱标准算法采用 JWT 动态算签生成 Token，拒绝透传明文 Key"""
        if self.provider != 'zhipu':
            # 非智谱模型，直接返回 API Key
            return self._get_api_key(db)
        
        curr_time = time.time()
        # 缓存保护：如果 Token 依然有效（预留 30 秒安全缓冲区），直接复用
        if self._cached_token and curr_time < self._token_expiry - 30:
            return self._cached_token
            
        try:
            api_key = self._get_api_key(db)
            id, secret = api_key.split(".")
            
            payload = {
                "api_key": id,
                "exp": int(curr_time * 1000) + 1800000,  # 30 分钟有效期
                "timestamp": int(curr_time * 1000),
            }
            
            # 安全编码：严禁向日志中直接 dump 此处的 secret
            self._cached_token = jwt.encode(
                payload,
                secret,
                algorithm="HS256",
                headers={"alg": "HS256", "sign_type": "SIGN"}
            )
            self._token_expiry = curr_time + 1800
            logger.info("Successfully refreshed Zhipu JWT Access Token.")
            return self._cached_token
        except Exception as e:
            logger.error(f"Failed to generate Zhipu JWT Token: {e}")
            raise

    async def generate_embedding(self, text: str, db: Session) -> List[float]:
        """异步非阻塞生成单个文本向量"""
        try:
            # 根据提供商选择不同的认证方式
            if self.provider == 'zhipu':
                token = self._generate_jwt_token(db)
                auth_header = f"Bearer {token}"
            else:
                # OpenAI, Gemini 等直接使用 API Key
                api_key = self._get_api_key(db)
                auth_header = f"Bearer {api_key}"
            
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(limits=limits, timeout=30.0) as client:
                response = await client.post(
                    f"{self._api_base_url}/embeddings",
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json"
                    },
                    json={"model": self.model_name, "input": text}
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate single embedding via API: {e}")
            raise
    
    async def generate_batch_embeddings(self, texts: List[str], db: Session, batch_size: int = 32) -> List[List[float]]:
        """利用长连接池，高效、非阻塞地批量提取文本向量"""
        try:
            # 根据提供商选择不同的认证方式
            if self.provider == 'zhipu':
                token = self._generate_jwt_token(db)
                auth_header = f"Bearer {token}"
            else:
                # OpenAI, Gemini 等直接使用 API Key
                api_key = self._get_api_key(db)
                auth_header = f"Bearer {api_key}"
            
            embeddings = []
            
            # 性能优化核心：将长连接池 AsyncClient 提至最外层，严禁在 for 循环中高频重复建立握手
            async with httpx.AsyncClient(timeout=60.0) as client:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    
                    response = await client.post(
                        f"{self._api_base_url}/embeddings",
                        headers={
                            "Authorization": auth_header,
                            "Content-Type": "application/json"
                        },
                        json={"model": self.model_name, "input": batch}
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    for item in data["data"]:
                        embeddings.append(item["embedding"])
            
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings via API: {e}")
            raise


class TextChunker:
    """Split text into chunks for embedding safely with heuristic alignment"""
    
    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap boundary must be strictly smaller than chunk size.")
    
    def chunk_text(self, text: str, metadata: Dict = None) -> List[Dict]:
        chunks = []
        start = 0
        chunk_index = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            
            if end < text_len:
                best_break = -1
                # 语义优化：建立由大到小的文本断块优先级结构（换行 > 完结标点）
                for punct in ['\n', '。', '！', '？', '.', '!', '?']:
                    last_punct = text.rfind(punct, start, end)
                    if last_punct > start:
                        best_break = last_punct + 1
                        break
                
                if best_break != -1:
                    end = best_break
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "chunk_index": chunk_index,
                    "metadata": metadata or {}
                })
                chunk_index += 1
            
            # 架构防御硬伤：计算下一步位移，100% 物理消除重叠区卡死引发的死循环
            next_start = end - self.chunk_overlap
            if next_start <= start:
                start = end  # 发生回退挤压时，强制推向当前断点末尾
            else:
                start = next_start
                
        return chunks

    def chunk_document(self, text: str, title: str, source_type: str, source_url: str = None, source_path: str = None) -> List[Dict]:
        metadata = {"title": title, "source_type": source_type, "source_url": source_url, "source_path": source_path}
        return self.chunk_text(text, metadata)


class ContentHasher:
    """Generate content hashes safely for database deduplication"""
    
    @staticmethod
    def generate_hash(content: str) -> str:
        normalized = re.sub(r'\s+', ' ', content.strip())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    
    @staticmethod
    async def generate_file_hash(file_path: str) -> str:
        """异步文件流式读取，杜绝大文件阻塞主循环"""
        def _read_hash():
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
            
        return await anyio.to_thread.run_sync(_read_hash)


# ==========================================
# 模块二：Pydantic 请求体契约校验层
# ==========================================

class WebImportRequest(BaseModel):
    url: str
    max_depth: int = 5
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


class LocalImportRequest(BaseModel):
    directory_path: str
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


class VideoImportRequest(BaseModel):
    url: Optional[str] = None
    file_path: Optional[str] = None
    strategy: ImportStrategy = ImportStrategy.SKIP
    task_name: Optional[str] = None


def _save_file_sync(file_src, dest_path: str):
    """磁盘同步 I/O 桥接函数，专门跑在工作线程池中"""
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file_src, buffer)


# ==========================================
# 模块三：FastAPI 安全非阻塞路由控制层
# ==========================================

@router.post("/import/web")
async def import_web_knowledge(
    request: WebImportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Import knowledge from web pages asynchronously"""
    task_name = request.task_name or f"Web Import: {request.url}"
    task = ImportTask(
        task_name=task_name, task_type=ImportType.WEB, input_url=request.url,
        max_depth=request.max_depth, strategy=request.strategy, status=TaskStatus.PENDING
    )
    
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id, import_type="web", url=request.url, max_depth=request.max_depth, strategy=request.strategy
    )
    return {"task_id": str(task.id), "message": "Web scraping import task successfully scheduled", "status": "pending"}


@router.post("/import/local")
async def import_local_knowledge(
    request: LocalImportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Import knowledge from a local authorized path"""
    try:
        # 安全加固：路径规范化及越界遍历防御 (../ 阻断)
        requested_path = Path(os.path.normpath(request.directory_path)).resolve()
        if not requested_path.is_absolute() or not requested_path.exists():
            raise HTTPException(status_code=400, detail="Target path must be an absolute and existing coordinate.")
        
        # 安全白箱隔离：校验执行路径是否属于系统许可根路径下
        allowed_base_paths = [
            Path(settings.UPLOAD_DIR).resolve(),
            Path(settings.STORAGE_PATH).resolve() if hasattr(settings, 'STORAGE_PATH') else None
        ]
        allowed_base_paths = [p for p in allowed_base_paths if p is not None]
        
        if not any(str(requested_path).startswith(str(allowed)) for allowed in allowed_base_paths):
            raise HTTPException(status_code=403, detail="Permission denied. Path is out of the authorized data base.")
        
        directory_path = str(requested_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformatted directory processing path: {str(e)}")
        
    task_name = request.task_name or f"Local Import: {Path(directory_path).name}"
    task = ImportTask(
        task_name=task_name, task_type=ImportType.LOCAL_FILE, input_path=directory_path,
        strategy=request.strategy, status=TaskStatus.PENDING
    )
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id, import_type="local_file", directory_path=directory_path, strategy=request.strategy
    )
    return {"task_id": str(task.id), "message": "Local disk indexing task scheduled", "status": "pending"}


@router.post("/import/video")
async def import_video_knowledge(
    request: VideoImportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Import and extract metadata knowledge from video stream source"""
    if not request.url and not request.file_path:
        raise HTTPException(status_code=400, detail="Ambiguous parameters. Either URL or file_path must be specified.")
        
    task_name = request.task_name or f"Video Import: {request.url or request.file_path}"
    task = ImportTask(
        task_name=task_name, task_type=ImportType.VIDEO, input_url=request.url,
        input_path=request.file_path, strategy=request.strategy, status=TaskStatus.PENDING
    )
    await anyio.to_thread.run_sync(db.add, task)
    await anyio.to_thread.run_sync(db.commit)
    await anyio.to_thread.run_sync(db.refresh, task)
    
    background_tasks.add_task(
        create_import_task,
        task_id=task.id, import_type="video", url=request.url, file_path=request.file_path, strategy=request.strategy
    )
    return {"task_id": str(task.id), "status": "pending"}


@router.post("/upload/file")
async def upload_single_file(
    file: UploadFile = File(...), task_name: str = None, strategy: ImportStrategy = ImportStrategy.SKIP,
    db: Session = Depends(get_db), background_tasks: BackgroundTasks = None
):
    """Upload and digest a single specific file safely without locking threads"""
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.rst']
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in supported_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported format: '{file_ext}'. Allowed: {supported_extensions}")
        
    safe_filename = Path(file.filename).name  # 斩断前端恶意传入的路径欺骗
    await anyio.to_thread.run_sync(os.makedirs, settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    
    # 1. 托管到专用工作线程池安全写入实体文件
    await anyio.to_thread.run_sync(_save_file_sync, file.file, file_path)
    
    # 2. 数据库联动事务处理：防止落库崩溃后形成磁盘垃圾无主文件
    try:
        task_name = task_name or f"Single File Upload: {file.filename}"
        task = ImportTask(
            task_name=task_name, task_type=ImportType.LOCAL_FILE, input_path=file_path,
            strategy=strategy, status=TaskStatus.PENDING
        )
        await anyio.to_thread.run_sync(db.add, task)
        await anyio.to_thread.run_sync(db.commit)
        await anyio.to_thread.run_sync(db.refresh, task)
    except Exception as db_err:
        # 联动原子回滚：数据库保存一旦遇难，紧急销毁由于 I/O 产生的磁盘实体文件
        if os.path.exists(file_path):
            await anyio.to_thread.run_sync(os.remove, file_path)
        logger.critical(f"Database sync failed. Uploaded asset purged to keep consistency. Error: {db_err}")
        raise HTTPException(status_code=500, detail="Internal persistency database breakdown, asset rollback executed.")
        
    if background_tasks:
        background_tasks.add_task(
            create_import_task,
            task_id=task.id, import_type="local_file", directory_path=file_path, strategy=strategy
        )
        
    return {"task_id": str(task.id), "file_path": file_path, "message": "File recorded and extraction pipeline initiated."}


@router.post("/upload/files")
async def upload_batch_files(
    files: List[UploadFile] = File(...), task_name: str = None, strategy: ImportStrategy = ImportStrategy.SKIP,
    db: Session = Depends(get_db), background_tasks: BackgroundTasks = None
):
    """Upload multiple files using advanced runtime UUID directory-level pipeline isolation"""
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.rst']
    valid_files = [f for f in files if Path(f.filename).suffix.lower() in supported_extensions]
    
    if not valid_files:
        raise HTTPException(status_code=400, detail="Zero valid matching extension documents found in payload.")
        
    # 核心增强：预先分配全局唯一的任务子文件夹，杜绝多请求高并发情况下的脏文件交织污染
    pre_allocated_task_id = uuid.uuid4()
    task_isolated_dir = os.path.join(settings.UPLOAD_DIR, str(pre_allocated_task_id))
    await anyio.to_thread.run_sync(os.makedirs, task_isolated_dir, exist_ok=True)
    
    saved_paths = []
    try:
        for file in valid_files:
            safe_filename = Path(file.filename).name
            file_path = os.path.join(task_isolated_dir, safe_filename)
            
            await anyio.to_thread.run_sync(_save_file_sync, file.file, file_path)
            saved_paths.append(file_path)
    except Exception as write_err:
        # 如果传输中途由于断网、磁盘满引发奔溃，立刻暴力推平该沙箱子目录，拒绝残留
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        logger.error(f"Batch write breakdown: {write_err}")
        raise HTTPException(status_code=500, detail="Disk streaming error occurred while burning multi-assets.")
        
    # 3. 关联沙箱目录并将对象绑定至元数据库
    try:
        task_name = task_name or f"Isolated Batch Upload: {len(saved_paths)} assets"
        task = ImportTask(
            id=pre_allocated_task_id, task_name=task_name, task_type=ImportType.LOCAL_FILE,
            input_path=task_isolated_dir, strategy=strategy, status=TaskStatus.PENDING
        )
        await anyio.to_thread.run_sync(db.add, task)
        await anyio.to_thread.run_sync(db.commit)
        await anyio.to_thread.run_sync(db.refresh, task)
    except Exception as db_err:
        # 元数据出错，自动执行级联物理擦除
        if os.path.exists(task_isolated_dir):
            await anyio.to_thread.run_sync(shutil.rmtree, task_isolated_dir)
        logger.critical(f"Database atomic exception. Purging isolated workspace: {db_err}")
        raise HTTPException(status_code=500, detail="Database core metadata injection failed, file space completely rolled back.")
        
    if background_tasks:
        # 收敛契约：只将当前隔离的子目录路径传给后台，底层函数扫描该独立目录即天然实现并发隔离
        background_tasks.add_task(
            create_import_task,
            task_id=task.id, import_type="local_file", directory_path=task_isolated_dir, strategy=strategy
        )
        
    return {
        "task_id": str(task.id),
        "workspace_isolated": task_isolated_dir,
        "total_ingested": len(saved_paths),
        "message": "Batch multi-files isolated environment initialized. Indexing scheduled."
    }