"""Step 2 - small downloads for the study-area preview map (~140 MB DEM + ~150 MB of overviews).

  * Copernicus GLO-90 DEM tiles for the context box (also reused later for the
    regional groundwater-path analysis), mosaicked to one GeoTIFF.
  * A ~200 m Sentinel-2 L2A surface-reflectance mosaic (B02 B03 B04 B8A B11 B12) of the
    download box, read from the internal overviews of the clearest winter 2024/25 scenes.

Outputs: data/raw/dem90/*.tif, data/interim/dem90_context.tif,
         data/interim/s2_overview_mosaic.tif, outputs/s2_overview_scenes.json
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
import requests
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject

from common import INTERIM, OUTPUTS, RAW, load_yaml, write_json, human_bytes
import s2_catalog

cfg = load_yaml("aoi.yaml")
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())


def download(url: str, dest) -> int:
    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.rename(dest)
    return dest.stat().st_size


# ------------------------------------------------------------------ GLO-90 DEM
w, s, e, n = cfg["context_bbox"]
jobs = []
for la in range(math.floor(s), math.ceil(n)):
    for lo in range(math.floor(w), math.ceil(e)):
        name = f"Copernicus_DSM_COG_30_N{la:02d}_00_E{lo:03d}_00_DEM"
        jobs.append((f"https://copernicus-dem-90m.s3.amazonaws.com/{name}/{name}.tif",
                     RAW / "dem90" / f"{name}.tif"))
with ThreadPoolExecutor(6) as ex:
    sizes = list(ex.map(lambda j: download(*j), jobs))
print(f"GLO-90: {len(jobs)} tiles, {human_bytes(sum(sizes))}")

srcs = [rasterio.open(p) for _, p in jobs]
mosaic, transform = merge(srcs, bounds=(w, s, e, n))
prof = srcs[0].profile.copy()
prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
            driver="GTiff", compress="deflate", predictor=3, tiled=True,
            blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
with rasterio.open(INTERIM / "dem90_context.tif", "w", **prof) as dst:
    dst.write(mosaic)
for src in srcs:
    src.close()
print("DEM mosaic:", mosaic.shape, "elev range", float(np.nanmin(mosaic)), float(np.nanmax(mosaic)))

# ------------------------------------------------------------------ Sentinel-2 overview mosaic
# Low-resolution (~200 m) surface-reflectance mosaic read from the COG overviews of the
# clearest winter 2024/25 scenes. Partial (swath-edge) scenes are completed from the next
# best date. ~1 MB per band per scene.
months = [(2025, 1), (2024, 12), (2025, 2)]
bands = ["B02", "B03", "B04", "B8A", "B11", "B12"]
res = 0.002
bw, bs, be, bn = summary["download_bbox_wsen"]
W, H = int(round((be - bw) / res)), int(round((bn - bs) / res))
dst_t = rasterio.transform.from_origin(bw, bn, res, res)
mos = np.full((len(bands), H, W), np.nan, np.float32)
scene_log = {}


def _minutes(iso):
    return int(iso[11:13]) * 60 + int(iso[14:16])


def tile_layers(tile):
    """Best scene per tile; if it is a partial swath, add the best scene from the other
    orbit (different overpass time), which covers the missing part of the tile."""
    out = []
    for sc in s2_catalog.ranked_scenes(tile, months):
        if any(abs(_minutes(sc.datetime) - _minutes(u.datetime)) <= 3 for u, _ in out):
            continue  # same orbit as a scene already used -> same gap
        layers = [s2_catalog.read_reflectance(sc, b, out_shape=(549, 549)) for b in bands]
        out.append((sc, layers))
        if sc.nodata < 1.0 or len(out) >= 3:
            break
    return tile, out


with ThreadPoolExecutor(4) as ex:
    results = list(ex.map(tile_layers, summary["sentinel2_mgrs_tiles"]))

for tile, scene_layers in results:
    scene_log[tile] = []
    for sc, layers in scene_layers:
        scene_log[tile].append({"scene": sc.scene_id, "datetime": sc.datetime, "cloud_pct": sc.cloud,
                                "nodata_pct": sc.nodata, "sun_elevation": round(sc.sun_elev, 1)})
        for i, (arr, tr, crs) in enumerate(layers):
            tmp = np.full((H, W), np.nan, np.float32)
            reproject(arr, tmp, src_transform=tr, src_crs=crs, src_nodata=np.nan,
                      dst_transform=dst_t, dst_crs="EPSG:4326", dst_nodata=np.nan,
                      resampling=Resampling.nearest)
            fill = np.isnan(mos[i]) & ~np.isnan(tmp)
            mos[i][fill] = tmp[fill]
write_json(OUTPUTS / "s2_overview_scenes.json", scene_log)
with rasterio.open(INTERIM / "s2_overview_mosaic.tif", "w", driver="GTiff", width=W, height=H,
                   count=len(bands), dtype="float32", crs="EPSG:4326", transform=dst_t,
                   nodata=np.nan, compress="deflate", predictor=3) as dst:
    dst.write(mos)
    dst.descriptions = tuple(bands)
n_scenes = sum(len(v) for v in scene_log.values())
print(f"Sentinel-2 overview mosaic: {n_scenes} scenes over {len(scene_log)} tiles, "
      f"{np.isnan(mos[2]).mean() * 100:.1f}% of the bbox without data")
