"""Step 13 - ASTER mineral and thermal indices via Google Earth Engine (clue 1).

STATUS: written but NOT YET RUN. It needs a Google Earth Engine service-account key in the
environment variable EE_SERVICE_ACCOUNT_JSON (the JSON text of the key), added in the cloud
environment settings; a new session picks it up. Until then, the scoring step uses the
weaker Sentinel-2 'pale_crust' proxy for this clue.

Indices (all on the 90 m UTM 40N grid of the project, written to data/interim/aster_g90.tif):
  SWIR, day scenes acquired before April 2008 (SWIR detector failure), ASTER/AST_L1T_003,
  radiance = (DN - 1) x unit-conversion coefficient; median of cloud-free scenes:
    cli  calcite index   (B6/B8) x (B9/B8)      carbonate 2.33 um absorption (Ninomiya 2003)
    ohi  OH index        (B7/B6) x (B4/B6)      (Ninomiya 2003)
    kli  kaolinite index (B4/B5) x (B8/B6)      (Ninomiya 2003)
  TIR emissivity, ASTER Global Emissivity Database AG100 v003 (Hulley et al. 2015):
    qi   quartz index    e11^2 / (e10 x e12)    (Ninomiya 2002)
    ci   carbonate index e13 / e14              (Ninomiya 2002)
    si   sulphate index  e10 x e12 / e11^2      = 1/QI; gypsum emissivity low near 8.6-8.7 um
  Night thermal, ASTER/AST_L1T_003 night scenes, band 13 brightness temperature (K):
    bt13_night_anom   night BT minus its 2 km local mean (thermal-inertia / moisture contrast)
"""
from __future__ import annotations

import json
import os

import numpy as np
import rasterio
from scipy import ndimage

from common import INTERIM, PROCESSED, UTM, grid, read_raster, write_raster

key = os.environ.get("EE_SERVICE_ACCOUNT_JSON")
if not key:
    raise SystemExit("EE_SERVICE_ACCOUNT_JSON is not set: add the Earth Engine service-account key "
                     "in the environment settings and start a new session.")

import ee  # noqa: E402

info = json.loads(key)
ee.Initialize(ee.ServiceAccountCredentials(info["client_email"], key_data=key),
              project=info.get("project_id"))

corr = json.loads((PROCESSED / "aoi_corridor.geojson").read_text())
geom = ee.Geometry([f for f in corr["features"] if f["properties"]["name"] == "corridor"][0]["geometry"])

# unit-conversion coefficients (W m-2 sr-1 um-1 per DN), normal gain, ASTER user handbook v2
UCC = {"B04": 0.1087, "B05": 0.0348, "B06": 0.0313, "B07": 0.0299, "B08": 0.0209, "B09": 0.0159,
       "B13": 0.005693}
K1_13, K2_13 = 866.468, 1350.069          # Planck constants for band 13


def radiance(img, b):
    return img.select(b).subtract(1).multiply(UCC[b]).rename(b)


ast = ee.ImageCollection("ASTER/AST_L1T_003").filterBounds(geom)
swir = (ast.filterDate("2000-03-01", "2008-04-01").filter(ee.Filter.lt("CLOUDCOVER", 5))
        .filter(ee.Filter.listContains("ORIGINAL_BANDS_PRESENT", "B09")))
swir_med = swir.map(lambda i: ee.Image.cat([radiance(i, b) for b in ("B04", "B05", "B06", "B07", "B08", "B09")])
                    .updateMask(i.select("B09").gt(0))).median()
b4, b5, b6, b7, b8, b9 = [swir_med.select(b) for b in ("B04", "B05", "B06", "B07", "B08", "B09")]
cli = b6.divide(b8).multiply(b9.divide(b8)).rename("cli")
ohi = b7.divide(b6).multiply(b4.divide(b6)).rename("ohi")
kli = b4.divide(b5).multiply(b8.divide(b6)).rename("kli")

ged = ee.Image("NASA/ASTER_GED/AG100_003")
e10, e11, e12, e13, e14 = [ged.select(f"emissivity_band{b}").multiply(0.001) for b in (10, 11, 12, 13, 14)]
qi = e11.pow(2).divide(e10.multiply(e12)).rename("qi")
ci = e13.divide(e14).rename("ci")
si = e10.multiply(e12).divide(e11.pow(2)).rename("si")

# the day/night property name is not documented consistently: try the likely ones in turn
night = None
for flt in (ee.Filter.eq("FLAG_DAY_NIGHT", "Night"), ee.Filter.eq("DAY_NIGHT_FLAG", "Night"),
            ee.Filter.lt("SOLAR_ELEVATION", 0)):
    cand = ast.filter(flt).filter(ee.Filter.lt("CLOUDCOVER", 10))
    if cand.size().getInfo() > 0:
        night = cand
        break
if night is None:
    print("no night-time ASTER scenes found with the known property names; night BT left empty")
    night = ast.filter(ee.Filter.eq("CLOUDCOVER", -999))
if night.size().getInfo() > 0:
    bt13 = (night.map(lambda i: ee.Image(K2_13).divide(ee.Image(K1_13).divide(radiance(i, "B13")).add(1).log())
                      .rename("bt13").updateMask(i.select("B13").gt(0))).median())
else:
    bt13 = ee.Image.constant(0).updateMask(0).rename("bt13")

stack = ee.Image.cat([cli, ohi, kli, qi, ci, si, bt13]).toFloat()
names = ["cli", "ohi", "kli", "qi", "ci", "si", "bt13_night"]
print("ASTER scenes: SWIR", swir.size().getInfo(), "| night", night.size().getInfo())

# pull pixels on the project's 90 m grid in 512 x 512 blocks (computePixels, < 48 MB/request)
t90, W, H = grid("g90")
m90, _ = read_raster(INTERIM / "corridor_mask_g90.tif")
out = np.full((len(names), H, W), np.nan, np.float32)
B = 512
for r0 in range(0, H, B):
    for c0 in range(0, W, B):
        h, w = min(B, H - r0), min(B, W - c0)
        if m90[r0:r0 + h, c0:c0 + w].max() == 0:
            continue
        x0, y0 = t90 * (c0, r0)
        arr = ee.data.computePixels({
            "expression": stack, "fileFormat": "NUMPY_NDARRAY",
            "grid": {"dimensions": {"width": w, "height": h},
                     "affineTransform": {"scaleX": 90, "shearX": 0, "translateX": x0,
                                         "shearY": 0, "scaleY": -90, "translateY": y0},
                     "crsCode": UTM}})
        for i, n in enumerate(names):
            out[i, r0:r0 + h, c0:c0 + w] = arr[n]
        print(f"block {r0},{c0} done", flush=True)

bt = out[names.index("bt13_night")]
filled = np.where(np.isfinite(bt), bt, np.nanmean(bt))
anom = bt - ndimage.uniform_filter(filled, size=23)          # 2 km local mean
out = np.concatenate([out, anom[None]])
names.append("bt13_night_anom")
out[:, m90 == 0] = np.nan
write_raster(INTERIM / "aster_g90.tif", out, t90, descriptions=names)
print("wrote", INTERIM / "aster_g90.tif")
