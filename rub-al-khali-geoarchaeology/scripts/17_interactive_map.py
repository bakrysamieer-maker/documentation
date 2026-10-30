"""Step 17 - interactive HTML map with live weight adjustment.

Builds outputs/maps/rub_al_khali_candidates.html from scripts/templates/map_template.html:
  * the six clue components, the masks and the corridor at 1 km, embedded as uint8 arrays;
    the page recomputes the weighted score in the browser when a slider moves, re-ranks the
    top-N candidates (minimum spacing) and redraws the score in Web Mercator (UTM 40N cells
    mapped to screen pixels with an in-page Transverse Mercator projection)
  * pre-rendered raster layers (Web Mercator WebP, embedded): Sentinel-2 true colour, DEM
    hillshade, sand mask, dune height, pale-crust proxy, radar sand mobility, 1972-2025 change
  * vector layers: wadis, wadi ends under dunes, projected buried courses, Shisr tracks,
    long straight lines, mapped modern roads and pipelines, dune displacement, reference points
  * default (config-weight) candidates with their snapshot thumbnails
Only Leaflet is loaded from a CDN; online base maps are optional extras.
"""
from __future__ import annotations

import base64
import json
from datetime import date

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib.colors import LightSource
from rasterio.warp import Resampling

from common import CANDIDATES, INTERIM, MAPS, OUTPUTS, PROCESSED, REFERENCE, UTM, grid, load_yaml, read_raster
from maputil import data_uri, to_mercator

cfg = load_yaml("weights.yaml")
info = json.loads((OUTPUTS / "score_info.json").read_text())
t1, W1, H1 = grid("g1km")
z = np.load(PROCESSED / "score_components_1km.npz")
names = list(cfg["weights"])
inside = z["inside"].astype(bool)
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())
w_, s_, e_, n_ = summary["download_bbox_wsen"]


def u8(a):
    return base64.b64encode(np.clip(np.nan_to_num(a) * 255, 0, 255).round().astype(np.uint8).tobytes()).decode()


arrays = {k: u8(np.where(inside, z[k], 0)) for k in names}
arrays["modern_mult"] = u8(1 - z["modern_frac"])
arrays["farm"] = u8((z["farm_frac"] > 0.1).astype(float))
arrays["seismic"] = u8(z["seismic"].astype(float))
arrays["inside"] = u8(inside.astype(float))


# ------------------------------------------------------------------ raster layers
def layer(path, band_idx, factor, resampling=Resampling.average):
    with rasterio.open(path) as src:
        h, w = src.height // factor, src.width // factor
        a = src.read(band_idx, out_shape=(h, w), resampling=resampling).astype("float32")
        tr = src.transform * src.transform.scale(src.width / w, src.height / h)
        nod = src.nodata
    if nod is not None and not np.isnan(nod):
        a[a == nod] = np.nan
    return a, tr


def rgba_ramp(a, vmin, vmax, cmap="Oranges", alpha_min=0.15):
    v = np.clip((a - vmin) / (vmax - vmin), 0, 1)
    rgba = (plt.get_cmap(cmap)(0.15 + 0.85 * np.nan_to_num(v)) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isfinite(a) & (v > 0.02), (255 * (alpha_min + (1 - alpha_min) * v)), 0).astype("uint8")
    return rgba


def overlay(rgba, tr, label, fmt="WEBP", max_px=1800, resampling=Resampling.nearest):
    merc, bounds = to_mercator(np.transpose(rgba, (2, 0, 1)), tr, src_crs=UTM, bands_first=True,
                               resampling=resampling, max_px=max_px)
    return {"url": data_uri(np.transpose(merc, (1, 2, 0)), fmt=fmt, max_px=max_px, quality=80),
            "bounds": bounds, "label": label}


images = {}
with rasterio.open(INTERIM / "s2_30m.tif") as src:
    f = 5
    h, w = src.height // f, src.width // f
    rgb = src.read([3, 2, 1], out_shape=(3, h, w), resampling=Resampling.average).astype("float32") / 1e4
    tr = src.transform * src.transform.scale(src.width / w, src.height / h)
valid = rgb.sum(0) > 0
lo, hi = np.percentile(rgb[:, valid], [1, 99.5])
tc = (np.clip((rgb - lo) / (hi - lo), 0, 1) ** 0.85 * 255).astype("uint8")
tc = np.concatenate([tc, (valid * 255).astype("uint8")[None]]).transpose(1, 2, 0)
images["s2"] = overlay(tc, tr, "Sentinel-2 true colour", resampling=Resampling.bilinear, max_px=2000)

dem, tr = layer(INTERIM / "dem30_utm.tif", 1, 4)
hs = LightSource(315, 35).hillshade(np.nan_to_num(dem, nan=np.nanmean(dem)), vert_exag=3, dx=120, dy=120)
hsr = np.dstack([(hs * 255).astype("uint8")] * 3 + [np.where(np.isfinite(dem), 255, 0).astype("uint8")])
images["hillshade"] = overlay(hsr, tr, "DEM hillshade", resampling=Resampling.bilinear, max_px=2000)

sand, tr = layer(INTERIM / "sand_mask_30m.tif", 1, 4, Resampling.mode)
srgba = np.zeros(sand.shape + (4,), "uint8")
srgba[sand == 1] = [0x1b, 0xaf, 0x7a, 110]
images["sand"] = overlay(srgba, tr, "Sand mask (Sentinel-2 redness + DEM dune relief)")

dh, tr = layer(INTERIM / "dune_height_30m.tif", 1, 4)
images["dune"] = overlay(rgba_ramp(dh, 0, 60), tr, "Dune height above sub-dune base, 0-60 m (clue 6)")

with rasterio.open(INTERIM / "s2_indices_30m.tif") as src:
    i_p = list(src.descriptions).index("pale_crust") + 1
pale, tr = layer(INTERIM / "s2_indices_30m.tif", i_p, 4, Resampling.max)
images["pale"] = overlay(rgba_ramp(pale, 1, 5), tr, "Pale-crust proxy, Sentinel-2 (clue 1, non-specific)")

with rasterio.open(INTERIM / "s1_g90.tif") as src:
    coh = src.read(list(src.descriptions).index("coh12") + 1).astype("float32")
    tr = src.transform
m90 = read_raster(INTERIM / "corridor_mask_g90.tif")[0] == 1
mob = np.where(m90, 1 - coh, np.nan)
images["mobility"] = overlay(rgba_ramp(mob, 0.1, 0.9), tr, "Radar sand mobility, 1 - S1 12-day coherence (clue 6)")

chg, tr = layer(INTERIM / "sand_change_60m.tif", 3, 2, Resampling.mode)
crgba = np.zeros(chg.shape + (4,), "uint8")
crgba[chg == 1] = [0x1b, 0xaf, 0x7a, 90]       # stable sand (aqua)
crgba[chg == 2] = [0xeb, 0x68, 0x34, 200]      # sand gained since 1972 (orange)
crgba[chg == 3] = [0x2a, 0x78, 0xd6, 200]      # sand lost since 1972 (blue)
images["change"] = overlay(crgba, tr, "Sand cover 1972-73 vs 2024-25 (Landsat-1 MSS vs Sentinel-2)")


# ------------------------------------------------------------------ vectors
def gj(gdf, cols=(), precision=1e-5):
    g = gdf.to_crs(4326)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g = g[[c for c in cols if c in g.columns] + ["geometry"]].copy()
    g["geometry"] = shapely.set_precision(g.geometry.values, precision)
    return json.loads(g.to_json(drop_id=True))


rd = lambda name: gpd.read_file(PROCESSED / f"{name}.geojson")
streams = rd("streams")
streams = streams[streams["catchment_km2"] >= 50]
streams = streams.to_crs(UTM)
streams["geometry"] = streams.simplify(60)
corr = rd("aoi_corridor").query("name == 'corridor'")
roads = rd("modern_roads_tracks").to_crs(UTM)
roads["geometry"] = roads.simplify(20)
infra = rd("modern_infrastructure")
pipes = infra[infra["class"].isin(["pipeline", "power_line", "minor_line"])]
disp = rd("dune_displacement").to_crs(UTM)
disp = disp[disp["corr_error"] < disp["corr_error"].quantile(0.5)]
k = 3.0                                                     # exaggerate arrows x3 for visibility
disp["geometry"] = [shapely.LineString([(p.x, p.y), (p.x + k * s * np.sin(np.radians(a)), p.y + k * s * np.cos(np.radians(a)))])
                    for p, s, a in zip(disp.geometry, disp["shift_m"], disp["azimuth_deg"])]
refs = pd.read_csv(REFERENCE / "reference_points.csv").dropna(subset=["lat"])
refs_g = gpd.GeoDataFrame(refs, geometry=gpd.points_from_xy(refs.lon, refs.lat), crs=4326)
vectors = {
    "corridor": gj(corr), "borders": gj(gpd.read_file(PROCESSED / "borders_context.geojson")),
    "streams": gj(streams, ["catchment_km2"]), "termini": gj(rd("wadi_termini"), ["catchment_km2", "elev_m"]),
    "courses": gj(rd("projected_courses"), ["catchment_km2", "length_km"]),
    "tracks": gj(rd("shisr_tracks"), ["bearing_deg", "segment_km", "detected_to_km", "mapped_modern_fraction", "part"]),
    "straight": gj(rd("long_straight_lines"), ["azimuth_deg", "extent_km"]),
    "roads": gj(roads, ["class", "names"]), "pipes": gj(pipes, ["class"]),
    "disp": gj(disp, ["shift_m", "rate_m_per_yr", "azimuth_deg"]),
    "refs": gj(refs_g, ["name", "role", "notes", "source"]),
}

# ------------------------------------------------------------------ default candidates with thumbnails
cand = pd.read_csv(CANDIDATES / "top20_candidates.csv")
from pyproj import Transformer
to_utm = Transformer.from_crs(4326, UTM, always_xy=True)
defaults = []
for _, c in cand.iterrows():
    x, y = to_utm.transform(c["lon"], c["lat"])
    r, col = rasterio.transform.rowcol(t1, x, y)
    th = CANDIDATES / "snapshots" / f"{c['candidate_id']}_thumb.jpg"
    defaults.append({"id": c["candidate_id"], "cell": int(r * W1 + col),
                     "explanations": c["natural_or_modern_explanations"], "nearest": c["nearest_reference"],
                     "thumb": ("data:image/jpeg;base64," + base64.b64encode(th.read_bytes()).decode()) if th.exists() else ""})

labels = {
    "wadi_terminus": {"short": "C3 wadi", "long": "Clue 3 - wadi end under dunes"},
    "spring_minerals": {"short": "C1 springs", "long": "Clue 1 - spring-type minerals"},
    "groundwater_lows": {"short": "C5 low", "long": "Clue 5 - groundwater-path low"},
    "tracks_alignments": {"short": "C2/4 tracks", "long": "Clue 2/4 - tracks and alignments"},
    "geometric_anomalies": {"short": "C4 geometry", "long": "Clue 4 - geometric anomalies"},
    "thin_sand": {"short": "C6 thin sand", "long": "Clue 6 - thin or recent sand"},
}
legend = [
    {"color": "#ffffff", "label": "candidate (labelled C01...)"},
    {"color": "#e34948", "label": "known site (Shisr)"},
    {"color": "#2a78d6", "label": "wadi / wadi end", "line": True},
    {"color": "#2a78d6", "label": "projected buried course", "line": True, "dash": True},
    {"color": "#1baf7a", "label": "track from Shisr (dashed = +40 km)", "line": True},
    {"color": "#898781", "label": "track on mapped modern road", "line": True},
    {"color": "#c3c2b7", "label": "long straight line (seismic-like)", "line": True, "dash": True},
    {"color": "#52514e", "label": "mapped modern road / track", "line": True},
    {"color": "#1baf7a", "label": "stable sand 1972-2025"},
    {"color": "#eb6834", "label": "sand gained since 1972"},
    {"color": "#2a78d6", "label": "sand lost since 1972"},
    {"color": "#eb6834", "label": "dune displacement (x3)", "line": True},
]
method = [
    f"Clue 1 source: {info.get('spring_minerals_source')}.",
    "Clue 3: D8 flow routing on Copernicus GLO-90; termini where a mostly sand-free catchment (>= 20 km2) "
    "enters the sand; projected courses routed on a sub-dune base surface (interdune floors).",
    "Clue 5: closed lows on the base surface, regional low, wet surfaces (MNDWI).",
    "Clues 2/4: Shisr-radial line segments from Sentinel-2 20 m; tracks on mapped modern roads are excluded "
    "from the score; trilith alignments need published site coordinates (not yet available).",
    "Clue 4: corners, circles and curvilinear lines away from modern features; "
    f"ML: {info.get('ml')}.",
    "Clue 6: dune height, sand change 1972-73 to 2024-25 (Landsat-1 MSS vs Sentinel-2), radar-bright sand.",
    "Masks: OSM/Overture roads, buildings, infrastructure, farmland; image-detected farms; seismic-like lines.",
    "Grid: 1 km cells in UTM 40N; component scores rescaled 0-1 inside the corridor (1st-99th percentile).",
]

DATA = {
    "asof": f"Built {date.today().isoformat()} from scripts in rub-al-khali-geoarchaeology/.",
    "grid": {"a": t1.a, "c": t1.c, "e": t1.e, "f": t1.f, "W": W1, "H": H1},
    "components": names, "labels": labels, "weights": cfg["weights"],
    "seismic_multiplier": cfg["masks"]["seismic_grid_multiplier"], "arrays": arrays,
    "canvas_bounds": [[s_, w_], [n_, e_]], "images": images, "vectors": vectors,
    "default_candidates": defaults, "legend": legend, "method": method,
}
html = (MAPS.parent.parent / "scripts" / "templates" / "map_template.html").read_text(encoding="utf-8")
out = MAPS / "rub_al_khali_candidates.html"
out.write_text(html.replace("__DATA__", json.dumps(DATA, separators=(",", ":"))), encoding="utf-8")
print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB")
