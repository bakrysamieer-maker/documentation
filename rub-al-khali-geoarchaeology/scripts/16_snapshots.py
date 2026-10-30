"""Step 16 - image snapshots (4 x 4 km) for every candidate.

Panels: (1) Sentinel-2 true colour 10 m (fresh windowed read, ~15 MB per candidate),
(2) Sentinel-2 SWIR false colour B12-B11-B2 (30 m), (3) Copernicus DEM hillshade with
streams, wadi termini and projected buried courses, (4) Landsat-1 MSS red band 1972-73
(60 m), (5) Sentinel-2 red band 2024-25 at the same 60 m, (6) detected line segments,
corners and circles on the 20 m red band, with modern features.
Output: outputs/candidates/snapshots/C##.png (+ small JPEG thumbnails for the map popups)
"""
from __future__ import annotations

import json

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mgrs
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LightSource
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds

from common import CANDIDATES, INTERIM, OUTPUTS, PROCESSED, RAW, UTM
import s2_catalog

HALF = 2000                                   # 4 x 4 km window
OUT = CANDIDATES / "snapshots"
OUT.mkdir(parents=True, exist_ok=True)
cand = pd.read_csv(CANDIDATES / "top20_candidates.csv")
scenes = json.loads((OUTPUTS / "s2_corridor_scenes.json").read_text())
to_utm = Transformer.from_crs(4326, UTM, always_xy=True)
vec = {k: gpd.read_file(PROCESSED / f"{k}.geojson").to_crs(UTM) for k in
       ("streams", "wadi_termini", "projected_courses", "shisr_tracks", "long_straight_lines",
        "modern_roads_tracks", "circles")}
segs = np.load(INTERIM / "segments.npy")
m = mgrs.MGRS()


def crop(path, bands, b, out_shape=None):
    with rasterio.open(path) as src:
        win = from_bounds(*b, transform=src.transform)
        return src.read(bands, window=win, out_shape=out_shape, boundless=True, fill_value=0).astype("float32")


def stretch(rgb):
    v = rgb[np.isfinite(rgb) & (rgb > 0)]
    if v.size == 0:
        return np.zeros_like(rgb)
    lo, hi = np.percentile(v, [1, 99.5])
    return np.clip((rgb - lo) / max(hi - lo, 1e-6), 0, 1)


def s2_true_colour_10m(lat, lon, b):
    """Fresh 10 m read from the scene used for the tile that contains the point."""
    tiles = {m.toMGRS(lat + dy, lon + dx, MGRSPrecision=0)[:5] for dy in (-0.05, 0, 0.05) for dx in (-0.05, 0, 0.05)}
    for t in tiles & set(scenes["tiles"]):
        for s in scenes["tiles"][t]:
            sid = s["scene"]
            parts = sid.split("_")
            yy, mm = int(parts[2][:4]), int(parts[2][4:6])
            sc = next((x for x in s2_catalog.scenes(t, yy, mm) if x.scene_id == sid), None)
            if sc is None:
                continue
            with rasterio.open("/vsicurl/" + sc.href("B04.tif")) as src:
                x0, y0, x1, y1 = rasterio.warp.transform_bounds(UTM, src.crs, *b)
                win = from_bounds(x0, y0, x1, y1, transform=src.transform)
                if win.col_off < 0 or win.row_off < 0 or win.col_off + win.width > src.width or \
                        win.row_off + win.height > src.height:
                    continue
            rgb = [s2_catalog.read_reflectance(sc, band, window=win)[0] for band in ("B04", "B03", "B02")]
            arr = np.dstack(rgb)
            if np.isnan(arr).mean() < 0.05:
                return arr, sid
    return None, None


for _, c in cand.iterrows():
    x, y = to_utm.transform(c["lon"], c["lat"])
    b = (x - HALF, y - HALF, x + HALF, y + HALF)
    ext = [-HALF / 1000, HALF / 1000, -HALF / 1000, HALF / 1000]
    fig, axs = plt.subplots(2, 3, figsize=(15, 10.4), constrained_layout=True)
    ax = axs.ravel()
    tc, sid = s2_true_colour_10m(c["lat"], c["lon"], b)
    if tc is not None:
        ax[0].imshow(stretch(tc) ** 0.85, extent=ext)
    ax[0].set_title(f"Sentinel-2 true colour 10 m\n{sid or 'not available'}", fontsize=8)

    sw = crop(INTERIM / "s2_30m.tif", [6, 5, 1], b) / 1e4
    ax[1].imshow(stretch(np.transpose(sw, (1, 2, 0))), extent=ext)
    ax[1].set_title("Sentinel-2 SWIR false colour (B12-B11-B2), 30 m", fontsize=8)

    dem = crop(INTERIM / "dem30_utm.tif", [1], b)[0]
    hs = LightSource(315, 35).hillshade(np.nan_to_num(dem, nan=np.nanmean(dem)), vert_exag=3, dx=30, dy=30)
    ax[2].imshow(hs, cmap="gray", extent=ext)
    ax[2].set_title(f"DEM hillshade (30 m), elev {np.nanmin(dem):.0f}-{np.nanmax(dem):.0f} m;\n"
                    "blue: wadis, cyan: projected courses, red ▲: wadi termini", fontsize=8)

    old = crop(INTERIM / "sand_change_60m.tif", [4], b)[0]       # quantile-mapped 1972 ratio
    mss = list((RAW / "landsat").glob("*_B5.TIF"))
    ax[3].imshow(stretch(old), cmap="gray", extent=ext)
    ax[3].set_title("Landsat-1 MSS 1972-73: red/green ratio (60 m, matched to 2025)", fontsize=8)
    new = crop(INTERIM / "sand_change_60m.tif", [5], b)[0]
    ax[4].imshow(stretch(new), cmap="gray", extent=ext)
    ax[4].set_title("Sentinel-2 2024-25: red/green ratio (60 m)", fontsize=8)

    b04 = crop(INTERIM / "s2_b04_20m.tif", [1], b)[0] / 1e4
    ax[5].imshow(stretch(b04), cmap="gray", extent=ext)
    sel = ((segs[:, 0] > b[0]) & (segs[:, 0] < b[2]) & (segs[:, 1] > b[1]) & (segs[:, 1] < b[3]))
    for s in segs[sel]:
        ax[5].plot([(s[0] - x) / 1000, (s[2] - x) / 1000], [(s[1] - y) / 1000, (s[3] - y) / 1000],
                   color="yellow", lw=0.8)
    ax[5].set_title("detected line segments (yellow), circles (magenta),\nmapped roads/tracks (red), "
                    "long straight / seismic-like lines (orange)", fontsize=8)

    clip = gpd.GeoSeries([gpd.points_from_xy([x], [y])[0].buffer(HALF * 1.5)], crs=UTM).iloc[0]
    shift = lambda g: g.translate(-x, -y).scale(1 / 1000, 1 / 1000, origin=(0, 0))
    for k, style, a in [("streams", dict(color="#3b8bff", lw=1.2), 2), ("projected_courses", dict(color="cyan", lw=1.5, ls="--"), 2),
                        ("modern_roads_tracks", dict(color="red", lw=0.8), 5),
                        ("long_straight_lines", dict(color="orange", lw=1.2), 5),
                        ("shisr_tracks", dict(color="lime", lw=1.2, ls=":"), 0)]:
        g = vec[k][vec[k].intersects(clip)]
        for geom in g.geometry:
            gs = shift(gpd.GeoSeries([geom]))
            gs.plot(ax=ax[a], **style)
    t = vec["wadi_termini"][vec["wadi_termini"].intersects(clip)]
    if len(t):
        shift(t.geometry).plot(ax=ax[2], color="red", marker="^", markersize=40)
    ci = vec["circles"][vec["circles"].intersects(clip)]
    for geom, r in zip(ci.geometry, ci["radius_m"]):
        ax[5].add_patch(plt.Circle(((geom.x - x) / 1000, (geom.y - y) / 1000), r / 1000, fill=False, color="magenta", lw=1))
    for a in ax:
        a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3])
        a.add_patch(plt.Rectangle((-0.5, -0.5), 1, 1, fill=False, color="white", lw=1.2, ls="--"))
        a.tick_params(labelsize=7)
    fig.suptitle(f"{c['candidate_id']} (CANDIDATE, not a discovery) {c['lat']:.4f}N {c['lon']:.4f}E  "
                 f"score {c['score']:.3f}  clues: {c['clues_satisfied'] or 'none >= 0.5'}\n"
                 f"possible natural/modern explanations: {c['natural_or_modern_explanations']}",
                 fontsize=9.5)
    fig.savefig(OUT / f"{c['candidate_id']}.png", dpi=85)
    plt.close(fig)
    im = Image.open(OUT / f"{c['candidate_id']}.png").convert("RGB")
    im.thumbnail((900, 900))
    im.save(OUT / f"{c['candidate_id']}_thumb.jpg", quality=72)
    print(c["candidate_id"], "snapshot written", flush=True)
