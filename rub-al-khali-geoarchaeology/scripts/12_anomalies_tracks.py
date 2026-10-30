"""Step 12 - linear, rectilinear and circular anomalies; tracks radiating from Shisr (clues 2, 4).

Input: Sentinel-2 B04 (red) at 20 m, corridor only (step 6); modern features (step 11).

Per 2048 x 2048 px tile (~41 km), in parallel:
  * ridge filter (Sato, sigma 1-2 px) for thin bright AND dark lines -> threshold at the
    tile's 97th percentile -> skeleton -> probabilistic Hough line segments (>= 240 m)
  * Canny edges -> Hough circles, radius 60-300 m
Then over the whole corridor:
  * collinear segments are merged in (azimuth, offset) Hough space; lines that stay straight
    for >= 4 km are flagged "long-straight" = likely seismic lines, pipelines or roads
    (ancient caravan tracks braid and curve)
  * Shisr-radial segments (azimuth within 6 deg of the bearing to Shisr, 2-60 km out) are
    binned by bearing; peaks are fitted as track lines and extended 40 km further into the
    sand; each is flagged if it coincides with a mapped modern road/track (within 150 m)
  * corners: segment pairs at 90 +/- 10 deg whose endpoints meet within 40 m
  * fit_alignments(): RANSAC lines through >= 3 known sites (e.g. triliths), extended into the
    sand - runs when published site coordinates are available (step 14)
Outputs: data/interim/anomalies_1km.tif, data/processed/{shisr_tracks,long_straight_lines,
         circles}.geojson, data/interim/segments.npy
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

from common import INTERIM, OUTPUTS, PROCESSED, REFERENCE, UTM, grid, load_yaml, read_raster, write_json, write_raster

TILE, HALO = 2048, 64
B04 = INTERIM / "s2_b04_20m.tif"


def process_tile(args):
    """Line segments and circles for one tile. Returns UTM coordinates."""
    from skimage.feature import canny
    from skimage.filters import sato
    from skimage.morphology import remove_small_objects, skeletonize
    from skimage.transform import hough_circle, hough_circle_peaks, probabilistic_hough_line

    r0, c0 = args
    with rasterio.open(B04) as src:
        win = Window(c0 - HALO, r0 - HALO, TILE + 2 * HALO, TILE + 2 * HALO).intersection(
            Window(0, 0, src.width, src.height))
        img = src.read(1, window=win).astype("float32")
        tr = src.window_transform(win)
    valid = img > 0
    if valid.mean() < 0.05:
        return np.empty((0, 6)), np.empty((0, 4))
    img = np.where(valid, img / 1e4, np.nanmedian(img[valid]) / 1e4)
    # farms / pivots (step 11) and dark compact blobs would otherwise dominate the response
    with rasterio.open(INTERIM / "modern_30m.tif") as msrc:
        b = rasterio.transform.array_bounds(img.shape[0], img.shape[1], tr)
        farm = msrc.read(2, window=rasterio.windows.from_bounds(*b, transform=msrc.transform),
                         out_shape=img.shape, boundless=True, fill_value=0) > 0
    dark = img < np.percentile(img[valid], 2)
    blobs = ndimage.binary_opening(dark, iterations=2)                # compact dark objects only
    exclude = ndimage.binary_dilation(farm | blobs, iterations=4)
    hp = img - ndimage.gaussian_filter(img, 10)                       # remove > ~200 m trends
    ridge = np.maximum(sato(hp, sigmas=[0.8, 1.5], black_ridges=False),
                       sato(hp, sigmas=[0.8, 1.5], black_ridges=True))
    ridge[exclude] = 0
    # local significance: z-score of the ridge response within ~1 km, so faint tracks on a
    # uniform plain count as much as tracks beside high-contrast farms
    mu = ndimage.uniform_filter(ridge, 51)
    sd = np.sqrt(np.maximum(ndimage.uniform_filter(ridge * ridge, 51) - mu * mu, 1e-12))
    z = (ridge - mu) / sd
    core = ndimage.binary_erosion(valid, iterations=4) & ~exclude
    lines = remove_small_objects((z > 2.0) & core, min_size=10)
    skel = skeletonize(lines)
    segs = probabilistic_hough_line(skel, threshold=10, line_length=12, line_gap=4, rng=0)
    # tile core in local pixel coordinates: features in the halo belong to the neighbour tile
    lc0, lr0 = c0 - win.col_off, r0 - win.row_off
    in_core = lambda x, y: lc0 <= x < lc0 + TILE and lr0 <= y < lr0 + TILE
    seg_out = []
    for (x0, y0), (x1, y1) in segs:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if not in_core(mx, my):
            continue
        X0, Y0 = tr * (x0 + 0.5, y0 + 0.5)
        X1, Y1 = tr * (x1 + 0.5, y1 + 0.5)
        resp = float(ridge[int(my), int(mx)])
        bright = float(hp[int(my), int(mx)] > 0)
        seg_out.append((X0, Y0, X1, Y1, resp, bright))
    # circles (60-300 m radius) on Canny edges of the smoothed image
    edges = canny(ndimage.gaussian_filter(img, 1.5), sigma=1.5) & valid
    radii = np.arange(3, 16)
    hspace = hough_circle(edges, radii)
    acc, cx, cy, rad = hough_circle_peaks(hspace, radii, min_xdistance=6, min_ydistance=6,
                                          threshold=0.55, total_num_peaks=400)
    circ = [(*(tr * (x + 0.5, y + 0.5)), r * 20.0, a) for a, x, y, r in zip(acc, cx, cy, rad)
            if in_core(x, y)]
    return np.array(seg_out).reshape(-1, 6), np.array(circ).reshape(-1, 4)


def bearing(x0, y0, x1, y1):
    return (np.degrees(np.arctan2(x1 - x0, y1 - y0)) + 360) % 360


def fit_alignments(points_xy: np.ndarray, tol_m=500.0, min_pts=3, extend_m=40000.0):
    """RANSAC straight lines through >= min_pts site points; returns list of LineStrings
    spanning the inliers and extended by extend_m beyond both ends."""
    from skimage.measure import LineModelND, ransac

    lines, pts = [], points_xy.copy()
    while len(pts) >= min_pts:
        model, inl = ransac(pts, LineModelND, min_samples=2, residual_threshold=tol_m, max_trials=2000)
        if model is None or inl.sum() < min_pts:
            break
        o, d = model.params
        t = (pts[inl] - o) @ d
        a, b = o + d * (t.min() - extend_m), o + d * (t.max() + extend_m)
        lines.append({"n_sites": int(inl.sum()), "geometry": LineString([a, b])})
        pts = pts[~inl]
    return lines


if __name__ == "__main__":
    cfg = load_yaml("aoi.yaml")
    with rasterio.open(B04) as src:
        H20, W20, t20 = src.height, src.width, src.transform
    m30, t30 = read_raster(INTERIM / "corridor_mask_g30.tif")
    starts = []
    for r0 in range(0, H20, TILE):
        for c0 in range(0, W20, TILE):
            # corridor coverage of this tile from the 30 m mask
            rr = slice(int(r0 / 1.5), int(min(H20, r0 + TILE) / 1.5))
            cc = slice(int(c0 / 1.5), int(min(W20, c0 + TILE) / 1.5))
            if m30[rr, cc].mean() > 0.01:
                starts.append((r0, c0))
    print(f"{len(starts)} tiles to process", flush=True)
    seg_list, circ_list = [], []
    with ProcessPoolExecutor(4) as ex:
        for i, (s, c) in enumerate(ex.map(process_tile, starts)):
            seg_list.append(s); circ_list.append(c)
            if i % 10 == 0:
                print(f"  tile {i + 1}/{len(starts)}: {sum(len(x) for x in seg_list):,} segments", flush=True)
    segs = np.vstack(seg_list)
    circles = np.vstack(circ_list)
    np.save(INTERIM / "segments.npy", segs)

    # ------------------------------------------------------------------ segment attributes
    x0, y0, x1, y1 = segs[:, 0], segs[:, 1], segs[:, 2], segs[:, 3]
    length = np.hypot(x1 - x0, y1 - y0)
    az = bearing(x0, y0, x1, y1) % 180                       # undirected azimuth 0-180
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2

    # modern-feature distance and corridor at the segment midpoints
    with rasterio.open(INTERIM / "modern_30m.tif") as src:
        dmod = src.read(1)
        r_, c_ = rasterio.transform.rowcol(src.transform, mx, my)
    r_ = np.clip(r_, 0, dmod.shape[0] - 1); c_ = np.clip(c_, 0, dmod.shape[1] - 1)
    near_modern = dmod[r_, c_] < 150
    in_corr = m30[np.clip(r_, 0, m30.shape[0] - 1), np.clip(c_, 0, m30.shape[1] - 1)] == 1

    # ------------------------------------------------------------------ long straight lines (seismic etc.)
    th = np.radians(az)
    rho = mx * np.cos(th) - my * np.sin(th)                 # offset perpendicular to the azimuth
    key_t = np.round(az / 1.0).astype(int) % 180
    key_r = np.round(rho / 60).astype(int)
    df = pd.DataFrame({"kt": key_t, "kr": key_r, "len": length,
                       "along": mx * np.sin(th) + my * np.cos(th)})
    g = df.groupby(["kt", "kr"]).agg(total=("len", "sum"), lo=("along", "min"), hi=("along", "max"),
                                     n=("len", "size"))
    straight_bins = g[(g["total"] > 2000) & ((g["hi"] - g["lo"]) > 4000) & (g["n"] >= 4)].index
    sb = set(map(tuple, straight_bins))
    long_straight = np.array([(a, b) in sb for a, b in zip(key_t, key_r)])
    ls_rows = []
    for (kt, kr), row in g.loc[straight_bins].iterrows():
        t_ = math.radians(kt)
        d = np.array([math.sin(t_), math.cos(t_)]); nrm = np.array([math.cos(t_), -math.sin(t_)])
        p0 = nrm * kr * 60 + d * row["lo"]; p1 = nrm * kr * 60 + d * row["hi"]
        ls_rows.append({"azimuth_deg": int(kt), "extent_km": round((row["hi"] - row["lo"]) / 1000, 1),
                        "detected_km": round(row["total"] / 1000, 1), "geometry": LineString([p0, p1])})
    ls_gdf = gpd.GeoDataFrame(ls_rows, crs=UTM)

    # ------------------------------------------------------------------ Shisr-radial tracks
    shisr = cfg["anchors"]["shisr"]
    from pyproj import Transformer
    sx, sy = Transformer.from_crs(4326, UTM, always_xy=True).transform(shisr["lon"], shisr["lat"])
    beta = bearing(sx, sy, mx, my)                          # bearing Shisr -> segment midpoint
    dist = np.hypot(mx - sx, my - sy)
    dang = np.abs(((az - beta % 180) + 90) % 180 - 90)
    radial = (dang < 6) & (dist > 2000) & (dist < 60000) & ~long_straight & in_corr
    hist, edges = np.histogram(beta[radial], bins=180, range=(0, 360), weights=length[radial])
    hs = ndimage.gaussian_filter1d(hist, 1.5, mode="wrap")
    thr_peak = hs.mean() + 2 * hs.std()
    peaks = [i for i in range(180) if hs[i] == hs[max(0, i - 3):i + 4].max() and hs[i] > thr_peak]
    roads = gpd.read_file(PROCESSED / "modern_roads_tracks.geojson").to_crs(UTM)
    road_union = roads.geometry.buffer(150).union_all() if len(roads) else None
    tracks = []
    for i in peaks:
        b0 = edges[i] + 1.0
        sel = radial & (np.abs(((beta - b0) + 180) % 360 - 180) < 3)
        if length[sel].sum() < 1500:
            continue
        far = dist[sel].max()
        ang = np.radians(np.average(beta[sel], weights=length[sel]))
        u = np.array([np.sin(ang), np.cos(ang)])
        detected = LineString([(sx + u[0] * 2000, sy + u[1] * 2000), (sx + u[0] * far, sy + u[1] * far)])
        ext = LineString([(sx + u[0] * far, sy + u[1] * far), (sx + u[0] * (far + 40000), sy + u[1] * (far + 40000))])
        mapped = (detected.intersection(road_union).length / detected.length) if road_union is not None else 0.0
        tracks.append({"bearing_deg": round(float(np.degrees(ang)) % 360, 1), "segments": int(sel.sum()),
                       "segment_km": round(float(length[sel].sum()) / 1000, 1),
                       "detected_to_km": round(far / 1000, 1),
                       "mapped_modern_fraction": round(float(mapped), 2),
                       "part": "detected", "geometry": detected})
        tracks.append({**tracks[-1], "part": "extension_40km", "geometry": ext})
    tr_gdf = gpd.GeoDataFrame(tracks, crs=UTM)
    print(f"Shisr-radial bearings: {[t['bearing_deg'] for t in tracks if t['part'] == 'detected']}", flush=True)

    # ------------------------------------------------------------------ corners (rectilinear)
    shortish = (length >= 100) & (length <= 600) & ~long_straight & in_corr
    idx = np.where(shortish)[0]
    ends = np.vstack([np.c_[x0[idx], y0[idx]], np.c_[x1[idx], y1[idx]]])
    owner = np.r_[idx, idx]
    tree = cKDTree(ends)
    pairs = tree.query_pairs(40, output_type="ndarray")
    a, b = owner[pairs[:, 0]], owner[pairs[:, 1]]
    diff = np.abs(((az[a] - az[b]) + 90) % 180 - 90)
    ok = (a != b) & (np.abs(diff - 90) <= 10)
    corners = ends[pairs[ok, 0]]

    # ------------------------------------------------------------------ 1 km aggregates
    t1, W1, H1 = grid("g1km")

    def per_km(xy, w=None):
        r, c = rasterio.transform.rowcol(t1, xy[:, 0], xy[:, 1])
        r, c = np.asarray(r), np.asarray(c)
        ok_ = (r >= 0) & (r < H1) & (c >= 0) & (c < W1)
        out = np.zeros((H1, W1), np.float32)
        np.add.at(out, (r[ok_], c[ok_]), 1.0 if w is None else w[ok_])
        return out

    keep = ~long_straight & ~near_modern & in_corr
    line_km = per_km(np.c_[mx[keep], my[keep]], length[keep] / 1000)
    corner_n = per_km(corners) if len(corners) else np.zeros((H1, W1), np.float32)
    seismic_km = per_km(np.c_[mx[long_straight], my[long_straight]], length[long_straight] / 1000)
    with rasterio.open(INTERIM / "modern_30m.tif") as src:
        cr, cc_ = rasterio.transform.rowcol(src.transform, circles[:, 0], circles[:, 1])
        cr = np.clip(cr, 0, src.height - 1); cc_ = np.clip(cc_, 0, src.width - 1)
        circ_modern = (dmod[cr, cc_] < 300)
    circle_n = per_km(circles[~circ_modern, :2]) if len(circles) else np.zeros((H1, W1), np.float32)

    # distance (km) from each 1 km cell centre to the nearest Shisr track line (detected or extension)
    rows_, cols_ = np.indices((H1, W1))
    cxs, cys = rasterio.transform.xy(t1, rows_.ravel(), cols_.ravel())
    if len(tr_gdf):
        from shapely import distance as sdist, points
        pts_ = points(np.c_[cxs, cys])
        union = tr_gdf.geometry.union_all()
        d_track = (sdist(pts_, union) / 1000).reshape(H1, W1).astype("float32")
    else:
        d_track = np.full((H1, W1), np.inf, np.float32)

    write_raster(INTERIM / "anomalies_1km.tif",
                 np.stack([line_km, corner_n, circle_n, seismic_km, d_track]), t1,
                 descriptions=["line_km_per_km2", "corners_per_km2", "circles_per_km2",
                               "long_straight_km_per_km2", "dist_shisr_track_km"])
    tr_gdf.to_crs(4326).to_file(PROCESSED / "shisr_tracks.geojson")
    ls_gdf.to_crs(4326).to_file(PROCESSED / "long_straight_lines.geojson")
    circ_gdf = gpd.GeoDataFrame({"radius_m": circles[:, 2], "score": circles[:, 3], "near_modern": circ_modern},
                                geometry=[Point(x, y) for x, y in circles[:, :2]], crs=UTM)
    circ_gdf.to_crs(4326).to_file(PROCESSED / "circles.geojson")
    stats = {"segments": int(len(segs)), "long_straight_segments": int(long_straight.sum()),
             "long_straight_lines": int(len(ls_gdf)), "radial_segments": int(radial.sum()),
             "shisr_track_bearings": [t["bearing_deg"] for t in tracks if t["part"] == "detected"],
             "corners": int(len(corners)), "circles": int(len(circles)),
             "circles_near_modern": int(circ_modern.sum())}
    write_json(OUTPUTS / "anomaly_stats.json", stats)
    print(stats)
