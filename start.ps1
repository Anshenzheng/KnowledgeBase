# 智能知识仓库 Agent - 启动脚本

Write-Host "================================" -ForegroundColor Cyan
Write-Host "智能知识仓库 Agent 启动脚本" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
Write-Host "检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# 检查 Node.js
Write-Host "检查 Node.js 环境..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ 未找到 Node.js，请先安装 Node.js 18+" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "启动后端服务..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 启动后端
$backendPath = Join-Path $PSScriptRoot "backend"
if (Test-Path $backendPath) {
    Set-Location $backendPath
    
    # 检查虚拟环境
    if (-not (Test-Path "venv")) {
        Write-Host "创建 Python 虚拟环境..." -ForegroundColor Yellow
        python -m venv venv
    }
    
    # 激活虚拟环境
    Write-Host "激活 Python 虚拟环境..." -ForegroundColor Yellow
    & ".\venv\Scripts\Activate.ps1"
    
    # 检查依赖
    Write-Host "检查 Python 依赖..." -ForegroundColor Yellow
    pip install -r requirements.txt
    
    # 初始化数据库
    Write-Host "初始化数据库..." -ForegroundColor Yellow
    python -c "from app.database import init_db; init_db()"
    
    # 启动 FastAPI
    Write-Host "启动 FastAPI 服务 (端口 8000)..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; .\venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    
    Write-Host "✓ 后端服务已启动" -ForegroundColor Green
    Write-Host "  API 文档：http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "✗ 后端目录不存在" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "启动前端服务..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 启动前端
$frontendPath = Join-Path $PSScriptRoot "frontend"
if (Test-Path $frontendPath) {
    Set-Location $frontendPath
    
    # 检查 node_modules
    if (-not (Test-Path "node_modules")) {
        Write-Host "安装 NPM 依赖 (首次运行可能需要几分钟)..." -ForegroundColor Yellow
        npm install
    }
    
    # 启动 Angular
    Write-Host "启动 Angular 开发服务器 (端口 4200)..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; npm start"
    
    Write-Host "✓ 前端服务已启动" -ForegroundColor Green
    Write-Host "  访问地址：http://localhost:4200" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "✗ 前端目录不存在" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "所有服务已启动!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "后端 API:  http://localhost:8000" -ForegroundColor Cyan
Write-Host "前端界面：http://localhost:4200" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出此窗口..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
