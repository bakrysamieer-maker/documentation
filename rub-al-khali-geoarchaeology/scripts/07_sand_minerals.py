"""Step 7 - Sentinel-2 indices, sand mask and (proxy) mineral layers on the 30 m grid.

Indices (corridor only, NaN elsewhere) -> data/interim/s2_indices_30m.tif
  brightness  mean reflectance of B02 B03 B04 B8A B11 B12
  redness     B04 / B02         iron-oxide coatings of dune sand
  ndvi        (B8A-B04)/(B8A+B04)
  mndwi       (B03-B11)/(B03+B11)  open water / wet sabkha
  ndswir      (B11-B12)/(B11+B12)  2.2-2.35 um absorbers: clays, carbonates, sulphates
  pale_crust  z(brightness) + z(ndswir) - z(redness): NON-SPECIFIC proxy for pale
              carbonate / gypsum / evaporite crusts. ASTER (step 13) replaces it when available.

Sand mask -> data/interim/sand_mask_30m.tif (1 = sand)
  red sand:  redness above the corridor's Otsu threshold
  pale sand: dune relief (DEM minus 1 km-smoothed DEM, local std) high AND redness above
             a lower threshold
  cleaned with morphological opening/closing (removes specks < ~1 ha, fills small holes).
"""
from __future__ import annotations

import numpy as np
import rasterio
from scipy import ndimage
from skimage.filters import threshold_otsu

from common import INTERIM, OUTPUTS, UTM, grid, read_raster, write_json, write_raster

t30, W, H = grid("g30")
mask, _ = read_raster(INTERIM / "corridor_mask_g30.tif")
inside = mask == 1

def robust_z(a):
    v = a[np.isfinite(a)]
    med = np.median(v)
    iqr = np.subtract(*np.percentile(v, [75, 25]))
    return ((a - med) / (iqr / 1.349)).astype("float32")


INDICES = ["brightness", "redness", "ndvi", "mndwi", "ndswir", "pale_crust"]
prof = dict(driver="GTiff", width=W, height=H, count=len(INDICES), dtype="float32", crs=UTM,
            transform=t30, nodata=np.nan, compress="deflate", predictor=3, tiled=True,
            blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
# indices are written one at a time to keep memory low (each 30 m layer is ~0.6 GB)
with rasterio.open(INTERIM / "s2_30m.tif") as src, \
        rasterio.open(INTERIM / "s2_indices_30m.tif", "w", **prof) as dst:
    dst.descriptions = tuple(INDICES)
    names = list(src.descriptions)
    band = lambda b: src.read(names.index(b) + 1).astype("float32") / 1e4
    put = lambda name, a: dst.write(a.astype("float32"), INDICES.index(name) + 1)
    B02, B03, B04 = band("B02"), band("B03"), band("B04")
    valid = inside & (B04 > 0)
    # floor on blue avoids huge ratios from rare near-zero (dark / edge) pixels
    redness = np.where(valid, B04 / np.maximum(B02, 0.02), np.nan).astype("float32")
    brightness = B02 + B03 + B04
    del B02
    B8A, B11, B12 = band("B8A"), band("B11"), band("B12")
    brightness = np.where(valid, (brightness + B8A + B11 + B12) / 6, np.nan).astype("float32")
    put("brightness", brightness)
    put("redness", redness)
    put("ndvi", np.where(valid, (B8A - B04) / np.maximum(B8A + B04, 1e-4), np.nan))
    put("mndwi", np.where(valid, (B03 - B11) / np.maximum(B03 + B11, 1e-4), np.nan))
    ndswir = np.where(valid, (B11 - B12) / np.maximum(B11 + B12, 1e-4), np.nan).astype("float32")
    put("ndswir", ndswir)
    del B03, B04, B8A, B11, B12
    pale = robust_z(brightness) + robust_z(ndswir) - robust_z(redness)
    put("pale_crust", pale)
    del pale, ndswir, brightness

# ------------------------------------------------------------------ dune relief from the 30 m DEM
dem, _ = read_raster(INTERIM / "dem30_utm.tif")
d = np.where(np.isfinite(dem), dem, np.nanmean(dem))
resid = d - ndimage.gaussian_filter(d, sigma=1000 / 30)
k = 15                                                     # 450 m window
m1 = ndimage.uniform_filter(resid, k)
m2 = ndimage.uniform_filter(resid * resid, k)
relief = np.sqrt(np.maximum(m2 - m1 * m1, 0)).astype("float32")
relief[~valid] = np.nan
write_raster(INTERIM / "dune_relief_30m.tif", relief, t30, descriptions=["local_relief_m"])
del resid, m1, m2, d

# ------------------------------------------------------------------ sand mask
v = redness[valid]
lo, hi = np.percentile(v, [0.5, 99.5])
t_red = float(threshold_otsu(v[(v > lo) & (v < hi)]))        # Otsu on the central 99%
t_relief = float(np.nanpercentile(relief[valid], 60))
t_red_low = float(np.percentile(v, 25))
sand = valid & ((redness > t_red) | ((relief > t_relief) & (redness > t_red_low)))
sand = ndimage.binary_opening(sand, iterations=2)
sand = ndimage.binary_closing(sand, iterations=3) & valid
write_raster(INTERIM / "sand_mask_30m.tif", np.where(valid, sand, 255).astype("uint8"), t30,
             nodata=255, descriptions=["sand=1 (255 = outside corridor / no data)"])
stats = {"otsu_redness": round(t_red, 3), "redness_low_threshold": round(t_red_low, 3),
         "relief_threshold_m": round(t_relief, 2),
         "sand_fraction_of_corridor": round(float(sand[valid].mean()), 3)}
write_json(OUTPUTS / "sand_mask_stats.json", stats)
print(stats)
