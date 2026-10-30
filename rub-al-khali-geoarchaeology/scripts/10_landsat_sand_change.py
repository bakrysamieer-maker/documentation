"""Step 10 - multi-decade sand cover: Landsat-1 MSS (1972-73) vs Sentinel-2 (2024-25), clue 6.

Data: Landsat Collection 1 Level-1 (L1TP) MSS from the public Google Cloud bucket
gcp-public-data-landsat; green (B4) and red (B5) bands only (~150-200 MB).
One scene per WRS-1 path/row covering the corridor (least cloud, winter preferred).

Method (60 m UTM grid aligned with the 30 m grid):
  * TOA reflectance from the MTL rescaling factors, sun-elevation corrected
  * the same sand index in both epochs: red/green ratio (MSS has no blue band)
  * sand / not-sand per scene with that scene's own Otsu threshold (no cross-date seams)
  * change classes: 0 stable ground, 1 stable sand, 2 sand gained (recent cover),
                    3 sand lost (recently exposed)
  * dune displacement: phase cross-correlation of the red band in 32 x 32 px (1.9 km)
    windows; each scene's registration offset (median shift on stable non-sand ground)
    is removed; only well-correlated windows are kept.

Outputs: data/interim/sand_change_60m.tif, data/processed/dune_displacement.geojson,
         outputs/landsat_scenes.json
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import Point
from skimage.filters import threshold_otsu
from skimage.registration import phase_cross_correlation

from common import INTERIM, OUTPUTS, PROCESSED, RAW, UTM, download, grid, read_raster, write_json, write_raster

GCS = "https://storage.googleapis.com"
BUCKET = "gcp-public-data-landsat"
PATH_ROWS = [(171, 46), (171, 47), (172, 46), (172, 47), (172, 48), (173, 46), (173, 47)]
S = requests.Session()

t30, W30, H30 = grid("g30")
t60 = rasterio.transform.from_origin(t30.c, t30.f, 60, 60)
W60, H60 = W30 // 2, H30 // 2
corr60 = np.zeros((H60, W60), np.uint8)
m30, _ = read_raster(INTERIM / "corridor_mask_g30.tif")
reproject(m30, corr60, src_transform=t30, src_crs=UTM, dst_transform=t60, dst_crs=UTM,
          resampling=Resampling.nearest)
inside = corr60 == 1


def list_scenes(path, row):
    u = f"{GCS}/storage/v1/b/{BUCKET}/o"
    r = S.get(u, params={"prefix": f"LM01/01/{path:03d}/{row:03d}/", "delimiter": "/"}, timeout=60)
    return r.json().get("prefixes", [])


def mtl(prefix):
    sid = prefix.rstrip("/").split("/")[-1]
    txt = S.get(f"{GCS}/{BUCKET}/{prefix}{sid}_MTL.txt", timeout=60).text
    g = lambda k: re.search(rf"{k}\s*=\s*\"?([^\"\n]+)", txt).group(1).strip()
    return {"id": sid, "prefix": prefix, "date": g("DATE_ACQUIRED"), "cloud": float(g("CLOUD_COVER")),
            "sun_elev": float(g("SUN_ELEVATION")),
            **{f"{k}{b}": float(g(f"REFLECTANCE_{k}_BAND_{b}")) for k in ("MULT", "ADD") for b in (4, 5)}}


def choose(pr):
    cands = [mtl(p) for p in list_scenes(*pr) if "_L1TP_" in p]
    cands = [c for c in cands if c["cloud"] >= 0]
    winter = lambda c: int(c["date"][5:7]) in (11, 12, 1, 2, 3)
    # least cloud first; winter (low sun, like the Sentinel-2 dates) only breaks near-ties
    return min(cands, key=lambda c: (round(c["cloud"] / 5), not winter(c), c["cloud"])) if cands else None


with ThreadPoolExecutor(7) as ex:
    chosen = [c for c in ex.map(choose, PATH_ROWS) if c]
write_json(OUTPUTS / "landsat_scenes.json", chosen)


def scene_toa(c):
    """TOA reflectance of B4/B5 on the 60 m grid, with clouds (BQA) masked out."""
    q = RAW / "landsat" / f"{c['id']}_BQA.TIF"
    download(f"{GCS}/{BUCKET}/{c['prefix']}{c['id']}_BQA.TIF", q, session=S)
    with rasterio.open(q) as src:
        bqa = src.read(1)
        # Collection 1 BQA: bit 4 cloud with bits 5-6 cloud confidence = 3 (high). The MSS flags are
        # speckled over bright sand, so remove speckle before a modest ~120 m buffer.
        cloud = ((bqa >> 4) & 1).astype(bool) & (((bqa >> 5) & 3) == 3)
        cloud = ndimage.binary_dilation(ndimage.binary_opening(cloud, iterations=2), iterations=2)
    c["cloud_masked_pct"] = round(float(cloud[bqa > 1].mean() * 100), 1) if (bqa > 1).any() else 0.0
    out = {}
    for b in (4, 5):
        p = RAW / "landsat" / f"{c['id']}_B{b}.TIF"
        download(f"{GCS}/{BUCKET}/{c['prefix']}{c['id']}_B{b}.TIF", p, session=S)
        with rasterio.open(p) as src:
            dn = src.read(1).astype("float32")
            refl = np.where((dn > 0) & ~cloud,
                            (c[f"MULT{b}"] * dn + c[f"ADD{b}"]) / np.sin(np.radians(c["sun_elev"])), np.nan)
            dst = np.full((H60, W60), np.nan, np.float32)
            reproject(refl, dst, src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                      dst_transform=t60, dst_crs=UTM, dst_nodata=np.nan, resampling=Resampling.bilinear)
        out[b] = dst
    return out


# ------------------------------------------------------------------ Sentinel-2 at 60 m (red/green)
with rasterio.open(INTERIM / "s2_30m.tif") as src:
    names = list(src.descriptions)
    s2 = {b: src.read(names.index(b) + 1, out_shape=(H60, W60), resampling=Resampling.average)
             .astype("float32") / 1e4 for b in ("B03", "B04")}
for b in s2:
    s2[b][(s2[b] <= 0) | ~inside] = np.nan
ratio_new = s2["B04"] / s2["B03"]
t_new = float(threshold_otsu(ratio_new[np.isfinite(ratio_new)]))
sand_new = ratio_new > t_new
with rasterio.open(INTERIM / "sand_mask_30m.tif") as src:     # reliable 2025 sand mask (step 7)
    sand7 = src.read(1, out_shape=(H60, W60), resampling=Resampling.average).astype("float32")
    sand7 = np.where(src.read(1, out_shape=(H60, W60), resampling=Resampling.nearest) == 255, np.nan, sand7)

# ------------------------------------------------------------------ MSS 1972-73 mosaic, per-scene Otsu
ratio_old = np.full((H60, W60), np.nan, np.float32)
red_old = np.full((H60, W60), np.nan, np.float32)
sand_old = np.zeros((H60, W60), bool)
scene_id = np.zeros((H60, W60), np.uint8)
for i, c in enumerate(sorted(chosen, key=lambda c: c["cloud"]), start=1):
    toa = scene_toa(c)
    r = toa[5] / toa[4]
    ok = np.isfinite(r) & inside & np.isnan(ratio_old) & np.isfinite(ratio_new)
    if ok.sum() < 1000:
        continue
    # quantile-map this scene's 1972 ratio onto the 2025 ratio of the same pixels, then use the
    # 2025 threshold for both epochs (different sensors/atmospheres; keeps the footprint's sand
    # fraction comparable, so change = redistribution of sand within the footprint)
    q = np.linspace(0, 100, 201)
    mapped = np.interp(r[ok], np.percentile(r[ok], q), np.percentile(ratio_new[ok], q))
    ratio_old[ok] = mapped
    red_old[ok] = toa[5][ok]
    sand_old[ok] = mapped > t_new
    scene_id[ok] = i
    print(c["id"], c["date"], f"cloud {c['cloud']}% (masked {c['cloud_masked_pct']}%)",
          f"{ok.sum():,} cells", flush=True)
write_json(OUTPUTS / "landsat_scenes.json", chosen)

both = np.isfinite(ratio_old) & np.isfinite(ratio_new)
change = np.full((H60, W60), 255, np.uint8)
change[both & ~sand_old & ~sand_new] = 0
change[both & sand_old & sand_new] = 1
change[both & ~sand_old & sand_new] = 2
change[both & sand_old & ~sand_new] = 3

# ------------------------------------------------------------------ dune displacement (phase correlation)
red_new = s2["B04"]
win, step = 48, 24                                   # 2.9 km windows, 1.4 km spacing
vec = []
for r0 in range(0, H60 - win, step):
    for c0 in range(0, W60 - win, step):
        a = red_old[r0:r0 + win, c0:c0 + win]
        b = red_new[r0:r0 + win, c0:c0 + win]
        if np.isnan(a).mean() > 0.02 or np.isnan(b).mean() > 0.02 or np.nanstd(a) < 1e-3 or np.nanstd(b) < 1e-3:
            continue
        a = np.nan_to_num(a, nan=float(np.nanmean(a))); b = np.nan_to_num(b, nan=float(np.nanmean(b)))
        shift, err, _ = phase_cross_correlation(b, a, upsample_factor=4, normalization=None)
        sc = scene_id[r0 + win // 2, c0 + win // 2]
        frac_sand = float(np.nanmean(sand7[r0:r0 + win, c0:c0 + win]))
        vec.append((r0 + win / 2, c0 + win / 2, shift[0], shift[1], err, sc, frac_sand))
vec = np.array(vec, dtype="float64")
# registration offset per MSS scene: median shift over windows with little sand
for sc in np.unique(vec[:, 5]):
    sel = (vec[:, 5] == sc) & (vec[:, 6] < 0.2) & (vec[:, 4] < np.percentile(vec[:, 4], 50))
    if sel.sum() >= 20:
        vec[vec[:, 5] == sc, 2] -= np.median(vec[sel, 2])
        vec[vec[:, 5] == sc, 3] -= np.median(vec[sel, 3])
good = (vec[:, 4] < np.percentile(vec[:, 4], 60)) & (vec[:, 6] > 0.5)
years = 2025.1 - 1972.9
rows = []
for r, c, dy, dx, err, sc, fs in vec[good]:
    x, y = rasterio.transform.xy(t60, r, c)
    mag = float(np.hypot(dx, dy) * 60)
    rows.append({"shift_m": round(mag, 1), "rate_m_per_yr": round(mag / years, 2),
                 "azimuth_deg": round(float(np.degrees(np.arctan2(dx, -dy)) % 360), 1),
                 "corr_error": round(float(err), 3), "geometry": Point(x, y)})
disp = gpd.GeoDataFrame(rows, crs=UTM)
disp.to_crs(4326).to_file(PROCESSED / "dune_displacement.geojson")

# displacement magnitude raster (60 m, nearest window value)
dmag = np.full((H60, W60), np.nan, np.float32)
for (r, c, dy, dx, *_), keep in zip(vec, good):
    if keep:
        dmag[int(r - step / 2):int(r + step / 2), int(c - step / 2):int(c + step / 2)] = np.hypot(dx, dy) * 60
write_raster(INTERIM / "sand_change_60m.tif",
             np.stack([sand_old.astype("float32"), sand_new.astype("float32"), change.astype("float32"),
                       ratio_old, ratio_new, dmag]), t60,
             descriptions=["sand_1972", "sand_2025", "change_class", "red_green_1972",
                           "red_green_2025", "dune_shift_m"])
cls = {k: int((change == v).sum()) for k, v in
       [("stable_ground", 0), ("stable_sand", 1), ("sand_gained", 2), ("sand_lost", 3)]}
stats = {"years": round(years, 1), "change_cells_60m": cls,
         "displacement_windows": len(disp),
         "median_shift_m": round(float(disp["shift_m"].median()), 1) if len(disp) else None,
         "p90_shift_m": round(float(disp["shift_m"].quantile(0.9)), 1) if len(disp) else None}
write_json(OUTPUTS / "sand_change_stats.json", stats)
print(stats)
