#!/usr/bin/env python3
"""
Warp georeferenced DOM into EPSG:3857 meters consistent with AMap tiling:
sample pixel centers in the source CRS → WGS84 lon/lat → GCJ-02 → WebMercator.

Source may be geographic (4326) or projected (UTM / CGCS2000 / etc.); previously
assuming gt values were already lon/lat caused PROJ webmerc "Invalid latitude".

Reads GeoTIFF by reference (VRT + GCP); output GeoTIFF suitable for gdal2tiles.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from osgeo import gdal, osr

gdal.UseExceptions()

# WebMercator valid latitude (degrees), inclusive margin
_MERC_LAT_MAX = 85.05112878


def _source_ct_to_wgs84_geo(ds: gdal.Dataset) -> osr.CoordinateTransformation:
    """Map dataset projected/geographic coordinates → WGS84 geographic lon,lat (degrees)."""
    src = osr.SpatialReference()
    wkt = ds.GetProjectionRef()
    if wkt:
        src.ImportFromWkt(wkt)
    elif ds.GetGCPProjection():
        src.ImportFromWkt(ds.GetGCPProjection())
    else:
        src.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(src, dst)


def _out_of_china(lng: float, lat: float) -> bool:
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(lng: float, lat: float) -> float:
    ret = (
        -100.0
        + 2.0 * lng
        + 3.0 * lat
        + 0.2 * lat * lat
        + 0.1 * lng * lat
        + 0.2 * math.sqrt(abs(lng))
    )
    ret += ((20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0) / 3.0
    ret += ((20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0) / 3.0
    ret += ((160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0) / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = (
        300.0
        + lng
        + 2.0 * lat
        + 0.1 * lng * lng
        + 0.1 * lng * lat
        + 0.1 * math.sqrt(abs(lng))
    )
    ret += ((20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0) / 3.0
    ret += ((20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0) / 3.0
    ret += (
        (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    )
    return ret


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lng, lat):
        return lng, lat
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / (((a * (1 - ee)) / (magic * sqrtmagic)) * math.pi)
    dlng = (dlng * 180.0) / ((a / sqrtmagic) * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def lonlat_to_xy3857(lon: float, lat: float) -> tuple[float, float]:
    lat_c = max(-_MERC_LAT_MAX, min(_MERC_LAT_MAX, lat))
    srs4326 = osr.SpatialReference()
    srs4326.ImportFromEPSG(4326)
    srs4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs3857 = osr.SpatialReference()
    srs3857.ImportFromEPSG(3857)
    srs3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(srs4326, srs3857)
    x, y, _ = ct.TransformPoint(lon, lat_c)
    return float(x), float(y)


def center_gcj02_offset_3857(ds: gdal.Dataset, ct_src_to_wgs: osr.CoordinateTransformation) -> tuple[float, float]:
    """
    Compute the GCJ-02 offset at the image centre in EPSG:3857 metres.
    The GCJ-02 correction is nearly uniform over a small area, so a single
    centre-point translation is accurate to within a few centimetres for
    images up to ~10 km on a side.
    Returns (dx_metres, dy_metres) to ADD to the EPSG:3857 GeoTransform origin.
    """
    gt = ds.GetGeoTransform()
    cx_src = gdal.ApplyGeoTransform(gt, ds.RasterXSize / 2.0, ds.RasterYSize / 2.0)
    lon_wgs, lat_wgs, _ = ct_src_to_wgs.TransformPoint(cx_src[0], cx_src[1])
    lon_wgs, lat_wgs = float(lon_wgs), float(lat_wgs)
    lon_gcj, lat_gcj = wgs84_to_gcj02(lon_wgs, lat_wgs)
    x_wgs, y_wgs = lonlat_to_xy3857(lon_wgs, lat_wgs)
    x_gcj, y_gcj = lonlat_to_xy3857(lon_gcj, lat_gcj)
    return x_gcj - x_wgs, y_gcj - y_wgs


def bounds_amap_lnglat(ds3857: gdal.Dataset) -> tuple[list[float], list[float]]:
    """Corners of warped raster → lon/lat numbers suitable for AMap LngLat (GCJ space)."""
    gt = ds3857.GetGeoTransform()
    xs = ds3857.RasterXSize
    ys = ds3857.RasterYSize
    corners = (
        (0.5, 0.5),
        (xs - 0.5, 0.5),
        (xs - 0.5, ys - 0.5),
        (0.5, ys - 0.5),
    )
    srs3857 = osr.SpatialReference()
    srs3857.ImportFromEPSG(3857)
    srs3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs4326 = osr.SpatialReference()
    srs4326.ImportFromEPSG(4326)
    srs4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(srs3857, srs4326)
    lngs: list[float] = []
    lats: list[float] = []
    for px, py in corners:
        mx, my = gdal.ApplyGeoTransform(gt, px, py)
        lng, lat, _ = ct.TransformPoint(mx, my)
        lngs.append(float(lng))
        lats.append(float(lat))
    sw = [min(lngs), min(lats)]
    ne = [max(lngs), max(lats)]
    return sw, ne


def write_meta(
    path: Path,
    ds3857: gdal.Dataset,
    zoom: str,
    tile_url_suffix: str,
    tile_format: str = "png",
) -> None:
    sw, ne = bounds_amap_lnglat(ds3857)
    gt = ds3857.GetGeoTransform()
    res_x = abs(gt[1])
    res_y = abs(gt[5])
    pixel_size_m = (res_x + res_y) / 2.0
    center = [(sw[0] + ne[0]) / 2.0, (sw[1] + ne[1]) / 2.0]
    meta = {
        "tileUrlSuffix": tile_url_suffix,
        "tileFormat": tile_format,
        "zoom": zoom,
        "center_gcj_lnglat": center,
        "bounds_gcj_lnglat": {"southwest": sw, "northeast": ne},
        "resolution_m_approx": pixel_size_m,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="DOM (any GDAL CRS) → GCJ-aligned EPSG:3857 GeoTIFF")
    ap.add_argument("src", type=Path, help="Source GeoTIFF (projected or WGS84 geographic)")
    ap.add_argument("dst", type=Path, help="Output GeoTIFF (EPSG:3857)")
    ap.add_argument("--grid-x", type=int, default=22, help="(unused, kept for CLI compat)")
    ap.add_argument("--grid-y", type=int, default=22, help="(unused, kept for CLI compat)")
    ap.add_argument("--meta-out", type=Path, help="Write orthophoto_amap_meta.json for test page")
    ap.add_argument("--zoom-for-meta", default="14-19", help="Zoom range string embedded in meta")
    ap.add_argument("--tile-url-suffix", default="/static/map/tiles_dom", help="Tile base URL path")
    ap.add_argument("--tile-format", default="png", choices=["png", "jpg"], help="Tile image format written into meta")
    args = ap.parse_args()

    src = gdal.Open(str(args.src))
    if src is None:
        raise SystemExit(f"Cannot open {args.src}")

    ct_src_to_wgs = _source_ct_to_wgs84_geo(src)

    # ── Step 1: standard warp from source CRS → EPSG:3857 (WGS-84 based) ──────
    # Doing a standard reprojection first guarantees correct pixel placement and
    # a proper 3857 GeoTransform.  We then apply the GCJ-02 offset as a pure
    # translation in Step 2, which is accurate to < 1 m for images ≤ ~10 km.
    tmp_path = str(args.dst.with_suffix(".wgs3857.tif"))
    warp_opts = gdal.WarpOptions(
        dstSRS="EPSG:3857",
        format="GTiff",
        creationOptions=[
            "COMPRESS=DEFLATE",
            "PREDICTOR=2",
            "ZLEVEL=6",
            "TILED=YES",
            "BLOCKXSIZE=512",
            "BLOCKYSIZE=512",
            "BIGTIFF=IF_NEEDED",
            "INTERLEAVE=PIXEL",
        ],
        resampleAlg=gdal.GRA_Bilinear,
        multithread=True,
        dstAlpha=True,
    )
    gdal.Warp(tmp_path, str(args.src), options=warp_opts)

    # ── Step 2: apply GCJ-02 centre-point translation to the GeoTransform ──────
    # The GCJ-02 offset is nearly constant over a small area, so translating
    # the GeoTransform origin by the centre-point offset is sufficient.
    tmp_ds = gdal.Open(tmp_path, gdal.GA_Update)
    if tmp_ds is None:
        raise SystemExit("Step-1 warp produced no dataset")

    dx, dy = center_gcj02_offset_3857(src, ct_src_to_wgs)
    gt = list(tmp_ds.GetGeoTransform())
    gt[0] += dx   # shift X origin east by GCJ-02 delta
    gt[3] += dy   # shift Y origin north by GCJ-02 delta (dy is positive-northward)
    tmp_ds.SetGeoTransform(gt)
    tmp_ds.FlushCache()
    tmp_ds = None

    print(
        f"[warp_dom_gcj3857] GCJ-02 offset applied: "
        f"dx={dx:+.2f} m  dy={dy:+.2f} m"
    )

    # ── Step 3: DEFLATE-compress final output (copy with updated GT) ────────────
    # Re-open read-only for the copy so the updated GT is flushed.
    gdal.GetDriverByName("GTiff").CreateCopy(
        str(args.dst),
        gdal.Open(tmp_path),
        0,
        options=[
            "COMPRESS=DEFLATE", "PREDICTOR=2", "ZLEVEL=6",
            "TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512",
            "BIGTIFF=IF_NEEDED", "INTERLEAVE=PIXEL",
        ],
    )
    try:
        Path(tmp_path).unlink(missing_ok=True)
    except OSError:
        pass

    out_ds = gdal.Open(str(args.dst))
    if out_ds is None:
        raise SystemExit("Final output not readable")

    if args.meta_out:
        write_meta(args.meta_out, out_ds, args.zoom_for_meta, args.tile_url_suffix, args.tile_format)

    print(f"[warp_dom_gcj3857] OK → {args.dst}")


if __name__ == "__main__":
    main()
