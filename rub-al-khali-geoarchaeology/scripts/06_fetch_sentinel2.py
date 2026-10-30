"""Step 6 - Sentinel-2 L2A bands inside the corridor (~1.5 GB of windowed COG reads).

The corridor spans two Sentinel-2 orbits (overpasses ~07:04 and ~07:14 UTC). Mixing dates
between neighbouring tiles leaves straight radiometric seams (haze and sun angle differ), so:
  1. one acquisition date is chosen per orbit (most tiles cloud-free; winter, low sun);
  2. each orbit is mosaicked separately from that single date;
  3. the secondary orbit is matched to the primary one band by band (mean/std of the pixels
     both orbits cover), then used only where the primary orbit has no data.
Only the window covering the corridor is read:
  * B04 (red)              at 20 m  -> data/interim/s2_b04_20m.tif   (anomaly detection)
  * B02 B03 B04 B8A B11 B12 at 30 m -> data/interim/s2_30m.tif      (indices, sand mask)
    (10 m bands are read from the 40 m overview, 20 m bands from their 40 m overview,
     then resampled to the 30 m analysis grid)
Values are stored as reflectance x 10000 in uint16 (0 = no data).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from shapely.geometry import box
from shapely.ops import transform as shp_transform

from common import INTERIM, OUTPUTS, PROCESSED, UTM, grid, read_raster, write_json, write_raster
import s2_catalog

summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())
months = [(2024, 12), (2025, 1), (2025, 2)]
corr_ll = gpd.read_file(PROCESSED / "aoi_corridor.geojson").query("name == 'corridor'").geometry.iloc[0]

t30, W30, H30 = grid("g30")
# 20 m grid with the same origin as the 30 m grid
t20 = rasterio.transform.from_origin(t30.c, t30.f, 20, 20)
W20, H20 = int(W30 * 1.5), int(H30 * 1.5)

BANDS30 = ["B02", "B03", "B04", "B8A", "B11", "B12"]
NATIVE = {"B02": 10, "B03": 10, "B04": 10, "B8A": 20, "B11": 20, "B12": 20}


def _minutes(iso):
    return int(iso[11:13]) * 60 + int(iso[14:16])


# ------------------------------------------------------------------ choose one date per orbit
tiles = summary["sentinel2_mgrs_tiles"]
with ThreadPoolExecutor(6) as ex:
    catalog = dict(zip(tiles, ex.map(
        lambda t: [s for ym in months for s in s2_catalog.scenes(t, *ym)], tiles)))
all_sc = [s for v in catalog.values() for s in v]
split = np.mean([_minutes(s.datetime) for s in all_sc])            # ~07:09 UTC
orbit = lambda s: "early" if _minutes(s.datetime) < split else "late"


def date_score(orb, date):
    """(tiles cloud-free and >50% covered on this date, -total cloud) for one orbit."""
    sc = [s for s in all_sc if orbit(s) == orb and s.datetime[:10] == date]
    good = [s for s in sc if s.cloud < 1.0 and s.nodata < 50]
    return len(good), -sum(s.cloud for s in sc)


best_date = {}
for orb in ("early", "late"):
    dates = sorted({s.datetime[:10] for s in all_sc if orbit(s) == orb})
    best_date[orb] = max(dates, key=lambda d: date_score(orb, d))
coverage = {orb: sum(1 for s in all_sc if orbit(s) == orb and s.datetime[:10] == best_date[orb]
                     and s.nodata < 50) for orb in best_date}
primary = max(coverage, key=coverage.get)
secondary = "late" if primary == "early" else "early"
print("chosen dates:", best_date, "primary orbit:", primary, flush=True)


def scene_on(tile, orb):
    for s in catalog[tile]:
        if orbit(s) == orb and s.datetime[:10] == best_date[orb]:
            return s
    return None


def read_band(sc, band, res_out):
    """Read the corridor window of one band at res_out metres. Returns (refl, transform, crs) or None."""
    with rasterio.open("/vsicurl/" + sc.href(f"{band}.tif")) as src:
        to_tile = Transformer.from_crs(4326, src.crs, always_xy=True).transform
        poly = shp_transform(to_tile, corr_ll).intersection(box(*src.bounds))
        if poly.is_empty:
            return None
        win = from_bounds(*poly.bounds, transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, src.width, src.height))
        f = res_out / NATIVE[band]
        shape = (max(1, int(win.height / f)), max(1, int(win.width / f)))
        crs = src.crs
    refl, tr, _ = s2_catalog.read_reflectance(sc, band, out_shape=shape, window=win)
    return refl, tr, crs


def paste(dst, dst_t, refl, tr, crs, res):
    """Reproject refl into the matching sub-window of dst, filling only empty cells."""
    b = transform_bounds(crs, UTM, *rasterio.transform.array_bounds(*refl.shape, tr))
    c0 = max(0, int((b[0] - dst_t.c) // res)); c1 = min(dst.shape[1], int((b[2] - dst_t.c) // res) + 2)
    r0 = max(0, int((dst_t.f - b[3]) // res)); r1 = min(dst.shape[0], int((dst_t.f - b[1]) // res) + 2)
    if c1 <= c0 or r1 <= r0:
        return
    sub_t = dst_t * dst_t.translation(c0, r0)
    tmp = np.full((r1 - r0, c1 - c0), np.nan, np.float32)
    reproject(refl, tmp, src_transform=tr, src_crs=crs, src_nodata=np.nan, dst_transform=sub_t,
              dst_crs=UTM, dst_nodata=np.nan, resampling=Resampling.bilinear)
    val = np.clip(np.nan_to_num(tmp * 10000, nan=0), 0, 65535).astype(np.uint16)
    view = dst[r0:r1, c0:c1]
    fill = (view == 0) & (val > 0)
    view[fill] = val[fill]


mos30 = {o: np.zeros((len(BANDS30), H30, W30), np.uint16) for o in ("early", "late")}
mos20 = {o: np.zeros((H20, W20), np.uint16) for o in ("early", "late")}
log = {t: [] for t in tiles}
plan, fallback = [], []
for tile in tiles:
    s_pri, s_sec = scene_on(tile, primary), scene_on(tile, secondary)
    use = []
    if s_pri is not None and s_pri.cloud < 5:
        use.append((primary, s_pri))
    if s_sec is not None and s_sec.cloud < 5 and (not use or s_pri.nodata > 1.0):
        use.append((secondary, s_sec))
    if not use:   # no clear scene on either chosen date: best scene of any date, pasted last
        best = s2_catalog.best_scene(tile, months)
        if best is not None:
            fallback.append((tile, orbit(best), best))
    plan += [(tile, o, s) for o, s in use]

# chosen-date scenes first, fallbacks afterwards, so a fallback only fills remaining holes
for tile, orb, sc in plan + fallback:
    jobs = [(b, 40) for b in BANDS30] + [("B04", 20)]
    with ThreadPoolExecutor(7) as ex:
        res = list(ex.map(lambda j: read_band(sc, *j), jobs))
    for (band, r), got in zip(jobs, res):
        if got is None:
            continue
        if r == 20:
            paste(mos20[orb], t20, *got, 20)
        else:
            paste(mos30[orb][BANDS30.index(band)], t30, *got, 30)
    log[tile].append({"orbit": orb, "scene": sc.scene_id, "datetime": sc.datetime,
                      "cloud_pct": sc.cloud, "nodata_pct": sc.nodata,
                      "sun_elevation": round(sc.sun_elev, 1),
                      "fallback": (tile, orb, sc) in fallback})
    print(tile, orb, sc.scene_id, flush=True)


# ------------------------------------------------------------------ match secondary orbit to primary
def match(sec, pri):
    """Linear mean/std matching of sec to pri over cells both cover (central 98% of values)."""
    both = (sec > 0) & (pri > 0)
    n = int(both.sum())
    if n < 10000:
        return sec, None
    a, b = pri[both].astype("float64"), sec[both].astype("float64")
    lo_a, hi_a = np.percentile(a, [1, 99]); lo_b, hi_b = np.percentile(b, [1, 99])
    keep = (a > lo_a) & (a < hi_a) & (b > lo_b) & (b < hi_b)
    gain = a[keep].std() / b[keep].std()
    off = a[keep].mean() - gain * b[keep].mean()
    out = np.where(sec > 0, np.clip(sec * gain + off, 1, 65535), 0).astype(np.uint16)
    return out, {"gain": round(float(gain), 4), "offset": round(float(off), 1), "overlap_cells": n}


norm = {}
out30 = mos30[primary]
for i, band in enumerate(BANDS30):
    adj, norm[band] = match(mos30[secondary][i], mos30[primary][i])
    fill = (out30[i] == 0) & (adj > 0)
    out30[i][fill] = adj[fill]
adj20, norm["B04_20m"] = match(mos20[secondary], mos20[primary])
out20 = mos20[primary]
fill = (out20 == 0) & (adj20 > 0)
out20[fill] = adj20[fill]
src_orbit = np.where(mos30[primary][2] > 0, 1, np.where(mos30[secondary][2] > 0, 2, 0)).astype("uint8")
print("normalisation of secondary orbit:", norm)

write_json(OUTPUTS / "s2_corridor_scenes.json",
           {"chosen_dates": best_date, "primary_orbit": primary, "normalisation": norm, "tiles": log})
write_raster(INTERIM / "s2_30m.tif", out30, t30, nodata=0, descriptions=BANDS30, dtype="uint16")
write_raster(INTERIM / "s2_b04_20m.tif", out20, t20, nodata=0, descriptions=["B04"], dtype="uint16")
write_raster(INTERIM / "s2_orbit_30m.tif", src_orbit, t30, nodata=0, descriptions=["1=primary 2=secondary"])
m30, _ = read_raster(INTERIM / "corridor_mask_g30.tif")
print(f"30 m stack written; corridor cells without data: {((out30[2] == 0) & (m30 == 1)).sum():,}")
