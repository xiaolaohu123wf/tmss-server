#!/usr/bin/env bash
# 启动 Vite 开发服务器
# 系统默认 Node v10 太旧，自动寻找 Node 18+ 可用路径

set -e

# 1. 优先使用系统安装的 node20 / node18
for BIN in node20 node18 node; do
  NODEPATH=$(command -v "$BIN" 2>/dev/null || true)
  if [ -n "$NODEPATH" ]; then
    VERSION=$("$NODEPATH" --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
    if [ "$VERSION" -ge 18 ] 2>/dev/null; then
      echo "[dev.sh] 使用 Node: $NODEPATH (v$VERSION)"
      exec "$NODEPATH" ./node_modules/vite/bin/vite.js "$@"
    fi
  fi
done

# 2. 回退到 Cursor 自带的 Node 20
CURSOR_NODE=$(find /root/.cursor-server/bin/linux-x64 -name "node" -type f 2>/dev/null | head -1)
if [ -n "$CURSOR_NODE" ]; then
  VERSION=$("$CURSOR_NODE" --version | sed 's/v//' | cut -d. -f1)
  echo "[dev.sh] 使用 Cursor Node: $CURSOR_NODE (v$VERSION)"
  exec "$CURSOR_NODE" ./node_modules/vite/bin/vite.js "$@"
fi

echo "[dev.sh] 错误: 未找到 Node 18+ 版本，请先安装："
echo "  sudo dnf module enable nodejs:20 -y && sudo dnf install nodejs -y"
exit 1
