#!/usr/bin/env bash
# 在 Debian/Ubuntu 上安装 Docker Engine 与 Compose 插件，并将当前用户加入 docker 组。
# 用法：sudo bash scripts/install-docker.sh
# 若需走代理：sudo -E bash scripts/install-docker.sh

set -euo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[ERROR] 请使用 root 运行：sudo bash scripts/install-docker.sh" >&2
  exit 1
fi

SUDO_USER_NAME="${SUDO_USER:-${USER:-}}"
export DEBIAN_FRONTEND=noninteractive

if [[ -n "${http_proxy:-}" || -n "${HTTP_PROXY:-}" ]]; then
  log "检测到代理：${http_proxy:-${HTTP_PROXY:-}}"
else
  log "未检测到代理环境变量；若下载慢可先用 export 设置 http_proxy，再 sudo -E 运行"
fi

log "更新 apt 软件源索引（可能需要 1～3 分钟）..."
apt-get update

log "安装基础依赖：ca-certificates curl gnupg ..."
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  log "下载 Docker 官方 GPG 密钥..."
  curl -fsSL --connect-timeout 30 --max-time 120 \
    https://download.docker.com/linux/debian/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
else
  log "Docker GPG 密钥已存在，跳过"
fi

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
ARCH="$(dpkg --print-architecture)"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

log "添加 Docker 源后再次更新 apt（可能需要 1～3 分钟）..."
apt-get update

log "安装 Docker Engine 与 Compose 插件（体积较大，请耐心等待）..."
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

log "启动并设置 Docker 开机自启..."
systemctl enable --now docker

if [[ -n "${SUDO_USER_NAME}" && "${SUDO_USER_NAME}" != "root" ]]; then
  usermod -aG docker "${SUDO_USER_NAME}"
  log "已将用户 ${SUDO_USER_NAME} 加入 docker 组。请重新登录或执行：newgrp docker"
fi

docker --version
docker compose version
log "Docker 安装完成"
