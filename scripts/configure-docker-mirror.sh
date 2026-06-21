#!/usr/bin/env bash
# 配置轩辕 Docker 镜像加速（daemon.json + docker-compose.override.yml）
# 用法：
#   sudo bash scripts/configure-docker-mirror.sh
#   sudo bash scripts/configure-docker-mirror.sh ova1v2yit7sl2c.xuanyuan.run
# 若 apt/curl 需代理：sudo -E bash scripts/configure-docker-mirror.sh

set -euo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }

MIRROR_DOMAIN="${1:-ova1v2yit7sl2c.xuanyuan.run}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OVERRIDE_FILE="${PROJECT_DIR}/docker-compose.override.yml"

# 保留已有代理配置（若 daemon.json 里已配置）
HTTP_PROXY_VAL=""
HTTPS_PROXY_VAL=""
NO_PROXY_VAL="localhost,127.0.0.1"
if [[ -f /etc/docker/daemon.json ]]; then
  HTTP_PROXY_VAL="$(python3 -c "import json; d=json.load(open('/etc/docker/daemon.json')); print(d.get('proxies',{}).get('http-proxy',''))" 2>/dev/null || true)"
  HTTPS_PROXY_VAL="$(python3 -c "import json; d=json.load(open('/etc/docker/daemon.json')); print(d.get('proxies',{}).get('https-proxy',''))" 2>/dev/null || true)"
fi
# 环境变量优先（sudo -E 时）
HTTP_PROXY_VAL="${HTTP_PROXY:-${http_proxy:-${HTTP_PROXY_VAL}}}"
HTTPS_PROXY_VAL="${HTTPS_PROXY:-${https_proxy:-${HTTPS_PROXY_VAL}}}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  log "生成 compose 覆盖文件（无需 root）..."
else
  log "写入 /etc/docker/daemon.json（镜像：${MIRROR_DOMAIN}）..."

  if [[ -n "${HTTP_PROXY_VAL}" ]]; then
    HTTPS_EFFECTIVE="${HTTPS_PROXY_VAL:-${HTTP_PROXY_VAL}}"
    MIRROR_DOMAIN="${MIRROR_DOMAIN}" \
    HTTP_PROXY_VAL="${HTTP_PROXY_VAL}" \
    HTTPS_EFFECTIVE="${HTTPS_EFFECTIVE}" \
    NO_PROXY_VAL="${NO_PROXY_VAL}" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

data = {
    "insecure-registries": [os.environ["MIRROR_DOMAIN"]],
    "registry-mirrors": [f"https://{os.environ['MIRROR_DOMAIN']}"],
    "proxies": {
        "http-proxy": os.environ["HTTP_PROXY_VAL"],
        "https-proxy": os.environ["HTTPS_EFFECTIVE"],
        "no-proxy": os.environ["NO_PROXY_VAL"],
    },
}
Path("/etc/docker/daemon.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
    log "已保留 HTTP 代理：${HTTP_PROXY_VAL}"
  else
    MIRROR_DOMAIN="${MIRROR_DOMAIN}" python3 - <<'PY'
import json
import os
from pathlib import Path

data = {
    "insecure-registries": [os.environ["MIRROR_DOMAIN"]],
    "registry-mirrors": [f"https://{os.environ['MIRROR_DOMAIN']}"],
}
Path("/etc/docker/daemon.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
  fi

  log "重启 Docker 服务..."
  systemctl daemon-reload
  systemctl restart docker
  docker info | grep -A3 "Registry Mirrors" || true
fi

log "生成 ${OVERRIDE_FILE} ..."
cat > "${OVERRIDE_FILE}" <<EOF
# 由 scripts/configure-docker-mirror.sh 自动生成，勿提交 git
# 显式走轩辕专属域名，避免 registry-mirrors 回退 docker.io 超时

services:
  redis:
    image: ${MIRROR_DOMAIN}/library/redis:7-alpine

  postgres:
    image: ${MIRROR_DOMAIN}/library/postgres:16-alpine

  nginx:
    image: ${MIRROR_DOMAIN}/library/nginx:alpine

  app:
    build:
      context: .
      args:
        PYTHON_IMAGE: ${MIRROR_DOMAIN}/library/python:3.12-slim
EOF

log "完成。接下来执行："
echo "  docker compose --profile local-db up -d"
echo ""
echo "手动验证拉取："
echo "  docker pull ${MIRROR_DOMAIN}/library/redis:7-alpine"
