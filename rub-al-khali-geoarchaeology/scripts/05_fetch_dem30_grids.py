"""Step 5 - 30 m DEM and the analysis grids (UTM 40N).

Downloads the 16 Copernicus GLO-30 tiles that touch the corridor (~630 MB), mosaics
them, and reprojects:
  * GLO-30 -> 30 m grid over the download box          (data/interim/dem30_utm.tif)
  * GLO-90 -> 90 m grid over the context box           (data/interim/dem90_utm.tif)
and rasterises the corridor onto the 30 m, 90 m and 1 km grids.

Grid definitions are written to config/grids.json and read by later steps via common.grid().
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject, transform_bounds

from common import (CONFIG, INTERIM, OUTPUTS, PROCESSED, RAW, UTM, download, human_bytes,
                    load_yaml, write_raster)

cfg = load_yaml("aoi.yaml")
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())


def snap_grid(bounds_ll, res):
    """UTM grid (transform, width, height) covering lon/lat bounds, snapped to res."""
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", UTM, *bounds_ll, densify_pts=50)
    x0, y0 = np.floor(x0 / res) * res, np.floor(y0 / res) * res
    x1, y1 = np.ceil(x1 / res) * res, np.ceil(y1 / res) * res
    w, h = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    return rasterio.transform.from_origin(x0, y1, res, res), w, h


grids = {}
for name, bnds, res in [("g30", summary["download_bbox_wsen"], 30),
                        ("g90", summary["context_bbox_wsen"], 90),
                        ("g1km", summary["download_bbox_wsen"], 1000)]:
    t, w, h = snap_grid(bnds, res)
    grids[name] = {"crs": UTM, "res": res, "transform": list(t)[:6], "width": w, "height": h}
    print(f"{name}: {w} x {h} cells at {res} m")
(CONFIG / "grids.json").write_text(json.dumps(grids, indent=2))

# ------------------------------------------------------------------ download GLO-30 tiles
jobs = []
for code in summary["dem30_tiles"]:            # e.g. 'N18E053'
    la, lo = int(code[1:3]), int(code[4:7])
    name = f"Copernicus_DSM_COG_10_N{la:02d}_00_E{lo:03d}_00_DEM"
    jobs.append((f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif",
                 RAW / "dem30" / f"{name}.tif"))
with ThreadPoolExecutor(4) as ex:
    sizes = list(ex.map(lambda j: download(*j), jobs))
print(f"GLO-30: {len(jobs)} tiles, {human_bytes(sum(sizes))}")


def to_grid(src_arr, src_t, src_crs, name, resampling=Resampling.bilinear):
    t = rasterio.transform.Affine(*grids[name]["transform"])
    out = np.full((grids[name]["height"], grids[name]["width"]), np.nan, np.float32)
    reproject(src_arr, out, src_transform=src_t, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=t, dst_crs=UTM, dst_nodata=np.nan, resampling=resampling,
              num_threads=4)
    return out, t


# ------------------------------------------------------------------ 30 m DEM in UTM
srcs = [rasterio.open(p) for _, p in jobs]
w, s, e, n = summary["download_bbox_wsen"]
mosaic, mt = merge(srcs, bounds=(w - 0.02, s - 0.02, e + 0.02, n + 0.02), nodata=np.nan,
                   dtype="float32")
for src in srcs:
    src.close()
dem30, t30 = to_grid(mosaic[0], mt, "EPSG:4326", "g30")
del mosaic
write_raster(INTERIM / "dem30_utm.tif", dem30, t30)
print("dem30_utm:", dem30.shape, "range", np.nanmin(dem30), np.nanmax(dem30),
      f"{np.isnan(dem30).mean() * 100:.2f}% NaN")
del dem30

# ------------------------------------------------------------------ 90 m DEM (context) in UTM
with rasterio.open(INTERIM / "dem90_context.tif") as src:
    a90 = src.read(1).astype("float32")
    if src.nodata is not None:
        a90[a90 == src.nodata] = np.nan
    dem90, t90 = to_grid(a90, src.transform, src.crs, "g90")
write_raster(INTERIM / "dem90_utm.tif", dem90, t90)
print("dem90_utm:", dem90.shape)

# ------------------------------------------------------------------ corridor masks
corr = gpd.read_file(PROCESSED / "aoi_corridor.geojson")
geom = corr.loc[corr["name"] == "corridor"].to_crs(UTM).geometry.iloc[0]
for name in ("g30", "g90", "g1km"):
    t = rasterio.transform.Affine(*grids[name]["transform"])
    m = rasterize([(geom, 1)], out_shape=(grids[name]["height"], grids[name]["width"]),
                  transform=t, fill=0, dtype="uint8", all_touched=(name == "g1km"))
    write_raster(INTERIM / f"corridor_mask_{name}.tif", m, t, nodata=0)
    print(f"corridor mask {name}: {m.sum():,} cells")
