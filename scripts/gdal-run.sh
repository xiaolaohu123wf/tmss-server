#!/usr/bin/env bash
# Run GDAL CLI from Docker when host has no gdal-bin.
# Default image via GHCR mirror (override with GDAL_DOCKER_IMAGE).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${GDAL_DOCKER_IMAGE:-ova1v2yit7sl2c-ghcr.xuanyuan.run/osgeo/gdal:ubuntu-full-latest}"

if command -v gdalinfo >/dev/null 2>&1; then
  exec "$@"
else
  exec docker run --rm \
    -v "$ROOT:/work" \
    -w /work \
    "$IMAGE" \
    "$@"
fi
