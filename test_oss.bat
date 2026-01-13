@echo off
echo ============================================
echo 阿里云 OSS 配置验证
echo ============================================
echo.

cd /d "%~dp0"
call .venv\Scripts\activate.bat
python scripts\test_oss_config.py

echo.
echo 按任意键关闭...
pause >nul
