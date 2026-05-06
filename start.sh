#!/usr/bin/env bash
# TMSS 后台启动脚本
# 用法：
#   bash start.sh          # 后台启动（追加日志）
#   bash start.sh restart  # 先停止旧进程再启动
#   bash start.sh stop     # 停止服务
#   bash start.sh status   # 查看运行状态
#   bash start.sh log      # 实时查看日志

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/backend.log"
VENV="$SCRIPT_DIR/.venv/bin/activate"
PID_FILE="$SCRIPT_DIR/.tmss.pid"

# ── 激活虚拟环境 ──────────────────────────────────
if [[ -f "$VENV" ]]; then
    source "$VENV"
else
    echo "[ERROR] 虚拟环境不存在：$VENV" >&2
    exit 1
fi

# ── 查找正在运行的 TMSS 进程 ──────────────────────
find_pid() {
    pgrep -f "python.*-m app.main" 2>/dev/null | head -1 || true
}

# ── 停止服务 ──────────────────────────────────────
do_stop() {
    local pid
    pid=$(find_pid)
    if [[ -n "$pid" ]]; then
        echo "[INFO] 停止 TMSS (PID $pid)..."
        kill "$pid"
        local i=0
        while kill -0 "$pid" 2>/dev/null && (( i < 10 )); do
            sleep 1; i=$(( i + 1 ))
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "[WARN] 进程未在10秒内退出，强制终止..."
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo "[INFO] 服务已停止"
    else
        echo "[INFO] TMSS 未在运行"
    fi
}

# ── 查看状态 ──────────────────────────────────────
do_status() {
    local pid
    pid=$(find_pid)
    if [[ -n "$pid" ]]; then
        echo "[OK] TMSS 正在运行 (PID $pid)"
        ss -tlnp 2>/dev/null | grep -E '890[01]' | awk '{print "       监听: "$1,$4,$5}'
    else
        echo "[--] TMSS 未在运行"
    fi
}

# ── 启动服务 ──────────────────────────────────────
do_start() {
    local pid
    pid=$(find_pid)
    if [[ -n "$pid" ]]; then
        echo "[WARN] TMSS 已在运行 (PID $pid)，如需重启请用 bash start.sh restart"
        return 0
    fi

    cd "$SCRIPT_DIR"

    # 在日志中写入启动分隔线，方便区分每次运行
    {
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo " TMSS 启动  $(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "════════════════════════════════════════════════════════════"
    } >> "$LOG_FILE"

    # 自动应用数据库迁移（幂等，多次执行无副作用）
    echo "[INFO] 执行数据库迁移..."
    if ! alembic upgrade head >> "$LOG_FILE" 2>&1; then
        echo "[ERROR] 数据库迁移失败，请查看日志：tail -n 50 $LOG_FILE" >&2
        exit 1
    fi
    echo "[INFO] 迁移完成"

    nohup python -m app.main >> "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # 等待最多5秒确认进程未立即崩溃
    sleep 2
    if ! kill -0 "$new_pid" 2>/dev/null; then
        echo "[ERROR] 启动失败，请查看日志：tail -n 50 $LOG_FILE"
        exit 1
    fi

    echo "[OK] TMSS 已启动 (PID $new_pid)"
    echo "      HTTP API : http://0.0.0.0:8900"
    echo "      TCP      : 0.0.0.0:8901"
    echo "      日志     : $LOG_FILE"
    echo ""
    echo "  实时日志：tail -f $LOG_FILE"
    echo "  停止服务：bash start.sh stop"
}

# ── 入口 ──────────────────────────────────────────
CMD="${1:-start}"
case "$CMD" in
    start)   do_start  ;;
    stop)    do_stop   ;;
    restart) do_stop; sleep 1; do_start ;;
    status)  do_status ;;
    log)     tail -f "$LOG_FILE" ;;
    *)
        echo "用法：bash start.sh [start|stop|restart|status|log]"
        exit 1
        ;;
esac
