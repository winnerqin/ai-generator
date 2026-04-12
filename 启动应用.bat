@echo off
chcp 65001 > nul
echo ========================================
echo   AI Generator - 快速启动
echo ========================================
echo.

call venv\Scripts\activate.bat

if not exist .env (
    echo [!] 未找到 .env 配置文件
    echo     请先复制 .env.example 为 .env 并填写所需密钥
    echo.
    pause
    exit /b 1
)

echo [*] 正在启动应用...
echo     访问地址: http://localhost:8090
echo     按 Ctrl+C 停止服务
echo.

python app_factory.py

pause
