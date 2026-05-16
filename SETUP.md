## 本地开发环境配置

### 必需软件

1. **Python 3.10+**
   - 下载地址：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **Node.js 18+**
   - 下载地址：https://nodejs.org/
   - 建议使用 LTS 版本

3. **PostgreSQL 15+**
   - 下载地址：https://www.postgresql.org/download/windows/
   - 安装时记住设置的 postgres 密码

4. **FFmpeg** (视频处理必需)
   - Windows 下载：https://ffmpeg.org/download.html
   - 解压后将 bin 目录添加到系统 PATH

### 可选软件

5. **Redis** (任务队列，可选)
   - Windows 下载：https://github.com/microsoftarchive/redis/releases
   - 用于异步任务处理

### 快速启动

1. 安装 PostgreSQL 并创建数据库：
```sql
CREATE DATABASE knowledge_base;
```

2. 安装 pgvector 扩展：
```bash
# 方法 1: 使用 pgxn (如果已安装)
pgxn install vector

# 方法 2: 手动编译
git clone https://github.com/pgvector/pgvector.git
cd pgvector
cmake -B build
cmake --build build --config Release
cmake --install build --config Release
```

3. 运行启动脚本：
```powershell
.\start.ps1
```

或者手动启动：

后端：
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -c "from app.database import init_db; init_db()"
uvicorn app.main:app --reload
```

前端：
```bash
cd frontend
npm install
npm start
```

4. 访问 http://localhost:4200

### 配置 API Keys

编辑 `backend\.env` 文件：
```env
OPENAI_API_KEY=sk-your-key-here
GEMINI_API_KEY=your-gemini-key
DEEPSEEK_API_KEY=your-deepseek-key
```

### 常见问题

**Q: pgvector 安装失败**
A: 确保 PostgreSQL 版本 >= 15，并且安装了 C++ 编译环境

**Q: 前端启动时 404 错误**
A: 确保后端服务已启动，检查 proxy.conf.json 配置

**Q: Whisper 模型下载慢**
A: 可以手动下载模型文件放到 ~/.cache/whisper 目录

**Q: 视频下载失败**
A: 更新 yt-dlp: `pip install --upgrade yt-dlp`
