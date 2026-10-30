"""Step 3 - study-area preview map (interactive HTML + static PNG). No large downloads.

Layers: Copernicus GLO-90 hillshade, Sentinel-2 winter 2025 quick-look mosaic,
proposed corridor / download box / context box, borders (Natural Earth 1:10m),
reference points with uncertainty circles and sources, and regional elevation
contours of a 15 km-smoothed DEM (a first look at the Dhofar -> NE regional slope).

Outputs: outputs/maps/00_study_area.html, outputs/figures/00_study_area.png,
         data/processed/regional_contours.geojson
"""
from __future__ import annotations

import base64
import io
import json

import folium
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from folium import plugins
from matplotlib.colors import LightSource
from PIL import Image
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy import ndimage
from shapely.geometry import LineString, box

from common import FIGURES, INTERIM, MAPS, OUTPUTS, PROCESSED, REFERENCE, load_yaml

cfg = load_yaml("aoi.yaml")
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())
corr = gpd.read_file(PROCESSED / "aoi_corridor.geojson")
boxes = gpd.read_file(PROCESSED / "aoi_boxes.geojson")
refs = pd.read_csv(REFERENCE / "reference_points.csv")
ctx = cfg["context_bbox"]

# ------------------------------------------------------------------ DEM, hillshade, regional surface
with rasterio.open(INTERIM / "dem90_context.tif") as src:
    dem = src.read(1).astype("float32")
    t = src.transform
lat_mid = (ctx[1] + ctx[3]) / 2
dx = abs(t.a) * 111320 * np.cos(np.radians(lat_mid))
dy = abs(t.e) * 110570
sea = dem <= 0.5

ls = LightSource(azdeg=315, altdeg=35)
hs = ls.hillshade(np.where(sea, 0, dem), vert_exag=4, dx=dx, dy=dy)

# regional surface: block-average to ~900 m then Gaussian (sigma ~15 km)
f = 10
small = dem[: dem.shape[0] // f * f, : dem.shape[1] // f * f].reshape(
    dem.shape[0] // f, f, dem.shape[1] // f, f).mean(axis=(1, 3))
small_sea = small <= 0.5
filled = np.where(small_sea, np.nan, small)
reg = ndimage.gaussian_filter(np.nan_to_num(filled, nan=np.nanmean(filled)), sigma=15000 / (dx * f))
reg[small_sea] = np.nan

# contour lines of the regional surface -> GeoJSON
xs = ctx[0] + (np.arange(reg.shape[1]) + 0.5) * abs(t.a) * f
ys = ctx[3] - (np.arange(reg.shape[0]) + 0.5) * abs(t.e) * f
levels = np.arange(50, 1000, 50)
cs = plt.contour(xs, ys, reg, levels=levels)
lines = []
for lev, segs in zip(cs.levels, cs.allsegs):
    for seg in segs:
        if len(seg) > 5:
            lines.append({"elev_m": int(lev), "geometry": LineString(seg)})
plt.close("all")
contours = gpd.GeoDataFrame(lines, crs=4326)
contours.to_file(PROCESSED / "regional_contours.geojson")

# lowest point of the regional surface inside the context box but north of 19.5N
# (the inland depression the groundwater path heads for), excluding the sea
yy, xx = np.meshgrid(ys, xs, indexing="ij")
mask = (yy > 19.5) & ~np.isnan(reg)
iy, ix = np.unravel_index(np.nanargmin(np.where(mask, reg, np.nan)), reg.shape)
low_pt = (float(xs[ix]), float(ys[iy]), float(reg[iy, ix]))
print(f"Regional (15 km-smoothed) low north of 19.5N: lon {low_pt[0]:.2f}, lat {low_pt[1]:.2f}, "
      f"~{low_pt[2]:.0f} m a.s.l.")

# ------------------------------------------------------------------ borders
ne = gpd.read_file(REFERENCE / "ne_10m_admin_0_boundary_lines_land.geojson")
borders = gpd.clip(ne, box(*ctx))[["NAME", "geometry"]] if "NAME" in ne else gpd.clip(ne, box(*ctx))
borders.to_file(PROCESSED / "borders_context.geojson")


# ------------------------------------------------------------------ helpers: warp to Web Mercator and encode
def to_mercator(arr, src_t, src_crs="EPSG:4326", bands_first=False, resampling=Resampling.bilinear):
    a = arr if bands_first else arr[None]
    h, w = a.shape[1:]
    b = rasterio.transform.array_bounds(h, w, src_t)
    dst_t, W, H = calculate_default_transform(src_crs, "EPSG:3857", w, h, *b)
    out = np.zeros((a.shape[0], H, W), a.dtype)
    for i in range(a.shape[0]):
        reproject(a[i], out[i], src_transform=src_t, src_crs=src_crs, dst_transform=dst_t,
                  dst_crs="EPSG:3857", resampling=resampling)
    wb = rasterio.transform.array_bounds(H, W, dst_t)
    from pyproj import Transformer
    tr = Transformer.from_crs(3857, 4326, always_xy=True)
    lo0, la0 = tr.transform(wb[0], wb[1])
    lo1, la1 = tr.transform(wb[2], wb[3])
    return out, [[la0, lo0], [la1, lo1]]


def data_uri(rgb_or_rgba: np.ndarray, fmt="PNG", max_px=2200, quality=85):
    img = Image.fromarray(rgb_or_rgba)
    if max(img.size) > max_px:
        s = max_px / max(img.size)
        img = img.resize((int(img.size[0] * s), int(img.size[1] * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format=fmt, **({"quality": quality} if fmt in ("JPEG", "WEBP") else {"optimize": True}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


# hillshade tinted by elevation
norm = np.clip((dem - 0) / 1200, 0, 1)
cmap = plt.get_cmap("terrain")
tint = cmap(0.25 + 0.75 * norm)[..., :3]
shade = (0.55 * tint + 0.45 * hs[..., None]) * (0.6 + 0.4 * hs[..., None])
shade[sea] = [0.70, 0.80, 0.90]
rgb = (np.clip(shade, 0, 1) * 255).astype("uint8").transpose(2, 0, 1)
hs_merc, hs_bounds = to_mercator(rgb, t, bands_first=True)
hs_uri = data_uri(hs_merc.transpose(1, 2, 0), fmt="JPEG")

with rasterio.open(INTERIM / "s2_overview_mosaic.tif") as src:
    s2 = dict(zip(src.descriptions, src.read()))
    ql_t = src.transform


def stretch(bands_, lo=1, hi=99.5, gamma=0.9):
    out = []
    for b in bands_:
        v = b[~np.isnan(b)]
        p0, p1 = np.percentile(v, [lo, hi])
        out.append(np.clip((b - p0) / (p1 - p0), 0, 1) ** gamma)
    rgb_ = (np.nan_to_num(np.stack(out)) * 255).astype("uint8")
    a = np.where(np.isnan(bands_[0]), 0, 255).astype("uint8")
    return np.concatenate([rgb_, a[None]])


tc = stretch([s2["B04"], s2["B03"], s2["B02"]])          # true colour
sw = stretch([s2["B12"], s2["B11"], s2["B02"]])          # SWIR false colour (geology)
ql = tc[:3]
alpha = tc[3]
tc_merc, ql_bounds = to_mercator(tc, ql_t, bands_first=True, resampling=Resampling.nearest)
sw_merc, _ = to_mercator(sw, ql_t, bands_first=True, resampling=Resampling.nearest)
ql_uri = data_uri(tc_merc.transpose(1, 2, 0), fmt="WEBP", max_px=1800)   # WebP keeps transparency
sw_uri = data_uri(sw_merc.transpose(1, 2, 0), fmt="WEBP", max_px=1800)

# ------------------------------------------------------------------ interactive map
m = folium.Map(location=[19.5, 54.0], zoom_start=7, tiles=None, control_scale=True)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri, Maxar, Earthstar Geographics", name="Esri World Imagery (online)").add_to(m)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap (online)").add_to(m)
folium.raster_layers.ImageOverlay(hs_uri, bounds=hs_bounds, opacity=1.0,
                                  name="Copernicus DEM 90 m - hillshade (offline)").add_to(m)
folium.raster_layers.ImageOverlay(ql_uri, bounds=ql_bounds, opacity=1.0, show=False,
                                  name="Sentinel-2 L2A true colour ~200 m, Dec 2024-Feb 2025 (offline)").add_to(m)
folium.raster_layers.ImageOverlay(sw_uri, bounds=ql_bounds, opacity=1.0, show=False,
                                  name="Sentinel-2 SWIR false colour B12-B11-B2 ~200 m (offline)").add_to(m)

folium.GeoJson(contours, name="Regional elevation contours (15 km-smoothed DEM, 50 m)",
               style_function=lambda f: {"color": "#7a4b00", "weight": 1, "opacity": 0.6},
               tooltip=folium.GeoJsonTooltip(["elev_m"], aliases=["smoothed elevation (m)"])).add_to(m)
folium.GeoJson(borders, name="International borders (Natural Earth 1:10m, approx.)",
               style_function=lambda f: {"color": "#e8e8e8", "weight": 2.5, "dashArray": "8 4"}).add_to(m)

box_style = {
    "context_bbox": {"color": "#888888", "weight": 1.5, "fill": False, "dashArray": "4 6"},
    "dem_extent": {"color": "#1f78b4", "weight": 1.5, "fill": False, "dashArray": "2 4"},
    "download_bbox": {"color": "#ff7f00", "weight": 2.5, "fill": False},
}
labels = {"context_bbox": "Context box (90 m DEM only) 51.5-56.5E, 17-22N",
          "dem_extent": "30 m DEM extent (incl. upstream catchments to 17N)",
          "download_bbox": "Proposed download bounding box (W {0:.2f}, S {1:.2f}, E {2:.2f}, N {3:.2f})".format(
              *summary["download_bbox_wsen"])}
for _, r in boxes.iterrows():
    folium.GeoJson(r.geometry.__geo_interface__, name=labels[r["name"]],
                   style_function=lambda f, s=box_style[r["name"]]: s,
                   tooltip=labels[r["name"]]).add_to(m)
c = corr[corr["name"] == "corridor"].iloc[0]
folium.GeoJson(c.geometry.__geo_interface__,
               name=f"Proposed analysis corridor ({summary['area_km2']['corridor']:,} km2)",
               style_function=lambda f: {"color": "#e31a1c", "weight": 3, "fillColor": "#e31a1c",
                                         "fillOpacity": 0.08},
               tooltip=f"Analysis corridor: 150 km wide Shisr -> Umm Al Heesh band + NW fan "
                       f"({summary['area_km2']['corridor']:,} km2)").add_to(m)

pts = folium.FeatureGroup(name="Reference points (with positional uncertainty)")
colors = {"known_site": "red", "natural_reference": "blue"}
for _, r in refs.dropna(subset=["lat"]).iterrows():
    html = (f"<b>{r['name']}</b> {r['name_ar'] if isinstance(r['name_ar'], str) else ''}<br>"
            f"{r['lat']:.4f} N, {r['lon']:.4f} E &nbsp;(±{r['uncertainty_km']} km, {r['position_quality']})<br>"
            f"<i>{r['notes']}</i><br>Source: <a href='{r['source_url']}' target='_blank'>{r['source']}</a>")
    folium.Marker([r["lat"], r["lon"]], popup=folium.Popup(html, max_width=380),
                  tooltip=r["name"],
                  icon=folium.Icon(color=colors.get(r["role"], "gray"),
                                   icon="star" if r["role"] == "known_site" else "info-sign")).add_to(pts)
    folium.Circle([r["lat"], r["lon"]], radius=float(r["uncertainty_km"]) * 1000,
                  color=colors.get(r["role"], "gray"), weight=1, fill=False, dash_array="3 3").add_to(pts)
folium.CircleMarker([low_pt[1], low_pt[0]], radius=7, color="#6a3d9a", fill=True,
                    tooltip=f"Lowest point of 15 km-smoothed DEM north of 19.5N (~{low_pt[2]:.0f} m): "
                            "regional depression the groundwater path heads for (data-derived)").add_to(pts)
pts.add_to(m)

note = f"""
<div style="position: fixed; bottom: 18px; left: 10px; z-index: 9999; background: rgba(255,255,255,0.93);
 padding: 8px 10px; border: 1px solid #999; border-radius: 4px; font: 12px/1.35 sans-serif; max-width: 360px;">
<b>Study-area proposal (step 1 checkpoint)</b><br>
<span style="color:#e31a1c">&#9632;</span> Analysis corridor {summary['area_km2']['corridor']:,} km&sup2;:
150 km band Shisr&rarr;Umm Al Heesh (bearing {summary['corridor_bearing_deg']}&deg;, {summary['shisr_to_umm_al_heesh_km']} km) + NW fan (140 km)<br>
<span style="color:#ff7f00">&#9633;</span> Download bbox {summary['area_km2']['download_bbox']:,} km&sup2;<br>
Positions are candidates for verification; nothing here is a discovery.
Desk study only. Borders are approximate (Natural Earth 1:10m).
</div>"""
m.get_root().html.add_child(folium.Element(note))
plugins.MousePosition(position="topright", separator=" | ", num_digits=4,
                      prefix="lat | lon:").add_to(m)
plugins.MeasureControl(primary_length_unit="kilometers").add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
m.save(MAPS / "00_study_area.html")

# ------------------------------------------------------------------ static PNG
fig, axes = plt.subplots(1, 2, figsize=(17, 9.2), constrained_layout=True)
ext = [ctx[0], ctx[2], ctx[1], ctx[3]]
ax = axes[0]
ax.imshow(rgb.transpose(1, 2, 0), extent=ext, origin="upper")
cl = ax.contour(xs, ys, reg, levels=levels[::2], colors="#5a3800", linewidths=0.6, alpha=0.7)
ax.clabel(cl, fmt="%d m", fontsize=7)
ax.set_title("Copernicus GLO-90 DEM hillshade + 15 km-smoothed elevation contours (100 m)", fontsize=11)
ax2 = axes[1]
qb = rasterio.transform.array_bounds(*ql.shape[1:], ql_t)
ax2.imshow(np.full((10, 10, 3), 235, np.uint8), extent=ext)
ax2.imshow(np.dstack([ql.transpose(1, 2, 0), alpha]), extent=[qb[0], qb[2], qb[1], qb[3]])
ax2.set_title("Sentinel-2 L2A true colour, ~200 m (clearest Dec 2024-Feb 2025 scenes)", fontsize=11)
for a in axes:
    borders.plot(ax=a, color="white", lw=1.6, ls="--")
    boxes[boxes["name"] == "download_bbox"].boundary.plot(ax=a, color="#ff7f00", lw=1.8)
    corr[corr["name"] == "corridor"].boundary.plot(ax=a, color="#e31a1c", lw=2.2)
    for _, r in refs.dropna(subset=["lat"]).iterrows():
        a.plot(r["lon"], r["lat"], marker="*" if r["role"] == "known_site" else "o",
               ms=13 if r["role"] == "known_site" else 7,
               color="red" if r["role"] == "known_site" else "#1f4e9c", mec="white", mew=0.8)
        a.annotate(r["name"].split(" (")[0], (r["lon"], r["lat"]), xytext=(6, 4),
                   textcoords="offset points", fontsize=8.5, color="black",
                   bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.75, lw=0))
    a.plot(low_pt[0], low_pt[1], marker="v", ms=9, color="#6a3d9a", mec="white")
    a.annotate("smoothed-DEM low", (low_pt[0], low_pt[1]), xytext=(6, -12), textcoords="offset points",
               fontsize=8, color="#6a3d9a")
    a.set_xlim(ctx[0], ctx[2]); a.set_ylim(ctx[1], ctx[3])
    a.set_aspect(1 / np.cos(np.radians(lat_mid)))
    a.set_xlabel("Longitude (°E)"); a.set_ylabel("Latitude (°N)")
    a.text(ctx[0] + 0.1, ctx[1] + 0.1, "Saudi Arabia", fontsize=9, color="white", alpha=0.0)
axes[0].text(52.0, 21.3, "SAUDI ARABIA", color="#333", fontsize=10, weight="bold")
axes[0].text(55.3, 18.6, "OMAN", color="#333", fontsize=10, weight="bold")
axes[0].text(51.6, 17.4, "YEMEN", color="#333", fontsize=10, weight="bold")
fig.suptitle(f"Proposed study area - red: analysis corridor ({summary['area_km2']['corridor']:,} km²), "
             f"orange: download bbox W{summary['download_bbox_wsen'][0]:.2f} S{summary['download_bbox_wsen'][1]:.2f} "
             f"E{summary['download_bbox_wsen'][2]:.2f} N{summary['download_bbox_wsen'][3]:.2f} "
             f"({summary['area_km2']['download_bbox']:,} km²); borders approximate (Natural Earth)",
             fontsize=11.5)
fig.savefig(FIGURES / "00_study_area.png", dpi=130)
print("wrote", MAPS / "00_study_area.html", "and", FIGURES / "00_study_area.png")
