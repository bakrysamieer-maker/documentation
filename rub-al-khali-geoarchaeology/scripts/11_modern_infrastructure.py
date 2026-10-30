"""Step 11 - modern look-alikes to suppress: mapped infrastructure + image-detected farms.

Mapped (OpenStreetMap and other open sources via Overture Maps, release 2026-10-21.0,
bbox-filtered GeoParquet reads from the AWS Open Data bucket):
  transportation/segment (roads, tracks), buildings/building, base/infrastructure
  (power lines, pipelines, tanks, airstrips, walls), base/land_use (farmland, industrial...)
Image-detected (Sentinel-2, step 7): irrigated fields / centre pivots = compact clusters
  with NDVI > 0.25 and area >= 2 ha. Sparse natural vegetation (e.g. the ghaf woodland at
  Muqshin) mostly stays below this threshold and is NOT masked, because natural shallow
  groundwater is part of the hypothesis being tested.

Outputs: data/processed/modern_*.geojson, data/interim/modern_30m.tif
         (band 1 distance to nearest modern feature in m; band 2 farm mask)
"""
from __future__ import annotations

import json
import os

import geopandas as gpd
import numpy as np
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import rasterio
from rasterio.features import rasterize
from scipy import ndimage
from shapely import from_wkb

from common import INTERIM, OUTPUTS, PROCESSED, UTM, grid, read_raster, write_json, write_raster

RELEASE = "overturemaps-us-west-2/release/2026-10-21.0"
summary = json.loads((OUTPUTS / "aoi_summary.json").read_text())
W_, S_, E_, N_ = summary["download_bbox_wsen"]
_p = os.environ["HTTPS_PROXY"].replace("http://", "").split(":")
fs = pafs.S3FileSystem(anonymous=True, region="us-west-2",
                       proxy_options={"scheme": "http", "host": _p[0], "port": int(_p[1])})
bbox_filter = ((pc.field("bbox", "xmin") < E_) & (pc.field("bbox", "xmax") > W_) &
               (pc.field("bbox", "ymin") < N_) & (pc.field("bbox", "ymax") > S_))


def overture(theme_type, columns):
    d = ds.dataset(f"{RELEASE}/{theme_type}/", filesystem=fs, format="parquet")
    cols = [c for c in columns if c in d.schema.names]
    tb = d.to_table(filter=bbox_filter, columns=cols + ["geometry"]).to_pydict()
    geoms = from_wkb(tb.pop("geometry"))
    for k in list(tb):
        if k == "names":
            tb[k] = [(n or {}).get("primary") for n in tb[k]]
    return gpd.GeoDataFrame(tb, geometry=geoms, crs=4326)


layers = {
    "roads_tracks": overture("theme=transportation/type=segment", ["id", "subtype", "class", "names"]),
    "buildings": overture("theme=buildings/type=building", ["id", "subtype", "class"]),
    "infrastructure": overture("theme=base/type=infrastructure", ["id", "subtype", "class", "names"]),
    "land_use": overture("theme=base/type=land_use", ["id", "subtype", "class", "names"]),
}
counts = {}
for k, g in layers.items():
    g.to_file(PROCESSED / f"modern_{k}.geojson")
    counts[k] = {"features": len(g)}
    if "class" in g:
        counts[k]["top_classes"] = g["class"].value_counts().head(8).to_dict()
    print(k, counts[k], flush=True)

# ------------------------------------------------------------------ rasterise on the 30 m grid
t30, W, H = grid("g30")
modern = np.zeros((H, W), bool)
for k, g in layers.items():
    if k == "land_use":   # only clearly modern land uses
        g = g[g["subtype"].isin(["agriculture", "developed", "industrial", "military", "transportation"])
              | g["class"].isin(["farmland", "industrial", "military", "quarry", "landfill", "construction"])]
    if len(g):
        geoms = [geom for geom in g.to_crs(UTM).geometry if geom is not None and not geom.is_empty]
        modern |= rasterize([(geom, 1) for geom in geoms], out_shape=(H, W), transform=t30,
                            fill=0, dtype="uint8", all_touched=True).astype(bool)

# image-detected irrigated fields / pivots
with rasterio.open(INTERIM / "s2_indices_30m.tif") as src:
    ndvi = src.read(list(src.descriptions).index("ndvi") + 1)
veg = np.nan_to_num(ndvi, nan=0) > 0.25
lab, n = ndimage.label(veg)
sizes = ndimage.sum(np.ones_like(lab, dtype="uint8"), lab, index=np.arange(1, n + 1))
farm = np.isin(lab, np.arange(1, n + 1)[sizes >= 22])        # >= 2 ha (22 cells of 900 m2)
farm = ndimage.binary_closing(farm, iterations=2)
modern |= farm
dist = (ndimage.distance_transform_edt(~modern) * 30).astype("float32")
write_raster(INTERIM / "modern_30m.tif", np.stack([dist, farm.astype("float32")]), t30,
             descriptions=["dist_modern_m", "farm_mask"])
counts["farm_cells_30m"] = int(farm.sum())
counts["farm_area_km2"] = round(farm.sum() * 900 / 1e6, 1)
write_json(OUTPUTS / "modern_infrastructure_stats.json", counts)
print("farm area km2:", counts["farm_area_km2"])
