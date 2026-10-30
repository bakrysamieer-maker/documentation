"""Step 9 - Sentinel-1 C-band seasonal backscatter and coherence (~250 MB).

Source: Global Seasonal Sentinel-1 Interferometric Coherence and Backscatter data set
(Kellndorfer et al. 2022, Scientific Data 9:73), Dec 2019 - Nov 2020, 3 arcsec, AWS Open Data
bucket sentinel-1-global-coherence-earthbigdata. 1x1 degree tiles named by upper-left corner.

Layers written to data/interim/s1_g90.tif (90 m UTM 40N grid):
  vv_win, vv_sum, vh_win, vh_sum : backscatter amplitude as 20*log10(DN) (relative dB; only
                                    used as z-scores, so the dataset's absolute offset does not matter)
  coh12                         : mean 12-day VV coherence over the four seasons (0-1)
  rho_win, tau_win              : winter coherence-decay model parameters (long-term
                                    coherence and decorrelation time; relative units)
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject

from common import INTERIM, OUTPUTS, RAW, UTM, download, grid, human_bytes, write_raster

BASE = "https://sentinel-1-global-coherence-earthbigdata.s3.us-west-2.amazonaws.com/data/tiles"
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())
tiles = summary["sentinel1_seasonal_tiles"]

products = {
    "vv_win": ["winter_vv_AMP"], "vv_sum": ["summer_vv_AMP"],
    "vh_win": ["winter_vh_AMP"], "vh_sum": ["summer_vh_AMP"],
    "coh12": ["winter_vv_COH12", "spring_vv_COH12", "summer_vv_COH12", "fall_vv_COH12"],
    "rho_win": ["winter_vv_rho"], "tau_win": ["winter_vv_tau"],
}
files = sorted({p for ps in products.values() for p in ps})
jobs = [(f"{BASE}/{t}/{t}_{p}.tif", RAW / "s1" / f"{t}_{p}.tif") for t in tiles for p in files]


def safe_download(job):
    try:
        return download(*job)
    except Exception as exc:          # a few tiles lack some seasons; record and continue
        print("missing:", job[0].split("/")[-1], type(exc).__name__)
        return 0


with ThreadPoolExecutor(8) as ex:
    sizes = list(ex.map(safe_download, jobs))
print(f"Sentinel-1: {sum(s > 0 for s in sizes)}/{len(jobs)} files, {human_bytes(sum(sizes))}")

t90, W90, H90 = grid("g90")
layers, names = [], []
for name, prods in products.items():
    stack = []
    for p in prods:
        paths = [RAW / "s1" / f"{t}_{p}.tif" for t in tiles if (RAW / "s1" / f"{t}_{p}.tif").exists()]
        srcs = [rasterio.open(x) for x in paths]
        mos, mt = merge(srcs, nodata=0, dtype="float32")
        crs = srcs[0].crs
        for s in srcs:
            s.close()
        a = mos[0]
        a[a == 0] = np.nan
        if "AMP" in p:
            a = 20 * np.log10(a)
        elif "COH" in p:
            a = a / 100.0
        out = np.full((H90, W90), np.nan, np.float32)
        reproject(a, out, src_transform=mt, src_crs=crs, src_nodata=np.nan, dst_transform=t90,
                  dst_crs=UTM, dst_nodata=np.nan, resampling=Resampling.bilinear)
        stack.append(out)
    layers.append(np.nanmean(np.stack(stack), axis=0) if len(stack) > 1 else stack[0])
    names.append(name)
    v = layers[-1][~np.isnan(layers[-1])]
    print(f"{name:8s} p5={np.percentile(v, 5):8.3f} p50={np.percentile(v, 50):8.3f} p95={np.percentile(v, 95):8.3f}")

write_raster(INTERIM / "s1_g90.tif", np.stack(layers).astype("float32"), t90, descriptions=names)
print("wrote", INTERIM / "s1_g90.tif")
