#!/usr/bin/env bash
# WGS84 DOM → GCJ/WebMercator GeoTIFF → XYZ PNG tiles for AMap overlay test.
# PNG preserves the alpha channel so tile edges are transparent (no black border).
# Requires Docker image with GDAL + Python GDAL (see scripts/gdal-run.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${GDAL_DOCKER_IMAGE:-ova1v2yit7sl2c-ghcr.xuanyuan.run/osgeo/gdal:ubuntu-full-latest}"

SRC="${1:-static/map/result_master_jpeg.tif}"
WARPED="${2:-static/map/result_warp_gcj3857.tif}"
OUTDIR="${3:-static/map/tiles_dom}"
ZOOM="${ZOOM:-14-19}"

run_docker() {
  docker run --rm \
    -v "$ROOT:/work" \
    -w /work \
    "$IMAGE" \
    "$@"
}

echo "[tile_dom_gcj_amap] warp $SRC → $WARPED (DEFLATE+alpha) …"
run_docker python3 scripts/warp_dom_gcj3857.py \
  "$SRC" "$WARPED" \
  --meta-out static/map/orthophoto_amap_meta.json \
  --zoom-for-meta "$ZOOM" \
  --tile-url-suffix "/static/map/tiles_dom" \
  --tile-format png

echo "[tile_dom_gcj_amap] gdal2tiles z=$ZOOM → $OUTDIR (PNG) …"
rm -rf "$ROOT/$OUTDIR"
mkdir -p "$ROOT/$OUTDIR"

run_docker gdal2tiles.py \
  --xyz \
  --zoom="$ZOOM" \
  --webviewer=none \
  --quiet \
  --tilesize=256 \
  --tiledriver=PNG \
  --resampling=bilinear \
  "$WARPED" "$OUTDIR"

echo "[tile_dom_gcj_amap] done. Open backend /orthophoto-test (requires tiles + meta)."
