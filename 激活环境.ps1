# 激活虚拟环境（PowerShell脚本）

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  即梦4.0图片生成器 - 虚拟环境激活" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查虚拟环境是否存在
if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "[×] 错误：虚拟环境未找到" -ForegroundColor Red
    Write-Host "    请先运行：python -m venv venv" -ForegroundColor Yellow
    exit 1
}

# 激活虚拟环境
Write-Host "[*] 正在激活虚拟环境..." -ForegroundColor Yellow
. .\venv\Scripts\Activate.ps1

Write-Host "[✓] 虚拟环境已激活" -ForegroundColor Green
Write-Host ""
Write-Host "提示：" -ForegroundColor Cyan
Write-Host "  - 启动Web应用：python web_app.py" -ForegroundColor White
Write-Host "  - 查看已安装包：pip list" -ForegroundColor White
Write-Host "  - 安装依赖包：pip install -r requirements.txt" -ForegroundColor White
Write-Host "  - 退出虚拟环境：deactivate" -ForegroundColor White
Write-Host ""
