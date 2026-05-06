#!/usr/bin/env bash
# JPEG-compressed GeoTIFF from drone DOM; CRS unchanged (e.g. WGS84).
# Default: JPEG_QUALITY=65, warn if output exceeds MAX_MB (200).
# Usage: ./scripts/compress_dom_master.sh [input.tif] [output.tif]
# Env: JPEG_QUALITY (default 65), MAX_MB (default 200).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/scripts/gdal-run.sh"

INPUT="${1:-$ROOT/static/map/result.tif}"
OUTPUT="${2:-$ROOT/static/map/result_master_jpeg.tif}"
MAX_MB="${MAX_MB:-200}"
JPEG_QUALITY="${JPEG_QUALITY:-65}"

if [[ ! -f "$INPUT" ]]; then
  echo "Missing input: $INPUT" >&2
  exit 1
fi
case "$INPUT" in
"$ROOT"/*) ;;
*)
  echo "Input must be under repo root: $ROOT" >&2
  exit 1
  ;;
esac

case "$OUTPUT" in
"$ROOT"/*) ;;
*)
  echo "Output must be under repo root: $ROOT" >&2
  exit 1
  ;;
esac

rel_in="${INPUT#$ROOT/}"
rel_out="${OUTPUT#$ROOT/}"

need_byte_opts=false
if "$RUN" gdalinfo "$rel_in" | grep -qE 'Type=UInt16|Type=Int16'; then
  need_byte_opts=true
fi

byte_opts=()
if [[ "$need_byte_opts" == true ]]; then
  echo "[compress_dom_master] 16-bit detected: using -ot Byte -scale 0 65535 0 255 (may need manual stretch)"
  byte_opts=(-ot Byte -scale 0 65535 0 255)
fi

echo "[compress_dom_master] JPEG_QUALITY=$JPEG_QUALITY ..."
"$RUN" gdal_translate -q -of GTiff \
  "${byte_opts[@]}" \
  -co "COMPRESS=JPEG" -co "JPEG_QUALITY=$JPEG_QUALITY" \
  -co PHOTOMETRIC=RGB \
  -co TILED=YES -co BLOCKXSIZE=512 -co BLOCKYSIZE=512 \
  -co BIGTIFF=IF_NEEDED \
  -co INTERLEAVE=PIXEL \
  "$rel_in" "$rel_out"

sz=$(stat -c%s "$OUTPUT")
mb=$((sz / 1048576))
echo "[compress_dom_master] size=${mb}MB path=$OUTPUT"

if [[ "$mb" -le "$MAX_MB" ]]; then
  echo "[compress_dom_master] OK (≤ ${MAX_MB}MB)"
  exit 0
fi

echo "[compress_dom_master] WARN: above ${MAX_MB}MB at JPEG_QUALITY=$JPEG_QUALITY; use gdal_translate -outsize pct pct or lower JPEG_QUALITY." >&2
exit 1
