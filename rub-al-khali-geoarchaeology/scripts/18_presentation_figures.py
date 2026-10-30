"""Step 18 - clean figures for the Arabic presentation (no English text inside the images).

Arabic labels are set in Noto Sans Arabic (SIL Open Font License, data/reference/fonts/);
matplotlib >= 3.11 shapes Arabic and lays it out right-to-left itself, so strings are passed
unchanged. Captions and legends live in the slides. Output: outputs/presentation/figures/*.png
"""
from __future__ import annotations

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.font_manager import FontProperties
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from common import CANDIDATES, FIGURES, INTERIM, OUTPUTS, PROCESSED, REFERENCE, UTM, grid, read_raster
from maputil import block_max

OUT = OUTPUTS / "presentation" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
AR = FontProperties(fname=str(REFERENCE / "fonts" / "NotoSansArabic[wdth,wght].ttf"))
ar = lambda s: s
HALO = [pe.withStroke(linewidth=3, foreground="white")]
to_utm = Transformer.from_crs(4326, UTM, always_xy=True)
BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def save(fig, name, dpi=150):
    fig.savefig(OUT / name, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def s2_rgb(factor):
    with rasterio.open(INTERIM / "s2_30m.tif") as src:
        h, w = src.height // factor, src.width // factor
        b = src.read([3, 2, 1], out_shape=(3, h, w), resampling=Resampling.average).astype("float32") / 1e4
        tr = src.transform * src.transform.scale(src.width / w, src.height / h)
    valid = b.sum(0) > 0
    lo, hi = np.percentile(b[:, valid], [1, 99.5])
    rgb = np.clip((b - lo) / (hi - lo), 0, 1) ** 0.9
    rgba = np.dstack([np.transpose(rgb, (1, 2, 0)), valid.astype("float32")])
    ext = [tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f]
    return rgba, ext


def frame(ax, ext):
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(False)


def scalebar(ax, ext, km=50, y_frac=0.04):
    x0 = ext[0] + (ext[1] - ext[0]) * 0.05
    y0 = ext[2] + (ext[3] - ext[2]) * y_frac
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="#0b0b0b", lw=3, solid_capstyle="butt")
    ax.text(x0 + km * 500, y0 + (ext[3] - ext[2]) * 0.012, ar(f"{km} كم"), fontproperties=AR,
            ha="center", va="bottom", fontsize=11, color="#0b0b0b")


rd = lambda n: gpd.read_file(PROCESSED / f"{n}.geojson").to_crs(UTM)
corr = rd("aoi_corridor").query("name == 'corridor'")
borders = rd("borders_context")
refs = pd.read_csv(REFERENCE / "reference_points.csv").dropna(subset=["lat"])
AR_NAMES = {"shisr": "شصر (وبار)", "umm_al_heesh": "بحيرات أم الحيش", "hamidan": "تركيب الحميدان",
            "muqshin_s2": "قرية مقشن", "umm_as_samim": "أم السميم"}

# ------------------------------------------------------------------ 1. overview
rgba, ext = s2_rgb(6)
fig, ax = plt.subplots(figsize=(8.2, 9))
ax.imshow(rgba, extent=ext)
corr.boundary.plot(ax=ax, color="#e34948", lw=2)
borders.plot(ax=ax, color="white", lw=1.5, ls="--")
for _, r in refs.iterrows():
    if r["id"] not in AR_NAMES:
        continue
    x, y = to_utm.transform(r["lon"], r["lat"])
    if not (ext[0] < x < ext[1] and ext[2] < y < ext[3]):
        continue
    ax.plot(x, y, marker="*" if r["role"] == "known_site" else "o", ms=15 if r["role"] == "known_site" else 8,
            color="#e34948" if r["role"] == "known_site" else "#ffffff", mec="#0b0b0b", mew=1)
    dy = {"umm_al_heesh": 9000, "hamidan": -9000}.get(r["id"], 3000)      # the two are 11 km apart
    ax.text(x - 6000, y + dy, ar(AR_NAMES[r["id"]]), fontproperties=AR, fontsize=13, ha="right", va="center",
            color="#0b0b0b", bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.85, lw=0))
for label, (lo, la) in {"عُمان": (54.9, 18.75), "السعودية": (53.3, 20.75)}.items():
    x, y = to_utm.transform(lo, la)
    ax.text(x, y, ar(label), fontproperties=AR, fontsize=18, color="#0b0b0b", ha="center",
            path_effects=HALO)
scalebar(ax, ext)
frame(ax, ext)
save(fig, "overview.png")

# ------------------------------------------------------------------ 2. drainage
fig, ax = plt.subplots(figsize=(8.2, 9))
ax.imshow(rgba, extent=ext)
st = rd("streams")
st[st["catchment_km2"] >= 50].plot(ax=ax, color="#2a78d6", lw=0.9)
rd("projected_courses").plot(ax=ax, color="#5be0ff", lw=1.6, ls="--")
t = rd("wadi_termini")
t.plot(ax=ax, color="#e34948", markersize=10 + np.log10(t["catchment_km2"]) * 14, edgecolor="white", linewidth=0.6)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1.2)
scalebar(ax, ext)
frame(ax, ext)
save(fig, "drainage.png")

# ------------------------------------------------------------------ 3. clue 6 panels
dh, t30 = read_raster(INTERIM / "dune_height_30m.tif")
f = 6
dh_s = dh[::f, ::f]
fig, ax = plt.subplots(figsize=(6, 6.6))
ax.imshow(rgba, extent=ext, alpha=0.35)
ax.imshow(np.ma.masked_invalid(np.where(dh_s > 1, dh_s, np.nan)), extent=ext, cmap="Oranges", vmin=0, vmax=60)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
frame(ax, ext)
save(fig, "dune_height.png")

with rasterio.open(INTERIM / "sand_change_60m.tif") as src:
    chg = src.read(3)[::3, ::3]
cm = np.zeros(chg.shape + (4,))
cm[chg == 1] = [0x1b / 255, 0xaf / 255, 0x7a / 255, 0.45]
cm[chg == 2] = [0xeb / 255, 0x68 / 255, 0x34 / 255, 0.95]
cm[chg == 3] = [0x2a / 255, 0x78 / 255, 0xd6 / 255, 0.95]
fig, ax = plt.subplots(figsize=(6, 6.6))
ax.imshow(rgba, extent=ext, alpha=0.35)
ax.imshow(cm, extent=ext)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
frame(ax, ext)
save(fig, "sand_change.png")

with rasterio.open(INTERIM / "s1_g90.tif") as src:
    coh = src.read(list(src.descriptions).index("coh12") + 1)
    tr90 = src.transform
m90, _ = read_raster(INTERIM / "corridor_mask_g90.tif")
mob = np.where(m90 == 1, 1 - coh, np.nan)
e90 = [tr90.c, tr90.c + mob.shape[1] * tr90.a, tr90.f + mob.shape[0] * tr90.e, tr90.f]
fig, ax = plt.subplots(figsize=(6, 6.6))
ax.imshow(rgba, extent=ext, alpha=0.35)
ax.imshow(np.ma.masked_invalid(mob), extent=e90, cmap="Oranges", vmin=0.05, vmax=0.9)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
frame(ax, ext)
save(fig, "radar_mobility.png")

# ------------------------------------------------------------------ 4. Shisr tracks (40 km window)
sx, sy = to_utm.transform(53.6489, 18.255)
H = 40000
b = (sx - H, sy - H * 0.5, sx + H, sy + H * 1.5)
with rasterio.open(INTERIM / "s2_b04_20m.tif") as src:
    a = src.read(1, window=from_bounds(*b, transform=src.transform), out_shape=(1500, 1000),
                 resampling=Resampling.average).astype("float32") / 1e4
lo, hi = np.percentile(a[a > 0], [1, 99.5])
fig, ax = plt.subplots(figsize=(6.4, 9.6))
ax.imshow(np.clip((a - lo) / (hi - lo), 0, 1), cmap="gray", extent=[b[0], b[2], b[1], b[3]])
segs = np.load(INTERIM / "segments.npy")
sel = (segs[:, 0] > b[0]) & (segs[:, 0] < b[2]) & (segs[:, 1] > b[1]) & (segs[:, 1] < b[3])
for s in segs[sel]:
    ax.plot([s[0], s[2]], [s[1], s[3]], color="#eda100", lw=0.8)
rd("modern_roads_tracks").cx[b[0]:b[2], b[1]:b[3]].plot(ax=ax, color="#e34948", lw=0.6)
tr_ = rd("shisr_tracks")
tr_[tr_["part"] == "detected"].plot(ax=ax, color="#1baf7a", lw=2.4)
tr_[tr_["part"] != "detected"].plot(ax=ax, color="#1baf7a", lw=2.4, ls="--")
rd("long_straight_lines").plot(ax=ax, color="#ffffff", lw=2, ls=":")
ax.plot(sx, sy, marker="*", ms=18, color="#e34948", mec="white")
frame(ax, [b[0], b[2], b[1], b[3]])
scalebar(ax, [b[0], b[2], b[1], b[3]], km=10, y_frac=0.03)
save(fig, "shisr_tracks.png")

# ------------------------------------------------------------------ 5. pale crust proxy + groundwater lows
with rasterio.open(INTERIM / "s2_indices_30m.tif") as src:
    pale = block_max(src.read(list(src.descriptions).index("pale_crust") + 1), f)
fig, ax = plt.subplots(figsize=(6, 6.6))
ax.imshow(rgba, extent=ext, alpha=0.35)
ax.imshow(np.ma.masked_where(~(pale > 2), pale), extent=ext, cmap="Oranges", vmin=1, vmax=5)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
frame(ax, ext)
save(fig, "pale_crust.png")

z = np.load(PROCESSED / "score_components_1km.npz")
t1, W1, H1 = grid("g1km")
e1 = [t1.c, t1.c + W1 * t1.a, t1.f + H1 * t1.e, t1.f]
fig, ax = plt.subplots(figsize=(6, 6.6))
ax.imshow(rgba, extent=ext, alpha=0.35)
ax.imshow(np.ma.masked_where(~(z["groundwater_lows"] > 0.05), z["groundwater_lows"]), extent=e1,
          cmap=ListedColormap(BLUE), vmin=0, vmax=1)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1)
frame(ax, ext)
save(fig, "groundwater_lows.png")

# ------------------------------------------------------------------ 6. weighted score + candidates
with rasterio.open(PROCESSED / "score_1km.tif") as src:
    sc = src.read(1)
dem, t30_ = read_raster(INTERIM / "dem30_utm.tif")
d = dem[::8, ::8]
hs = LightSource(315, 35).hillshade(np.nan_to_num(d, nan=np.nanmean(d)), vert_exag=3, dx=240, dy=240)
fig, ax = plt.subplots(figsize=(8.2, 9))
ax.imshow(np.where(np.isfinite(d), hs, np.nan), cmap="gray", extent=ext, vmin=0, vmax=1.2)
v = sc / np.nanmax(sc)
ax.imshow(np.ma.masked_where(~(v > 0.05), v), extent=e1, cmap=ListedColormap(BLUE), vmin=0, vmax=1, alpha=0.85)
cand = pd.read_csv(CANDIDATES / "top20_candidates.csv")
placed = []                                  # label boxes already drawn (data units, m)
LW, LH = 11000, 6000
for _, c in cand.iterrows():
    x, y = to_utm.transform(c["lon"], c["lat"])
    ax.plot(x, y, "o", ms=9, mfc="white", mec="#0b0b0b", mew=1.6)
    # greedy placement: right, left, above, below, then further out
    for dx, dy in [(3500, 0), (-3500 - LW, 0), (-LW / 2, 5000), (-LW / 2, -5000 - LH),
                   (3500, 7000), (3500, -7000), (-3500 - LW, 7000), (-3500 - LW, -7000)]:
        box = (x + dx, y + dy - LH / 2, x + dx + LW, y + dy + LH / 2)
        if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in placed):
            break
    placed.append(box)
    ax.text(box[0], (box[1] + box[3]) / 2, c["candidate_id"], fontsize=9, color="#0b0b0b", va="center",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.9, lw=0))
    if abs(dy) > 0 or dx < 0:
        ax.plot([x, box[0] if dx > 0 else box[2]], [y, (box[1] + box[3]) / 2], color="#0b0b0b", lw=0.6)
corr.boundary.plot(ax=ax, color="#0b0b0b", lw=1.2)
borders.plot(ax=ax, color="#52514e", lw=1.2, ls="--")
scalebar(ax, ext)
frame(ax, ext)
save(fig, "score_candidates.png")

# ------------------------------------------------------------------ 7. reference checks (titles cropped)
for k in ("shisr", "umm_al_heesh", "muqshin_s2", "muqshin"):
    p = FIGURES / "reference_chips" / f"{k}.png"
    if p.exists():
        im = Image.open(p)
        im.crop((0, 62, im.width, im.height)).save(OUT / f"check_{k}.png")

# ------------------------------------------------------------------ 8. example candidates: 3 clean panels
chips = INTERIM / "chips_10m"
for cid in ("C01", "C03", "C11"):
    c = cand.set_index("candidate_id").loc[cid]
    x, y = to_utm.transform(c["lon"], c["lat"])
    Hc = 2000
    bb = (x - Hc, y - Hc, x + Hc, y + Hc)
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.5))
    key = chips / f"{c['lat']:.5f}_{c['lon']:.5f}.npz"
    if key.exists():
        rgb = np.load(key)["rgb"]
        v_ = rgb[np.isfinite(rgb)]
        lo, hi = np.percentile(v_, [1, 99.5])
        axs[0].imshow(np.clip((rgb - lo) / (hi - lo), 0, 1) ** 0.85, extent=[-2, 2, -2, 2])
    with rasterio.open(INTERIM / "dem30_utm.tif") as src:
        dm = src.read(1, window=from_bounds(*bb, transform=src.transform)).astype("float32")
    hsx = LightSource(315, 35).hillshade(np.nan_to_num(dm, nan=np.nanmean(dm)), vert_exag=3, dx=30, dy=30)
    axs[1].imshow(hsx, cmap="gray", extent=[-2, 2, -2, 2])
    with rasterio.open(INTERIM / "s2_b04_20m.tif") as src:
        b4 = src.read(1, window=from_bounds(*bb, transform=src.transform)).astype("float32") / 1e4
    lo, hi = np.percentile(b4[b4 > 0], [1, 99.5])
    axs[2].imshow(np.clip((b4 - lo) / (hi - lo), 0, 1), cmap="gray", extent=[-2, 2, -2, 2])
    sel = (segs[:, 0] > bb[0]) & (segs[:, 0] < bb[2]) & (segs[:, 1] > bb[1]) & (segs[:, 1] < bb[3])
    for s in segs[sel]:
        axs[2].plot([(s[0] - x) / 1000, (s[2] - x) / 1000], [(s[1] - y) / 1000, (s[3] - y) / 1000],
                    color="#eda100", lw=1.2)
    for g in rd("wadi_termini").cx[bb[0]:bb[2], bb[1]:bb[3]].geometry:
        axs[1].plot((g.x - x) / 1000, (g.y - y) / 1000, "^", color="#e34948", ms=10, mec="white")
    for g in rd("projected_courses").cx[bb[0]:bb[2], bb[1]:bb[3]].geometry:
        xs_, ys_ = g.xy
        axs[1].plot((np.array(xs_) - x) / 1000, (np.array(ys_) - y) / 1000, color="#5be0ff", lw=1.5, ls="--")
    for a_ in axs:
        a_.add_patch(plt.Rectangle((-0.5, -0.5), 1, 1, fill=False, color="white", lw=1.4, ls="--"))
        a_.set_xlim(-2, 2); a_.set_ylim(-2, 2); a_.set_xticks([]); a_.set_yticks([])
    fig.subplots_adjust(wspace=0.04, left=0.01, right=0.99, top=0.99, bottom=0.01)
    save(fig, f"candidate_{cid}.png")

print("figures:", sorted(p.name for p in OUT.glob("*.png")))
