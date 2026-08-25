#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="test/8091"
REPOSITORY_URL="https://github.com/winnerqin/ai-generator.git"
SOURCE_DIR="/home/ubuntu/content/ai_generator_test"
DEPLOY_DIR="/opt/ai_generator_test"
PORT="8091"

log() {
    printf '[deploy-test-8091] %s\n' "$*"
}

if ! command -v git >/dev/null 2>&1; then
    log "错误：未安装 git。"
    exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
    log "错误：未安装 rsync。"
    exit 1
fi

mkdir -p "$(dirname "$SOURCE_DIR")"

if [[ -d "$SOURCE_DIR/.git" ]]; then
    log "更新源码：$SOURCE_DIR ($BRANCH)"
    git -C "$SOURCE_DIR" fetch origin "$BRANCH"
    git -C "$SOURCE_DIR" switch "$BRANCH"
    git -C "$SOURCE_DIR" pull --ff-only origin "$BRANCH"
elif [[ -e "$SOURCE_DIR" ]]; then
    log "错误：$SOURCE_DIR 已存在，但不是 Git 仓库。"
    exit 1
else
    log "首次拉取源码：$REPOSITORY_URL"
    git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$SOURCE_DIR"
fi

log "同步代码到 $DEPLOY_DIR"
sudo mkdir -p "$DEPLOY_DIR"
sudo rsync -av \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='run.sh' \
    "$SOURCE_DIR/" "$DEPLOY_DIR/"

if [[ ! -f "$DEPLOY_DIR/run.sh" ]]; then
    log "错误：$DEPLOY_DIR/run.sh 不存在；请先在服务器部署目录中配置启动脚本。"
    exit 1
fi

mapfile -t LISTENER_PIDS < <(
    sudo ss -H -ltnp "sport = :$PORT" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' \
        | cut -d= -f2 \
        | sort -u
)

if ((${#LISTENER_PIDS[@]})); then
    log "停止端口 $PORT 的旧进程：${LISTENER_PIDS[*]}"
    sudo kill -TERM "${LISTENER_PIDS[@]}"

    for _ in {1..20}; do
        if ! sudo ss -H -ltn "sport = :$PORT" 2>/dev/null | grep -q .; then
            break
        fi
        sleep 0.5
    done

    mapfile -t REMAINING_PIDS < <(
        sudo ss -H -ltnp "sport = :$PORT" 2>/dev/null \
            | grep -oE 'pid=[0-9]+' \
            | cut -d= -f2 \
            | sort -u
    )
    if ((${#REMAINING_PIDS[@]})); then
        log "旧进程未及时退出，强制停止：${REMAINING_PIDS[*]}"
        sudo kill -KILL "${REMAINING_PIDS[@]}"
    fi
else
    log "端口 $PORT 当前没有监听进程。"
fi

log "执行 $DEPLOY_DIR/run.sh"
cd "$DEPLOY_DIR"
sudo bash ./run.sh

log "部署命令执行完成。"
