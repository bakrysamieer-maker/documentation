"""Step 4 - check the published reference coordinates against 10 m Sentinel-2 imagery.

For each reference point a small window (~12 km; larger, at reduced resolution, for the
16 km Hamidan structure and the Umm as Samim sabkha) is read from the clearest winter
2024/25 scene. Where the reference is a water body or an oasis, the nearest open-water
(MNDWI) or vegetation (NDVI) cluster is located automatically and its offset from the
published coordinate is reported.

Outputs: outputs/figures/reference_chips/*.png, data/reference/reference_points_verified.csv
"""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mgrs
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from scipy import ndimage

from common import FIGURES, REFERENCE, write_json
import s2_catalog

OUT = FIGURES / "reference_chips"
OUT.mkdir(parents=True, exist_ok=True)
months = [(2025, 1), (2024, 12), (2025, 2)]
refs = pd.read_csv(REFERENCE / "reference_points.csv")

# window half-size (km), output pixel size (m), and what to look for
plan = {
    "shisr": (6, 10, None),
    "muqshin": (10, 10, "vegetation"),
    "muqshin_alt": (5, 10, "vegetation"),
    "muqshin_s2": (5, 10, "vegetation"),
    "umm_al_heesh": (8, 10, "wetland"),
    "hamidan": (16, 30, None),
    "umm_as_samim": (7, 20, None),   # point lies in a 9.8 km tile-overlap strip: keep the window small
}


def candidate_tiles(lat, lon):
    """MGRS squares around the point (both UTM zones near a zone boundary)."""
    m = mgrs.MGRS()
    out = []
    for dlat in (-0.15, 0, 0.15):
        for dlon in (-0.15, 0, 0.15):
            out.append(m.toMGRS(lat + dlat, lon + dlon, MGRSPrecision=0)[:5])
    return list(dict.fromkeys(out))


def read_chip(sc, lat, lon, half_km, res_m, bands):
    with rasterio.open("/vsicurl/" + sc.href("B04.tif")) as src:
        crs = src.crs
        tb = src.bounds
    x, y = Transformer.from_crs(4326, crs, always_xy=True).transform(lon, lat)
    b = (x - half_km * 1000, y - half_km * 1000, x + half_km * 1000, y + half_km * 1000)
    if b[0] < tb.left or b[2] > tb.right or b[1] < tb.bottom or b[3] > tb.top:
        return None
    n = int(2 * half_km * 1000 / res_m)
    out = {}
    for band in bands:
        with rasterio.open("/vsicurl/" + sc.href(f"{band}.tif")) as src:
            win = from_bounds(*b, transform=src.transform)
        arr, _, _ = s2_catalog.read_reflectance(sc, band, out_shape=(n, n), window=win)
        out[band] = arr
    if np.isnan(out["B04"]).mean() > 0.05:
        return None
    return out, b, crs, (x, y)


def find_target(chip, kind, res_m):
    """Centroid offset (km) of the nearest water / vegetation cluster to the chip centre."""
    if kind == "wetland":
        mndwi = (chip["B03"] - chip["B11"]) / (chip["B03"] + chip["B11"])
        vis = (chip["B02"] + chip["B03"] + chip["B04"]) / 3
        mask = (mndwi > 0.1) | (vis < 0.08)    # open water or very dark reed/palm fringe
    else:
        idx = (chip["B08"] - chip["B04"]) / (chip["B08"] + chip["B04"])       # NDVI
        mask = idx > 0.25
    lab, nlab = ndimage.label(ndimage.binary_opening(mask, iterations=1))
    if nlab == 0:
        return None
    n = mask.shape[0]
    cy = cx = (n - 1) / 2
    best = None
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        area = (lab[sl] == i).sum()
        if area < 4:
            continue
        yy, xx = ndimage.center_of_mass(lab == i)
        d = math.hypot(yy - cy, xx - cx) * res_m / 1000
        if best is None or d < best[0]:
            best = (d, yy, xx, area * res_m * res_m / 1e4)
    return best, mask


records = []
for _, r in refs.dropna(subset=["lat"]).iterrows():
    if r["id"] not in plan:
        continue
    half_km, res_m, kind = plan[r["id"]]
    bands = ["B04", "B03", "B02"] + (["B11"] if kind == "wetland" else []) + (["B08"] if kind == "vegetation" else [])
    got = None
    for tile in candidate_tiles(r["lat"], r["lon"]):
        try:
            ranked = s2_catalog.ranked_scenes(tile, months)
        except Exception:
            continue
        for sc in ranked[:4]:
            got = read_chip(sc, r["lat"], r["lon"], half_km, res_m, bands)
            if got:
                break
        if got:
            break
    if not got:
        print(r["id"], ": no complete Sentinel-2 window found")
        records.append({"id": r["id"], "verified": "no imagery"})
        continue
    chip, bnds, crs, (x0, y0) = got
    rgb = np.dstack([chip["B04"], chip["B03"], chip["B02"]])
    lo, hi = np.nanpercentile(rgb, [1, 99.5])
    rgb8 = np.clip((rgb - lo) / (hi - lo), 0, 1) ** 0.85

    fig, ax = plt.subplots(figsize=(7.2, 7.2), constrained_layout=True)
    ext = [-half_km, half_km, -half_km, half_km]
    ax.imshow(rgb8, extent=ext)
    ax.plot(0, 0, marker="+", ms=26, mew=2, color="yellow")
    ax.add_patch(plt.Circle((0, 0), float(r["uncertainty_km"]), fill=False, color="yellow", ls="--", lw=1))
    rec = {"id": r["id"], "scene": sc.scene_id, "verified": "visual check (see chip)"}
    if kind:
        res = find_target(chip, kind, res_m)
        if res and res[0]:
            (d, yy, xx, ha), mask = res
            n = mask.shape[0]
            ex = (xx - (n - 1) / 2) * res_m / 1000
            ny = ((n - 1) / 2 - yy) * res_m / 1000
            ax.contour(np.linspace(-half_km, half_km, n), np.linspace(half_km, -half_km, n), mask,
                       levels=[0.5], colors="cyan" if kind == "wetland" else "lime", linewidths=1)
            ax.plot(ex, ny, marker="o", ms=9, mfc="none", mec="red", mew=2)
            tlon, tlat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x0 + ex * 1000, y0 + ny * 1000)
            rec.update({"target": kind, "nearest_target_lat": round(tlat, 5), "nearest_target_lon": round(tlon, 5),
                        "offset_km": round(d, 2), "target_area_ha": round(ha, 1),
                        "verified": f"{kind} cluster found {d:.1f} km from published point"})
        else:
            rec.update({"target": kind, "verified": f"no {kind} cluster in window"})
    ax.set_xlim(-half_km, half_km); ax.set_ylim(-half_km, half_km)   # clip large uncertainty circles
    ax.set_xlabel("km east of published coordinate"); ax.set_ylabel("km north")
    ax.set_title(f"{r['name']}\npublished {r['lat']:.4f}N {r['lon']:.4f}E (yellow +, ±{r['uncertainty_km']} km)\n"
                 f"{sc.scene_id}  {res_m} m", fontsize=9)
    fig.savefig(OUT / f"{r['id']}.png", dpi=110)
    plt.close(fig)
    records.append(rec)
    print(rec)

ver = refs.merge(pd.DataFrame(records), on="id", how="left")
ver.to_csv(REFERENCE / "reference_points_verified.csv", index=False)

# one-page montage of the chips
order = ["shisr", "umm_al_heesh", "hamidan", "muqshin", "muqshin_alt", "muqshin_s2", "umm_as_samim"]
imgs = [plt.imread(OUT / f"{k}.png") for k in order if (OUT / f"{k}.png").exists()]
fig, axs = plt.subplots(2, 4, figsize=(22, 11.5), constrained_layout=True)
for ax in axs.flat:
    ax.axis("off")
for ax, im in zip(axs.flat, imgs):
    ax.imshow(im)
fig.suptitle("Reference coordinates checked on Sentinel-2 L2A (yellow + = published coordinate, dashed = stated "
             "uncertainty; cyan/green outlines = detected water/vegetation)", fontsize=13)
fig.savefig(FIGURES / "01_reference_checks.png", dpi=85)
