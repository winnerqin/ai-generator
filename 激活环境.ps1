Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Generator - 虚拟环境激活" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "[X] 未找到虚拟环境" -ForegroundColor Red
    Write-Host "    请先运行: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "[*] 正在激活虚拟环境..." -ForegroundColor Yellow
. .\venv\Scripts\Activate.ps1

Write-Host "[OK] 虚拟环境已激活" -ForegroundColor Green
Write-Host ""
Write-Host "常用命令:" -ForegroundColor Cyan
Write-Host "  - 启动应用: python app_factory.py" -ForegroundColor White
Write-Host "  - 查看依赖: pip list" -ForegroundColor White
Write-Host "  - 安装依赖: pip install -r requirements.txt" -ForegroundColor White
Write-Host "  - 运行测试: python -m pytest -q" -ForegroundColor White
Write-Host "  - 退出环境: deactivate" -ForegroundColor White
Write-Host ""
