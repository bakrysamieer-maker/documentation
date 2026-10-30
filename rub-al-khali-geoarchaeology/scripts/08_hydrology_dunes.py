"""Step 8 - drainage, wadi termini under the dunes, sub-dune base surface (clues 3, 5, 6).

90 m UTM grid (context box, so whole catchments on the Dhofar plateau are included):
  * D8 flow routing on the Copernicus GLO-90 DEM (pysheds): flow accumulation, channels >= 10 km2
  * wadi termini: channel cells (catchment >= 20 km2) outside the sand whose downstream
    cell is in the sand (sand mask from step 7) -> where a valley disappears under the dunes
  * sub-dune base surface: inside the sand, the interdune-floor elevation (2 km minimum
    filter, smoothed); outside the sand, the DEM itself. Dune height = DEM - base surface.
  * projected buried courses: D8 routing on the base surface (dunes removed), traced up to
    40 km downstream of each terminus
  * closed depressions (depth) on the DEM and on the base surface; regional residual of the
    base surface (negative = locally low) -> groundwater-path low points (clue 5)

Outputs: data/interim/hydro_g90.tif, data/interim/dune_height_30m.tif,
         data/processed/{streams,wadi_termini,projected_courses}.geojson
"""
from __future__ import annotations

import numpy as np

if not hasattr(np, "in1d"):          # pysheds 0.5 still calls np.in1d, removed in NumPy 2.x
    np.in1d = np.isin

import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.features
from pysheds.grid import Grid
from pysheds.sview import Raster
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import LineString, Point

from common import INTERIM, PROCESSED, UTM, grid, read_raster, write_raster

t90, W90, H90 = grid("g90")
t30, W30, H30 = grid("g30")
CELL_KM2 = 0.09 * 0.09
D8 = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}

# ------------------------------------------------------------------ sand fraction on the 90 m grid
sand30, _ = read_raster(INTERIM / "sand_mask_30m.tif")
s30 = np.where(sand30 == 255, np.nan, sand30).astype("float32")
sand90 = np.full((H90, W90), np.nan, np.float32)
reproject(s30, sand90, src_transform=t30, src_crs=UTM, src_nodata=np.nan, dst_transform=t90,
          dst_crs=UTM, dst_nodata=np.nan, resampling=Resampling.average)
del s30, sand30
corr90, _ = read_raster(INTERIM / "corridor_mask_g90.tif")
inside90 = corr90 == 1

# ------------------------------------------------------------------ flow routing on the DEM
pg = Grid.from_raster(str(INTERIM / "dem90_utm.tif"))
dem_r = pg.read_raster(str(INTERIM / "dem90_utm.tif"))
filled = pg.fill_depressions(pg.fill_pits(dem_r))
fdir = pg.flowdir(pg.resolve_flats(filled))
acc = pg.accumulation(fdir)
acc_km2 = np.asarray(acc, dtype="float32") * CELL_KM2
dem90 = np.asarray(dem_r, dtype="float32")
dep_dem = np.asarray(filled, dtype="float32") - dem90          # closed-depression depth on the DEM
print("flow routing done; max catchment", round(float(np.nanmax(acc_km2))), "km2", flush=True)

streams_fc = pg.extract_river_network(fdir, acc > 10 / CELL_KM2)
streams = gpd.GeoDataFrame.from_features(streams_fc["features"], crs=UTM)
streams["geometry"] = streams.geometry.simplify(45)


def downstream(fd):
    fd = np.asarray(fd)
    dr = np.zeros(fd.shape, np.int8); dc = np.zeros(fd.shape, np.int8)
    for k, (a, b) in D8.items():
        dr[fd == k] = a; dc[fd == k] = b
    rr, cc = np.indices(fd.shape, dtype=np.int32)
    return np.clip(rr + dr, 0, fd.shape[0] - 1), np.clip(cc + dc, 0, fd.shape[1] - 1)


r2, c2 = downstream(fdir)
sand_down = sand90[r2, c2]
# A wadi from the plateau has a mostly sand-free catchment; inside the dune field, DEM flow
# paths weave between interdune flats and sand and would create spurious "termini".
sand_w = Raster(np.nan_to_num(sand90, nan=0).astype("float64"), viewfinder=dem_r.viewfinder)
up_sand = np.asarray(pg.accumulation(fdir, weights=sand_w), dtype="float32") / np.maximum(
    np.asarray(acc, dtype="float32"), 1)
cand = (acc_km2 >= 20) & (sand90 < 0.3) & (sand_down >= 0.6) & inside90 & (up_sand < 0.3)
# ...and the valley must actually disappear: >= 60% sand along the next ~2.7 km downstream
term = np.zeros_like(cand)
for r, c in np.argwhere(cand):
    rr, cc, vals = r, c, []
    for _ in range(30):
        rr, cc = r2[rr, cc], c2[rr, cc]
        vals.append(np.nan_to_num(sand90[rr, cc], nan=0))
    term[r, c] = np.mean(vals) >= 0.6
lab, n = ndimage.label(ndimage.binary_dilation(term, iterations=5))   # merge termini within ~450 m
tr_, tc_ = np.nonzero(term)
cells = pd.DataFrame({"lab": lab[tr_, tc_], "row": tr_, "col": tc_, "acc": acc_km2[tr_, tc_]})
best = cells.loc[cells.groupby("lab")["acc"].idxmax()]              # largest catchment per cluster
xs_, ys_ = rasterio.transform.xy(t90, best["row"].values, best["col"].values)
term_gdf = gpd.GeoDataFrame({"row": best["row"].values, "col": best["col"].values,
                             "catchment_km2": best["acc"].round(1).values,
                             "elev_m": dem90[best["row"].values, best["col"].values].round(1)},
                            geometry=[Point(a, b) for a, b in zip(xs_, ys_)], crs=UTM)
print(f"wadi termini under dunes: {len(term_gdf)} clusters from {int(term.sum())} cells "
      f"(catchment >= 20 km2)", flush=True)
del r2, c2, sand_down

# ------------------------------------------------------------------ sub-dune base surface
sand_b = np.nan_to_num(sand90, nan=0) >= 0.5
d = np.where(np.isfinite(dem90), dem90, np.nanmax(dem90))
floor = ndimage.gaussian_filter(ndimage.minimum_filter(d, size=23), sigma=11)     # 2 km min, ~1 km smooth
wgt = ndimage.gaussian_filter(sand_b.astype("float32"), sigma=5)                 # feather the sand edge
base = np.where(np.isfinite(dem90), wgt * np.minimum(d, floor) + (1 - wgt) * d, np.nan).astype("float32")
dune_h90 = np.clip(dem90 - base, 0, None)

base_r = Raster(np.where(np.isfinite(base), base, np.nan).astype("float64"), viewfinder=dem_r.viewfinder)
base_filled = pg.fill_depressions(pg.fill_pits(base_r))
fdir_b = pg.flowdir(pg.resolve_flats(base_filled))
dep_base = (np.asarray(base_filled, dtype="float32") - base)
bb = np.where(np.isfinite(base), base, np.nanmean(base))
base_resid = (base - ndimage.gaussian_filter(bb, sigma=20000 / 90)).astype("float32")

# trace projected courses from each terminus over the base-surface flow directions
fdb = np.asarray(fdir_b)
courses = []
for tid, t in term_gdf.iterrows():
    r, c, pts = t["row"], t["col"], []
    for _ in range(int(40000 / 90)):
        pts.append(rasterio.transform.xy(t90, r, c))
        step = D8.get(int(fdb[r, c]))
        if step is None:
            break
        r, c = r + step[0], c + step[1]
        if not (0 <= r < H90 and 0 <= c < W90) or not np.isfinite(base[r, c]):
            break
    if len(pts) > 3:
        courses.append({"terminus_id": int(tid), "catchment_km2": t["catchment_km2"],
                        "length_km": round(len(pts) * 0.09, 1), "geometry": LineString(pts)})
course_gdf = gpd.GeoDataFrame(courses, crs=UTM)

# ------------------------------------------------------------------ distance layers for scoring
def dist_km(mask):
    return (ndimage.distance_transform_edt(~mask) * 0.09).astype("float32")


term_mask = np.zeros((H90, W90), bool)
term_mask[term_gdf["row"].values, term_gdf["col"].values] = True
course_mask = rasterio.features.rasterize(
    [(g, 1) for g in course_gdf.geometry], out_shape=(H90, W90), transform=t90, fill=0, dtype="uint8") == 1
d_term, idx = ndimage.distance_transform_edt(~term_mask, return_indices=True)
d_term = (d_term * 0.09).astype("float32")
near_area = acc_km2[idx[0], idx[1]]                     # catchment of the nearest terminus
d_course = dist_km(course_mask)

layers = {"acc_km2": acc_km2, "dem_depression_m": dep_dem, "base_surface_m": base,
          "dune_height_m": dune_h90, "base_depression_m": dep_base, "base_residual_m": base_resid,
          "dist_terminus_km": d_term, "nearest_terminus_catchment_km2": near_area.astype("float32"),
          "dist_projected_course_km": d_course, "sand_fraction": sand90}
write_raster(INTERIM / "hydro_g90.tif", np.stack(list(layers.values())).astype("float32"), t90,
             descriptions=list(layers))

# 30 m dune height (DEM30 - base surface resampled to 30 m), sand only
dem30, _ = read_raster(INTERIM / "dem30_utm.tif")
base30 = np.full((H30, W30), np.nan, np.float32)
reproject(base, base30, src_transform=t90, src_crs=UTM, dst_transform=t30, dst_crs=UTM,
          src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
sand30, _ = read_raster(INTERIM / "sand_mask_30m.tif")
dh30 = np.where(sand30 == 1, np.clip(dem30 - base30, 0, None), np.where(sand30 == 0, 0, np.nan))
write_raster(INTERIM / "dune_height_30m.tif", dh30.astype("float32"), t30, descriptions=["dune_height_m"])

# ------------------------------------------------------------------ vectors (clip streams to corridor + catchments)
corr = gpd.read_file(PROCESSED / "aoi_corridor.geojson").query("name == 'corridor'").to_crs(UTM)
area = corr.geometry.iloc[0].buffer(60000)
streams = streams[streams.intersects(area)]
ends = [g.coords[-1] for g in streams.geometry]
er, ec = rasterio.transform.rowcol(t90, [p[0] for p in ends], [p[1] for p in ends])
er, ec = np.clip(er, 0, H90 - 1), np.clip(ec, 0, W90 - 1)
streams["catchment_km2"] = acc_km2[er, ec].round(1)
streams.to_crs(4326).to_file(PROCESSED / "streams.geojson")
term_gdf.drop(columns=["row", "col"]).to_crs(4326).to_file(PROCESSED / "wadi_termini.geojson")
course_gdf.to_crs(4326).to_file(PROCESSED / "projected_courses.geojson")
v = dh30[np.isfinite(dh30) & (sand30 == 1)]
print(f"streams: {len(streams)} segments; projected courses: {len(course_gdf)}; "
      f"dune height in sand p50/p90/p99: {np.percentile(v, [50, 90, 99]).round(1)} m")
