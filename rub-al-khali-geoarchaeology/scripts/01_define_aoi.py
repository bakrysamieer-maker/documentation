"""Step 1 - define the study area and inventory the data it needs (no imagery is downloaded).

Builds:
  * a 150 km wide corridor along the Shisr -> Umm Al Heesh line (geodesic offsets),
  * a north-west fan from Shisr (tracks into the sands, Maitan area),
  * the bounding box of both (the download extent),
and lists the Copernicus DEM, Sentinel-2 (MGRS) and Sentinel-1 tiles that intersect it,
with real file sizes from HTTP HEAD requests where cheap.

Outputs: data/processed/aoi_*.geojson, outputs/aoi_summary.json
"""
from __future__ import annotations

import math
import re

import geopandas as gpd
import mgrs
import numpy as np
import requests
from pyproj import Geod
from shapely.geometry import Point, Polygon, box, mapping
from shapely.ops import unary_union

from common import PROCESSED, OUTPUTS, load_yaml, write_json, human_bytes

GEOD = Geod(ellps="WGS84")
cfg = load_yaml("aoi.yaml")
A = cfg["anchors"]


def fwd(lon, lat, az, dist_km):
    lo, la, _ = GEOD.fwd(lon, lat, az, dist_km * 1000.0)
    return lo, la


# ---------------------------------------------------------------- corridor band
s_lon, s_lat = A["shisr"]["lon"], A["shisr"]["lat"]
n_lon, n_lat = A["umm_al_heesh"]["lon"], A["umm_al_heesh"]["lat"]
az, back_az, dist_m = GEOD.inv(s_lon, s_lat, n_lon, n_lat)
hw, ext = cfg["corridor"]["half_width_km"], cfg["corridor"]["extend_km"]

start = fwd(s_lon, s_lat, back_az, ext)            # extend south of Shisr
total_km = dist_m / 1000.0 + 2 * ext
centre = [fwd(*start, az, d) for d in np.linspace(0, total_km, 40)]
# local azimuth along the geodesic for the perpendicular offsets
left, right = [], []
for (lo, la) in centre:
    a_here, _, _ = GEOD.inv(lo, la, *fwd(lo, la, az, 1.0))
    left.append(fwd(lo, la, a_here - 90, hw))
    right.append(fwd(lo, la, a_here + 90, hw))
band = Polygon(right + left[::-1])

# ---------------------------------------------------------------- NW fan
f = cfg["nw_fan"]
arc = [fwd(s_lon, s_lat, b, f["radius_km"])
       for b in np.arange(f["bearing_from_deg"], f["bearing_to_deg"] + 0.1, 2.5)]
fan = Polygon([(s_lon, s_lat)] + arc)

corridor = unary_union([band, fan]).buffer(0)
w, s, e, n = corridor.bounds
round_out = lambda v, step, up: (math.ceil if up else math.floor)(v / step) * step
bbox = (round_out(w, 0.05, False), round_out(s, 0.05, False),
        round_out(e, 0.05, True), round_out(n, 0.05, True))
dem_ext = (bbox[0], cfg["dem_south_lat"], bbox[2], bbox[3])
ctx = tuple(cfg["context_bbox"])

# equal-area sizes
ea = "ESRI:54034"  # World Cylindrical Equal Area
areas = gpd.GeoSeries([corridor, box(*bbox), box(*ctx)], crs=4326).to_crs(ea).area / 1e6

# ---------------------------------------------------------------- write vectors
gpd.GeoDataFrame(
    {"name": ["corridor", "nw_fan", "band"], "area_km2": [
        *gpd.GeoSeries([corridor, fan, band], crs=4326).to_crs(ea).area.div(1e6).round(0)]},
    geometry=[corridor, fan, band], crs=4326).to_file(PROCESSED / "aoi_corridor.geojson")
gpd.GeoDataFrame({"name": ["download_bbox", "dem_extent", "context_bbox"]},
                 geometry=[box(*bbox), box(*dem_ext), box(*ctx)], crs=4326
                 ).to_file(PROCESSED / "aoi_boxes.geojson")


# ---------------------------------------------------------------- DEM tiles
def dem_tiles(ext, geom=None):
    out = []
    for la in range(math.floor(ext[1]), math.ceil(ext[3])):
        for lo in range(math.floor(ext[0]), math.ceil(ext[2])):
            if geom is None or geom.intersects(box(lo, la, lo + 1, la + 1)):
                out.append((la, lo))
    return out


def dem_url(la, lo, res):
    code = 10 if res == 30 else 30
    name = f"Copernicus_DSM_COG_{code}_N{la:02d}_00_E{lo:03d}_00_DEM"
    return f"https://copernicus-dem-{res}m.s3.amazonaws.com/{name}/{name}.tif"


def head_size(url):
    try:
        r = requests.head(url, timeout=30)
        return int(r.headers.get("Content-Length", 0)) if r.ok else 0
    except requests.RequestException:
        return 0


# 30 m DEM: corridor plus a southern extension (upstream catchments on the Nejd)
south_ext = box(bbox[0], cfg["dem_south_lat"], bbox[2], s + 0.5)
dem30_geom = unary_union([corridor, south_ext.intersection(box(w, 0, e, 90))])
dem30 = [(la, lo, dem_url(la, lo, 30)) for la, lo in dem_tiles(dem_ext, dem30_geom)]
dem90 = [(la, lo, dem_url(la, lo, 90)) for la, lo in dem_tiles(ctx)]
dem30_bytes = sum(head_size(u) for *_, u in dem30)
dem90_bytes = sum(head_size(u) for *_, u in dem90)

# ---------------------------------------------------------------- Sentinel-2 MGRS tiles
m = mgrs.MGRS()
lons = np.arange(w, e, 0.03)
lats = np.arange(s, n, 0.03)
tiles = set()
for la in lats:
    for lo in lons:
        if corridor.contains(Point(lo, la)):
            tiles.add(m.toMGRS(la, lo, MGRSPrecision=0)[:5])

# Sentinel-2 does not produce every MGRS square: near the 54°E UTM-zone boundary the
# 40QA* squares do not exist and are covered by the overlapping 39QZ* tiles instead.
# Keep only squares that exist in the archive.
def s2_tile_exists(t):
    url = ("https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/?list-type=2"
           f"&prefix=sentinel-2-c1-l2a/{int(t[:2])}/{t[2]}/{t[3:5]}/&max-keys=1")
    return "<Key>" in requests.get(url, timeout=60).text


s2_missing = sorted(t for t in tiles if not s2_tile_exists(t))
s2_tiles = sorted(tiles - set(s2_missing))

# ---------------------------------------------------------------- Sentinel-1 seasonal tiles
# Kellndorfer et al. 2022 global seasonal coherence/backscatter: 1x1 deg tiles named by
# their upper-left corner (N19E054 covers 18-19N, 54-55E).
s1_tiles = [f"N{la + 1:02d}E{lo:03d}" for la, lo in dem_tiles(bbox, corridor)]

summary = {
    "anchors": A,
    "corridor_bearing_deg": round(az % 360, 1),
    "shisr_to_umm_al_heesh_km": round(dist_m / 1000, 1),
    "download_bbox_wsen": bbox,
    "dem_extent_wsen": dem_ext,
    "context_bbox_wsen": ctx,
    "area_km2": {"corridor": round(areas[0]), "download_bbox": round(areas[1]),
                 "context_bbox": round(areas[2])},
    "dem30_tiles": [f"N{la}E{lo:03d}" for la, lo, _ in dem30],
    "dem30_size": human_bytes(dem30_bytes),
    "dem90_tiles": len(dem90),
    "dem90_size": human_bytes(dem90_bytes),
    "sentinel2_mgrs_tiles": s2_tiles,
    "sentinel2_squares_not_in_archive": s2_missing,
    "sentinel1_seasonal_tiles": s1_tiles,
}
write_json(OUTPUTS / "aoi_summary.json", summary)
for k, v in summary.items():
    print(f"{k}: {v}")
