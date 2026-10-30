"""Step 15 - weighted candidate score per 1 km cell and the top-20 candidate list.

Every clue layer is aggregated to the 1 km grid and rescaled to 0-1 inside the corridor
(1st-99th percentile). Weights and masks come from config/weights.yaml. A clue counts as
"satisfied" for a cell when its component score is >= 0.5.

Components
  wadi_terminus       clue 3: near a wadi end under the dunes (weighted by catchment size)
                      or its projected buried course (x 0.7, more speculative)
  spring_minerals     clue 1: ASTER carbonate/sulphate indices if step 13 has run; otherwise
                      the Sentinel-2 pale-crust proxy, multiplied by 0.5 (non-specific)
  groundwater_lows    clue 5: closed lows on the sub-dune base surface, regional low, wet surfaces
  tracks_alignments   clues 2+4: near Shisr-radial tracks NOT coinciding with mapped modern
                      roads; near trilith alignment lines when published sites are available
  geometric_anomalies clue 4: corners, circles, curvilinear lines away from modern features
                      (+ random-forest similarity to known sites when >= 10 are available)
  thin_sand           clue 6: low dune height, sand gained/lost since 1972, radar-bright sand
Masks: distance to modern features, farm exclusion, seismic-grid multiplier.

Outputs: data/processed/score_1km.tif, data/processed/score_components_1km.npz,
         data/processed/candidates.geojson, outputs/candidates/top20_candidates.csv
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.warp import Resampling, reproject
from shapely import distance as sdist, points

from common import (CANDIDATES, INTERIM, OUTPUTS, PROCESSED, RAW, REFERENCE, UTM, download, grid,
                    load_yaml, read_raster, write_json, write_raster)

cfg = load_yaml("weights.yaml")
t1, W1, H1 = grid("g1km")
t30, W30, H30 = grid("g30")
t90, W90, H90 = grid("g90")
t60 = rasterio.transform.from_origin(t30.c, t30.f, 60, 60)
corr1, _ = read_raster(INTERIM / "corridor_mask_g1km.tif")
inside = corr1 == 1


def to_1km(arr, tr, how=Resampling.average):
    out = np.full((H1, W1), np.nan, np.float32)
    reproject(arr.astype("float32"), out, src_transform=tr, src_crs=UTM, src_nodata=np.nan,
              dst_transform=t1, dst_crs=UTM, dst_nodata=np.nan, resampling=how)
    return out


def band(path, name):
    with rasterio.open(path) as src:
        return src.read(list(src.descriptions).index(name) + 1).astype("float32"), src.transform


def scale01(a):
    v = a[inside & np.isfinite(a)]
    if v.size == 0 or np.nanmax(v) == np.nanmin(v):
        return np.zeros_like(a)
    lo, hi = np.percentile(v, [1, 99])
    return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)


comp, info = {}, {}

# ------------------------------------------------------------------ clue 3: wadi termini / buried courses
d_term, _ = band(INTERIM / "hydro_g90.tif", "dist_terminus_km")
catch, _ = band(INTERIM / "hydro_g90.tif", "nearest_terminus_catchment_km2")
d_course, _ = band(INTERIM / "hydro_g90.tif", "dist_projected_course_km")
w_area = np.clip(np.log10(np.maximum(catch, 1)) / 3, 0.3, 1.0)            # 1000 km2 -> 1
s_wadi90 = np.maximum(np.exp(-d_term / 3.0) * w_area, 0.7 * np.exp(-d_course / 1.5))
comp["wadi_terminus"] = scale01(to_1km(s_wadi90, t90))

# ------------------------------------------------------------------ clue 1: spring minerals
aster = INTERIM / "aster_g90.tif"
if aster.exists():
    with rasterio.open(aster) as src:
        a = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
    z = lambda x: (x - np.nanmedian(x)) / (np.nanstd(x) + 1e-9)
    s_min90 = np.nanmean(np.stack([z(a["cli"]), z(a["ci"]), z(a["si"])]), axis=0)
    comp["spring_minerals"] = scale01(to_1km(s_min90, t90))
    info["spring_minerals_source"] = "ASTER (L1T SWIR calcite index; GED TIR carbonate and sulphate indices)"
else:
    pale, _ = band(INTERIM / "s2_indices_30m.tif", "pale_crust")
    frac = np.where(np.isfinite(pale), (pale > 2.0).astype("float32"), np.nan)    # top few % of crust signal
    comp["spring_minerals"] = 0.5 * scale01(to_1km(frac, t30))
    info["spring_minerals_source"] = ("Sentinel-2 pale-crust PROXY (bright + SWIR-absorbing + not iron-stained), "
                                      "x0.5 because it cannot separate carbonate, gypsum, calcrete or sabkha salt")
    del pale, frac

# ------------------------------------------------------------------ clue 5: groundwater-path low points
dep_b, _ = band(INTERIM / "hydro_g90.tif", "base_depression_m")
resid, _ = band(INTERIM / "hydro_g90.tif", "base_residual_m")
mndwi, _ = band(INTERIM / "s2_indices_30m.tif", "mndwi")
wet = np.where(np.isfinite(mndwi), (mndwi > -0.05).astype("float32"), np.nan)
del mndwi
s_gw = (0.4 * scale01(to_1km(np.clip(dep_b, 0, 10), t90)) +
        0.3 * scale01(to_1km(np.clip(-resid, 0, 30), t90)) +
        0.3 * scale01(to_1km(wet, t30)))
comp["groundwater_lows"] = scale01(s_gw)
del wet

# ------------------------------------------------------------------ clues 2+4: tracks and alignments
rr, cc = np.indices((H1, W1))
xs, ys = rasterio.transform.xy(t1, rr.ravel(), cc.ravel())
cell_pts = points(np.c_[xs, ys])
s_track = np.zeros((H1, W1), np.float32)
tracks = gpd.read_file(PROCESSED / "shisr_tracks.geojson").to_crs(UTM)
if len(tracks):
    # drop bearings whose detected part mostly follows mapped modern roads/tracks
    keep_b = tracks.loc[(tracks["part"] == "detected") & (tracks["mapped_modern_fraction"] < 0.5), "bearing_deg"]
    tk = tracks[tracks["bearing_deg"].isin(keep_b)]
    if len(tk):
        d = (sdist(cell_pts, tk.geometry.union_all()) / 1000).reshape(H1, W1)
        s_track = np.exp(-d / 2.0).astype("float32")
    info["shisr_tracks_used"] = sorted(map(float, keep_b))
align_path = PROCESSED / "site_alignments.geojson"
if align_path.exists():
    al = gpd.read_file(align_path).to_crs(UTM)
    d = (sdist(cell_pts, al.geometry.union_all()) / 1000).reshape(H1, W1)
    s_track = np.maximum(s_track, np.exp(-d / 2.0))
    info["trilith_alignments"] = len(al)
comp["tracks_alignments"] = scale01(s_track)

# ------------------------------------------------------------------ clue 4: geometric anomalies
with rasterio.open(INTERIM / "anomalies_1km.tif") as src:
    an = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
s_geo = (0.5 * scale01(an["corners_per_km2"]) + 0.2 * scale01(an["circles_per_km2"]) +
         0.3 * scale01(an["line_km_per_km2"]))
comp["geometric_anomalies"] = scale01(s_geo)

# ------------------------------------------------------------------ clue 6: thin / recent sand
dh, _ = read_raster(INTERIM / "dune_height_30m.tif")
sand30, _ = read_raster(INTERIM / "sand_mask_30m.tif")
sandf = to_1km(np.where(sand30 == 255, np.nan, sand30).astype("float32"), t30)
dh1 = to_1km(np.where(sand30 == 1, dh, np.nan), t30)
del dh
thin_cover = np.nan_to_num(sandf, nan=0) * (1 - np.clip(np.nan_to_num(dh1, nan=0) / 25, 0, 1)) + \
             (1 - np.nan_to_num(sandf, nan=0)) * 0.5
chg, _ = band(INTERIM / "sand_change_60m.tif", "change_class")
recent = to_1km(np.where(chg == 255, np.nan, np.isin(chg, [2, 3]).astype("float32")), t60)
vv, _ = band(INTERIM / "s1_g90.tif", "vv_win")
sand90 = np.full((H90, W90), np.nan, np.float32)
reproject(np.where(sand30 == 255, np.nan, sand30).astype("float32"), sand90, src_transform=t30, src_crs=UTM,
          src_nodata=np.nan, dst_transform=t90, dst_crs=UTM, dst_nodata=np.nan, resampling=Resampling.average)
in_sand = sand90 > 0.7
vz = (vv - np.nanmedian(vv[in_sand])) / (np.nanstd(vv[in_sand]) + 1e-9)
radar_thin = to_1km(np.where(in_sand, (vz > 1).astype("float32"), np.nan), t90)
comp["thin_sand"] = scale01(0.5 * thin_cover + 0.25 * np.nan_to_num(recent, nan=0)
                            + 0.25 * np.nan_to_num(radar_thin, nan=0))
del sand30

# ------------------------------------------------------------------ masks
dmod, _ = band(INTERIM / "modern_30m.tif", "dist_modern_m")
farm, _ = band(INTERIM / "modern_30m.tif", "farm_mask")
buf = cfg["masks"]["modern_infrastructure_buffer_m"]
modern_frac = to_1km((dmod < buf).astype("float32"), t30)
farm_frac = to_1km(farm, t30)
dist_mod_1km = to_1km(dmod, t30, Resampling.min)
del dmod, farm
mask = (1 - np.nan_to_num(modern_frac, nan=0))
mask[np.nan_to_num(farm_frac, nan=0) > 0.1] *= cfg["masks"]["centre_pivot_and_fields"]
seismic = an["long_straight_km_per_km2"] > 0.5
mask[seismic] *= cfg["masks"]["seismic_grid_multiplier"]

# ------------------------------------------------------------------ optional: ML similarity to known sites
sites_csv = REFERENCE / "published_sites.csv"
if sites_csv.exists():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold, cross_val_score
    st = pd.read_csv(sites_csv)
    st = st[st["is_archaeological"].astype(bool)]
    sx, sy = Transformer.from_crs(4326, UTM, always_xy=True).transform(st["lon"].values, st["lat"].values)
    r_, c_ = rasterio.transform.rowcol(t1, sx, sy)
    r_, c_ = np.asarray(r_), np.asarray(c_)
    ok = (r_ >= 0) & (r_ < H1) & (c_ >= 0) & (c_ < W1)
    ok[ok] &= inside[r_[ok], c_[ok]]
    if ok.sum() >= 10:
        feats = np.stack([np.nan_to_num(v) for v in comp.values()] +
                         [scale01(np.nan_to_num(an[k])) for k in ("line_km_per_km2", "corners_per_km2")], -1)
        pos = np.zeros((H1, W1), bool); pos[r_[ok], c_[ok]] = True
        rng = np.random.default_rng(0)
        neg_idx = np.argwhere(inside & ~pos)
        neg_idx = neg_idx[rng.choice(len(neg_idx), min(len(neg_idx), 20 * ok.sum()), replace=False)]
        Xp, Xn = feats[pos], feats[neg_idx[:, 0], neg_idx[:, 1]]
        X = np.vstack([Xp, Xn]); y = np.r_[np.ones(len(Xp)), np.zeros(len(Xn))]
        blocks = np.r_[(np.argwhere(pos)[:, 0] // 25) * 100 + np.argwhere(pos)[:, 1] // 25,
                       (neg_idx[:, 0] // 25) * 100 + neg_idx[:, 1] // 25]
        rf = RandomForestClassifier(300, min_samples_leaf=3, class_weight="balanced", random_state=0)
        auc = cross_val_score(rf, X, y, groups=blocks, cv=GroupKFold(5), scoring="roc_auc")
        rf.fit(X, y)
        ml = rf.predict_proba(feats.reshape(-1, feats.shape[-1]))[:, 1].reshape(H1, W1)
        comp["geometric_anomalies"] = scale01(0.5 * comp["geometric_anomalies"] + 0.5 * ml)
        info["ml"] = {"positives": int(ok.sum()), "spatial_cv_auc_mean": round(float(auc.mean()), 3),
                      "spatial_cv_auc_sd": round(float(auc.std()), 3)}
    else:
        info["ml"] = f"only {int(ok.sum())} published archaeological sites inside the corridor: no classifier trained"
else:
    info["ml"] = "no published site table yet (step 14 not run): no classifier trained"

# ------------------------------------------------------------------ weighted score
w = cfg["weights"]
wsum = sum(w.values())
score = sum((w[k] / wsum) * np.nan_to_num(comp[k], nan=0) for k in w) * mask
score[~inside] = np.nan
names = list(w)
write_raster(PROCESSED / "score_1km.tif", np.stack([score] + [np.where(inside, comp[k], np.nan) for k in names]
                                                   + [np.where(inside, mask, np.nan)]).astype("float32"),
             t1, descriptions=["score"] + names + ["mask_multiplier"])
np.savez_compressed(PROCESSED / "score_components_1km.npz",
                    **{k: np.where(inside, comp[k], np.nan).astype("float32") for k in names},
                    mask=np.where(inside, mask, np.nan).astype("float32"),
                    modern_frac=np.nan_to_num(modern_frac, nan=0).astype("float32"),
                    farm_frac=np.nan_to_num(farm_frac, nan=0).astype("float32"),
                    dist_modern_m=dist_mod_1km.astype("float32"),
                    seismic=seismic, inside=inside, transform=np.array(list(t1)[:6]))

# ------------------------------------------------------------------ top-N with minimum spacing
N, sp = cfg["candidates"]["top_n"], cfg["candidates"]["min_spacing_km"]
order = np.argsort(np.nan_to_num(score, nan=-1).ravel())[::-1]
chosen = []
for idx in order:
    r, c = divmod(int(idx), W1)
    if not np.isfinite(score[r, c]) or score[r, c] <= 0:
        break
    if all(np.hypot(r - r2, c - c2) >= sp for r2, c2 in chosen):
        chosen.append((r, c))
    if len(chosen) == N:
        break

to_ll = Transformer.from_crs(UTM, 4326, always_xy=True)
ref = pd.read_csv(REFERENCE / "reference_points.csv").dropna(subset=["lat"])
# country of each candidate (Natural Earth 1:10m polygons, about +/-1 km near borders)
ne_countries = RAW / "ne_10m_admin_0_countries.geojson"
download("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
         "ne_10m_admin_0_countries.geojson", ne_countries)
countries = gpd.read_file(ne_countries)[["ADMIN", "geometry"]]
infra = gpd.read_file(PROCESSED / "modern_infrastructure.geojson").to_crs(UTM)
pipes = infra[infra["class"].isin(["pipeline", "power_line", "minor_line", "storage_tank"])]
lsl = gpd.read_file(PROCESSED / "long_straight_lines.geojson").to_crs(UTM)
terms = gpd.read_file(PROCESSED / "wadi_termini.geojson").to_crs(UTM)
dep_b1 = to_1km(np.clip(dep_b, 0, None), t90, Resampling.max)
pale1, _ = band(INTERIM / "s2_indices_30m.tif", "pale_crust")
pale1 = to_1km(pale1, t30, Resampling.max)
labels = {"wadi_terminus": "3 wadi end under dunes", "spring_minerals": "1 spring-type minerals",
          "groundwater_lows": "5 groundwater-path low", "tracks_alignments": "2/4 track or alignment",
          "geometric_anomalies": "4 geometric anomaly", "thin_sand": "6 thin/recent sand"}

rows = []
for rank, (r, c) in enumerate(chosen, start=1):
    x, y = rasterio.transform.xy(t1, r, c)
    lon, lat = to_ll.transform(x, y)
    p = points([[x, y]])[0]
    cs = {k: float(np.nan_to_num(comp[k][r, c])) for k in names}
    sat = [labels[k] for k in names if cs[k] >= 0.5]
    nat = []
    if cs["groundwater_lows"] >= 0.5 or dep_b1[r, c] > 2:
        nat.append("natural interdune/sabkha depression; evaporites or modern seepage can mimic spring deposits")
    if pale1[r, c] > 2:
        nat.append("pale crust may be gypsum/salt sabkha, calcrete or Pleistocene-Holocene lake marl, not a spring")
    if cs["wadi_terminus"] >= 0.5:
        nat.append("wadi terminal splay / alluvial fan deposits produce natural texture and pale sediment")
    if cs["geometric_anomalies"] >= 0.5:
        nat.append("orthogonal joint sets in limestone, dune slip-face edges, deflation scars or vehicle tracks")
    if cs["tracks_alignments"] >= 0.5:
        nat.append("tracks radiating from Shisr may be recent and unmapped vehicle routes")
    if len(lsl) and lsl.distance(p).min() < 3000:
        nat.append("oil-exploration seismic lines within 3 km")
    if len(pipes) and pipes.distance(p).min() < 5000:
        nat.append("mapped pipeline / power line / tank within 5 km")
    if dist_mod_1km[r, c] < 2000:
        nat.append(f"modern feature within {dist_mod_1km[r, c] / 1000:.1f} km")
    dref = {row["name"].split(" (")[0].split(" - ")[0]: np.hypot(*(np.array(Transformer.from_crs(
        4326, UTM, always_xy=True).transform(row["lon"], row["lat"])) - [x, y])) / 1000 for _, row in ref.iterrows()}
    near = min(dref, key=dref.get)
    hit = countries[countries.contains(points([[lon, lat]])[0])]
    country = hit["ADMIN"].iloc[0] if len(hit) else "unknown"
    rows.append({"rank": rank, "candidate_id": f"C{rank:02d}", "lat": round(lat, 5), "lon": round(lon, 5),
                 "country_approx": country,
                 "score": round(float(score[r, c]), 3), **{k: round(v, 2) for k, v in cs.items()},
                 "mask_multiplier": round(float(mask[r, c]), 2), "clues_satisfied": "; ".join(sat),
                 "n_clues": len(sat), "natural_or_modern_explanations": "; ".join(nat) or "none flagged automatically",
                 "nearest_reference": f"{near} ({dref[near]:.0f} km)",
                 "nearest_wadi_terminus_km": round(float(terms.distance(p).min() / 1000), 1) if len(terms) else None})
cand = pd.DataFrame(rows)
cand.to_csv(CANDIDATES / "top20_candidates.csv", index=False)
gpd.GeoDataFrame(cand, geometry=gpd.points_from_xy(cand.lon, cand.lat), crs=4326).to_file(
    PROCESSED / "candidates.geojson")
info.update({"weights": w, "masks": cfg["masks"], "n_candidates": len(cand),
             "corridor_cells_1km": int(inside.sum())})
write_json(OUTPUTS / "score_info.json", info)
print(json.dumps(info, indent=1, default=str))
print(cand[["candidate_id", "lat", "lon", "score", "n_clues", "clues_satisfied"]].to_string(index=False))
