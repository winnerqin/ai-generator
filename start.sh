#!/bin/bash

# 配置
APP_DIR="/opt/ai_generator"
VENV_DIR="$APP_DIR/venv"
APP_SCRIPT="app_factory.py"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/app.pid"
PORT=8090

# 创建日志目录
mkdir -p $LOG_DIR

# 检查端口是否被占用
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "Port $PORT is already in use"
    echo "Try to stop existing process first"
    exit 1
fi

# 进入项目目录
cd $APP_DIR || exit

# 激活虚拟环境
if [ -d "$VENV_DIR" ]; then
    echo "Activating virtual environment..."
    source $VENV_DIR/bin/activate
else
    echo "Virtual environment not found at $VENV_DIR"
    exit 1
fi

# 生成日志文件名（按日期）
DATE=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/app_$DATE.log"

# 启动应用
echo "Starting application on port $PORT..."
nohup python3 $APP_SCRIPT > $LOG_FILE 2>&1 &

# 保存PID
PID=$!
echo $PID > $PID_FILE

echo "Application started with PID: $PID"
echo "Log file: $LOG_FILE"
echo "Check logs with: tail -f $LOG_FILE"

# 等待一下，检查是否启动成功
sleep 2
if kill -0 $PID 2>/dev/null; then
    echo "Application is running successfully"
else
    echo "Application failed to start. Check log file: $LOG_FILE"
    exit 1
fi
