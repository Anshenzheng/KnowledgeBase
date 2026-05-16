# 后端服务启动指南

## 前置要求

### 1. PostgreSQL 数据库

必须安装并启动 PostgreSQL 12+ 数据库服务。

#### Windows 启动 PostgreSQL:

```powershell
# 方法 1: 使用服务管理器
Get-Service postgresql*
Start-Service postgresql-x64-15  # 根据你的版本号调整

# 方法 2: 使用 pg_ctl
& "C:\Program Files\PostgreSQL\15\bin\pg_ctl.exe" -D "C:\Program Files\PostgreSQL\15\data" start
```

#### 验证 PostgreSQL 是否运行:

```powershell
# 检查服务状态
Get-Service postgresql*

# 检查端口
netstat -ano | findstr :5432
```

### 2. 数据库配置

确保已创建数据库和用户：

```sql
-- 以 postgres 用户连接
psql -U postgres

-- 创建数据库
CREATE DATABASE knowledge_base;

-- 创建用户（如果需要）
CREATE USER knowledge_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE knowledge_base TO knowledge_user;
```

### 3. 配置文件

检查 `.env` 文件配置是否正确：

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=knowledge_base
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password
```

## 启动后端服务

### 方法 1: 使用虚拟环境（推荐）

```powershell
cd backend
.\venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 方法 2: 直接使用虚拟环境的 Python

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 验证服务启动

### 1. 检查健康状态

```powershell
curl http://localhost:8000/health
```

预期响应：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected"
}
```

如果 `database` 显示 `disconnected`，请检查 PostgreSQL 是否运行。

### 2. 访问 API 文档

浏览器打开：http://localhost:8000/docs

### 3. 测试模型 API

```powershell
curl http://localhost:8000/api/models
```

## 常见问题

### 问题 1: 端口 8000 被占用

**错误**: `error while attempting to bind on address ('0.0.0.0', 8000)`

**解决**:
```powershell
# 查找占用端口的进程
netstat -ano | findstr :8000

# 终止进程（替换 PID）
taskkill /F /PID <PID>
```

### 问题 2: 数据库连接失败

**错误**: `connection to server at "localhost", port 5432 failed: Connection refused`

**解决**:
1. 启动 PostgreSQL 服务
2. 检查 `.env` 配置
3. 确认数据库存在

### 问题 3: psycopg2 模块未找到

**错误**: `ModuleNotFoundError: No module named 'psycopg2'`

**解决**:
```powershell
cd backend
.\venv\Scripts\pip install psycopg2-binary
```

## 服务优化

### 延迟加载说明

应用现在使用延迟加载策略：
- 数据库引擎在第一次使用时才创建
- 嵌入模型在第一次使用时才加载
- 应用启动不阻塞，即使数据库不可用也能启动

### 功能限制

如果 PostgreSQL 未启动，应用仍可启动，但以下功能不可用：
- 模型配置管理
- 聊天对话
- 知识库导入
- 任务管理

健康检查会显示 `database: disconnected`

## 完整启动流程

1. ✅ 启动 PostgreSQL 服务
2. ✅ 验证数据库连接
3. ✅ 启动后端服务
4. ✅ 检查健康状态
5. ✅ 访问 API 文档测试
