@echo off
chcp 65001 > nul
echo ========================================
echo   即梦4.0图片生成器 - 快速启动
echo ========================================
echo.

REM 激活虚拟环境
call venv\Scripts\activate.bat

echo [✓] 虚拟环境已激活
echo.

REM 检查.env配置文件
if not exist .env (
    echo [!] 警告：未找到.env配置文件
    echo     请先复制.env.example为.env并填写您的API密钥
    echo.
    pause
    exit /b 1
)

echo [✓] 配置文件存在
echo.

REM 启动Web应用
echo [*] 正在启动Web应用...
echo     访问地址：http://localhost:5000
echo.
echo     按 Ctrl+C 停止服务器
echo.
echo ========================================
python web_app.py

pause
