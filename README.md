# 智能知识仓库 Agent

基于 Python FastAPI + PostgreSQL + pgvector + Angular 构建的智能知识仓库系统，支持多模型接入和多种知识导入方式。

## 功能特性

### 核心功能
- ✅ **多模型支持**: 集成 OpenAI (GPT), Google Gemini, DeepSeek, 智谱 AI 等多种大语言模型
- ✅ **智能对话**: 专业的聊天界面，支持与 AI Agent 进行对话
- ✅ **知识检索**: 基于向量数据库的语义检索，自动标注引用来源
- ✅ **任务管理**: 完整的导入任务追踪和状态管理
- ✅ **模型管理**: 可视化的模型配置界面，支持 Chat 模型和 Embedding 模型分别管理

### 系统优化
- 🛡️ **内存保护**: 分块读取文件、分批处理数据，防止内存溢出
- 🛡️ **并发优化**: 使用线程池管理耗时操作，避免阻塞主线程
- 🛡️ **资源监控**: 实时内存使用监控，超过阈值自动告警
- 🛡️ **异常处理**: 完善的守护线程和异常捕获机制
- 🛡️ **事务一致性**: 视频导入失败自动回滚，避免残留空数据
- 🛡️ **智能去重**: 本地文件按路径、URL 按地址、内容按 hash 多维度去重

### 知识导入工具
1. **网页爬虫导入**
   - 支持 5 层递归爬取
   - 自动提取网页主要内容
   - 智能去重和增量更新
   - **实时进度更新**：每页处理完立即反馈进度
   - **快速取消**：取消后爬虫立即停止，队列自动清空

2. **本地文件导入**
   - 支持 txt, md, rst 等格式
   - 批量导入目录文件
   - 自动文本分割和向量化
   - **并行处理**：多文件同时处理，进度实时更新

3. **视频知识库导入**
   - 支持 YouTube 等视频平台
   - 自动下载和音频提取
   - Whisper 语音识别转文本
   - 带时间戳的片段定位
   - **增量保存**：长视频分段处理，避免内存溢出
   - **空视频检测**：自动识别静音或转写失败的视频

### 数据库特性
- PostgreSQL + pgvector 向量数据库
- 高效的相似度搜索
- 完整的引用溯源系统
- 去重检查和导入策略（跳过/覆盖/新增）

## 技术栈

### 后端
- **框架**: FastAPI 0.109
- **数据库**: PostgreSQL 15+ with pgvector
- **向量嵌入**: TextEmbeddingService（支持多提供商）
- **LLM 集成**: httpx, PyJWT（智谱认证）
- **网页爬虫**: BeautifulSoup4, httpx
- **视频处理**: yt-dlp, Whisper
- **系统监控**: psutil（内存使用检查）
- **异步处理**: anyio, ThreadPoolExecutor

### 前端
- **框架**: Angular 17
- **UI 组件**: Angular Material
- **Markdown**: marked
- **代码高亮**: highlight.js

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- PostgreSQL 15+ (with pgvector extension)
- Redis (可选，用于任务队列)
- **FFmpeg** (视频转录必需)

#### FFmpeg 安装指南

FFmpeg 是视频处理的必备工具，用于从视频中提取音频进行语音识别。

**Windows:**
```bash
# 方法 1: 使用 winget (Windows 10/11 自带)
winget install ffmpeg

# 方法 2: 使用 Chocolatey
choco install ffmpeg

# 方法 3: 手动安装
# 1. 访问 https://www.gyan.dev/ffmpeg/builds/ 下载 release-full 版本
# 2. 解压到 C:\ffmpeg
# 3. 将 C:\ffmpeg\bin 添加到系统环境变量 PATH
# 4. 重启终端验证：ffmpeg -version
```

**macOS:**
```bash
# 使用 Homebrew
brew install ffmpeg
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

**验证安装:**
```bash
ffmpeg -version
```

如果显示版本信息，表示安装成功。

---### 首次启动步骤

#### 1. 安装 PostgreSQL 和 pgvector

**Windows 详细安装步骤:**

1. **安装 PostgreSQL 15+**
   - 下载并安装 PostgreSQL 15+: https://www.postgresql.org/download/windows/
   - 安装时记住设置的密码（默认为 postgres）

2. **下载 pgvector Windows 预编译包**
   - 官方 pgvector 仓库不提供 Windows 预编译包，使用社区维护的可靠版本
   - 打开下载地址：`https://github.com/andreiramani/pgvector_pgsql_windows/releases`
   - 下载与你的 PostgreSQL 版本匹配的包：
     - PostgreSQL 16：下载 `vector.v0.8.2-pg16.zip`（推荐版本，稳定兼容）
     - PostgreSQL 15/17：选择对应版本的 zip 包
   - 将下载的压缩包解压到任意目录（如 `下载\vector.v0.8.2-pg16`）

3. **安装 pgvector 扩展文件**
   
   **关键文件说明：**
   | 文件类型 | 所在目录 | 说明 |
   |---------|---------|------|
   | 动态库文件 | `vector.v0.8.2-pg16\lib\vector.dll` | 扩展的核心实现，必须复制到 PostgreSQL 的 lib 目录 |
   | 扩展脚本文件 | `vector.v0.8.2-pg16\share\extension\` 下的所有文件 | 包含 vector.control、vector--0.8.2.sql 等，定义扩展结构 |
   
   **注意：** `include` 目录下的头文件无需复制，仅编译源码时需要。
   
   **复制文件到 PostgreSQL 目录：**
   - 复制 `vector.dll` 到 PostgreSQL 的 lib 目录：
     ```
     C:\Program Files\PostgreSQL\16\lib\
     ```
   - 复制 `share\extension` 下的所有文件到 PostgreSQL 的扩展目录：
     ```
     C:\Program Files\PostgreSQL\16\share\extension\
     ```

4. **重启 PostgreSQL 服务**
   
   文件复制完成后，必须重启 PostgreSQL 服务才能识别新扩展：
   - 按下 `Win + R`，输入 `services.msc` 回车，打开「服务」窗口
   - 在列表中找到 `postgresql-x64-16`（你的 PostgreSQL 版本）
   - 右键点击服务，选择「重启」，等待服务状态变为「正在运行」

5. **在数据库中启用 pgvector 扩展**
   - 打开 PostgreSQL 的 SQL Shell (psql)（开始菜单中可找到）
   - 按提示连接到数据库（默认参数直接回车即可，密码为安装 PostgreSQL 时设置的 postgres 用户密码）
   - 执行以下 SQL 启用扩展：
     ```sql
     -- 启用 vector 扩展（IF NOT EXISTS 避免重复创建报错）
     CREATE EXTENSION IF NOT EXISTS vector;
     ```
   - 命令执行后无报错，且返回下一行 `postgres=#` 提示符，说明扩展已成功启用

6. **验证 pgvector 安装是否成功**
   
   **验证 1：查看已安装扩展列表**
   - 在 psql 中执行以下命令，确认 vector 扩展已注册：
     ```sql
     \dx
     ```
   - **预期结果：** 列表中出现 `vector` 条目，版本为 0.8.2，描述为 `vector data type and ivfflat and hnsw access methods`

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt install postgresql-15-pgvector

# macOS (使用 Homebrew)
brew install pgvector
```

#### 2. 创建数据库

```bash
# 使用 psql 命令行或 pgAdmin 创建数据库
psql -U postgres -c "CREATE DATABASE knowledge_base;"
```

#### 3. 配置后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# Windows CMD
.\venv\Scripts\activate.bat
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
cd backend
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac
```

编辑 `.env` 文件，配置以下参数：
```env
# 数据库配置
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=knowledge_base
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password  # 替换为您的数据库密码

# LLM API Keys（根据需要配置）
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
ZHIPU_API_KEY=...  # 智谱 AI API Key（格式：id.secret）
```

**注意**：系统现在支持从页面配置模型，包括 API Key、Base URL 等。`.env` 文件中的配置仅作为默认值，推荐在页面中进行配置。

#### 5. 初始化数据库表

```bash
cd backend
# 确保已激活虚拟环境
python -c "from app.database import init_db; init_db()"
```

#### 6. 启动后端服务

```bash
cd backend
# 确保已激活虚拟环境
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

验证后端启动成功：
- 访问 http://localhost:8000/docs 查看 API 文档
- 看到 Swagger UI 界面表示后端正常运行

#### 7. 配置前端

打开新的终端窗口：
```bash
cd frontend

# 安装依赖
npm install
```

#### 8. 启动前端

```bash
cd frontend
npm start
```

如果提示端口被占用或需要确认，输入 `y` 确认。

访问 http://localhost:4200 开始使用！

---

### 使用 Docker 启动（可选）

如果已安装 Docker 和 Docker Compose：
```bash
docker-compose up -d
```

这将自动启动所有服务。

---

## 使用指南

### 1. 配置模型

系统支持两种类型的模型配置：

#### Chat 模型（对话模型）
1. 访问"模型配置"页面
2. 点击"添加模型"按钮
3. 选择提供商（OpenAI/Gemini/DeepSeek/智谱 AI）
4. 填写 API Key 和模型名称
5. 设置温度参数和最大 Token 数
6. 可设置为默认模型

#### Embedding 模型（向量嵌入模型）
1. 切换到"Embedding 模型"标签页
2. 点击"添加模型"按钮
3. 选择提供商（智谱 AI/OpenAI/Gemini）
4. 填写 API Key 和模型名称
5. 可设置 Base URL（可选）
6. 可设置为默认模型

**预设配置**：系统为智谱 AI、OpenAI 和 Gemini 提供了预设选项，选择后会自动填充相关信息，只需填写 API Key 即可。

### 2. 导入知识库

#### 网页导入
1. 访问"知识库导入" -> "网页导入"
2. 输入起始 URL
3. 设置递归深度（1-5）
4. 选择重复处理策略
5. 点击"开始导入"

#### 本地文件导入
1. 访问"知识库导入" -> "本地文件导入"
2. 输入目录路径
3. 选择重复处理策略
4. 点击"开始导入"

#### 视频导入
**注意：** 视频导入需要安装 FFmpeg，请参考上方的安装指南。

1. 访问"知识库导入" -> "视频导入"
2. 输入视频 URL 或本地文件路径
3. 选择重复处理策略
4. 点击"开始导入"
5. 系统会自动：
   - 下载视频（如果是 URL）
   - 提取音频
   - 使用 Whisper 进行语音识别
   - 生成带时间戳的文本片段

### 3. 查看导入任务

访问"导入任务"页面查看所有任务的状态和进度

### 4. 开始对话

1. 访问"智能对话"页面
2. 选择模型
3. 勾选"使用知识库"
4. 输入问题，获取带引用的答案

## 系统稳定性说明

### 内存保护机制

系统已实施多层内存保护措施，防止内存溢出导致的崩溃：

1. **文件读取限制**：
   - 文本文件分块读取（每次 8KB）
   - 最大读取限制 10MB
   - 超过限制自动截断并记录警告

2. **数据库查询优化**：
   - 使用 `fetchmany()` 分批获取结果（每批 100 条）
   - 避免一次性加载大量数据到内存

3. **视频文件处理**：
   - 流式写入（每次 1MB）
   - 最大文件大小限制 1GB
   - 自动记录文件大小日志

4. **实时内存监控**：
   - 每处理 10 个文本块检查一次内存
   - 内存使用率超过 85% 时自动告警
   - 支持手动检查内存状态

### 并发优化

1. **线程池管理**：
   - 使用 `ThreadPoolExecutor` 统一管理线程
   - 最大工作线程数 10
   - 避免频繁创建销毁线程

2. **异步非阻塞**：
   - 使用 `anyio` 进行异步操作
   - 耗时操作在线程池中执行
   - 不阻塞主事件循环

3. **守护线程**：
   - 后台初始化线程使用守护模式
   - 主进程退出时自动清理
   - 完善的异常捕获机制

### 异常处理

1. **数据库连接**：
   - 连接池配置：`pool_size=20, max_overflow=40`
   - 自动检测连接健康：`pool_pre_ping=True`
   - 定时回收连接：`pool_recycle=3600`

2. **后台任务**：
   - 完整的 try-except 异常捕获
   - finally 块确保状态标记
   - 详细的错误日志记录

## 项目结构

```
KnowledgeBase/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库连接
│   │   ├── models.py            # SQLAlchemy 模型
│   │   ├── vector_db.py         # 向量数据库服务
│   │   ├── llm_service.py       # LLM 服务集成
│   │   ├── routes/
│   │   │   ├── chat.py          # 聊天 API
│   │   │   ├── models.py        # 模型配置 API
│   │   │   ├── knowledge.py     # 知识导入 API
│   │   │   └── tasks.py         # 任务管理 API
│   │   ├── services/
│   │   │   ├── text_embedding.py    # 文本嵌入服务
│   │   │   ├── knowledge_import.py  # 知识导入服务
│   │   │   └── knowledge_retrieval.py  # 知识检索服务
│   │   └── tools/
│   │       ├── web_scraper.py       # 网页爬虫
│   │       ├── video_downloader.py  # 视频下载
│   │       └── audio_transcriber.py # 音频转录
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── app.component.ts
    │   │   ├── app.config.ts
    │   │   ├── app.routes.ts
    │   │   ├── services/
    │   │   │   ├── chat.service.ts
    │   │   │   ├── model.service.ts
    │   │   │   ├── knowledge.service.ts
    │   │   │   └── task.service.ts
    │   │   └── components/
    │   │       ├── chat/          # 聊天组件
    │   │       ├── models/        # 模型配置组件
    │   │       ├── import/        # 导入组件
    │   │       └── tasks/         # 任务组件
    │   ├── assets/
    │   └── environments/
    ├── angular.json
    └── package.json
```

## API 文档

启动后端后访问 http://localhost:8000/docs 查看完整的 API 文档

### 主要 API 端点

- `POST /api/chat/messages` - 发送聊天消息
- `GET /api/chat/sessions` - 获取会话列表
- `GET /api/models` - 获取模型列表
- `POST /api/models` - 添加模型
- `POST /api/knowledge/import/web` - 网页导入
- `POST /api/knowledge/import/local` - 本地文件导入
- `POST /api/knowledge/import/video` - 视频导入
- `GET /api/tasks` - 获取任务列表

## 高级配置

### 自定义向量维度

在 `.env` 中修改：
```env
VECTOR_DIMENSION=768  # 根据使用的嵌入模型调整
CHUNK_SIZE=500        # 文本块大小
CHUNK_OVERLAP=50      # 文本块重叠
```

### 使用 Redis 任务队列

```bash
# 安装 Redis
# Windows: https://github.com/microsoftarchive/redis/releases
# Linux: sudo apt-get install redis-server

# 启动 Redis
redis-server

# 配置 Celery
celery -A app.celery worker --loglevel=info
```

## 故障排除

### 常见问题

1. **pgvector 扩展未找到**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **FFmpeg 未安装**
   - Windows: 下载 https://ffmpeg.org/download.html
   - 添加到系统 PATH

3. **内存使用率过高**
   - 检查导入的文件大小，避免超大文件
   - 减少批量导入的文件数量
   - 增加系统可用内存
   - 查看日志中的内存警告信息

4. **数据库连接池耗尽**
   - 增加连接池大小：修改 `database.py` 中的 `pool_size` 和 `max_overflow`
   - 减少并发请求数量
   - 检查是否有未关闭的数据库连接

5. **视频导入失败**
   - 确认 FFmpeg 已正确安装
   - 检查视频文件大小（最大 500MB）
   - 查看后端日志中的详细错误信息

6. **模型 API Key 无效**
   - 在页面配置中检查 API Key 是否正确
   - 确认模型是否处于激活状态
   - 检查 Base URL 是否正确

### 日志查看

后端日志使用 Loguru 记录，查看日志位置：
```bash
# 日志文件通常在项目根目录或配置的存储路径
tail -f logs/app.log
```

### 性能优化建议

1. **批量导入**：建议分批导入文件，每批不超过 20 个文件
2. **文本块大小**：根据实际需求调整 CHUNK_SIZE（默认 500）
3. **并发控制**：根据服务器性能调整线程池大小
4. **定期清理**：定期清理不再需要的导入任务和临时文件

## 贡献指南

3. **Whisper 模型下载失败**
   ```bash
   # 手动下载模型
   python -c "import whisper; whisper.load_model('base')"
   ```

4. **CORS 错误**
   - 确保前端 proxy.conf.json 配置正确
   - 检查后端 CORS 设置

## 开发计划

- [ ] 支持更多 LLM 提供商
- [ ] PDF 文档解析
- [ ] 多模态知识检索
- [ ] 知识图谱可视化
- [ ] 用户认证和权限管理
- [ ] 知识库版本管理

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
