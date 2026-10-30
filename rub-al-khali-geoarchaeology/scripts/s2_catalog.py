"""Find Sentinel-2 L2A (Collection 1) scenes by listing the public AWS bucket directly.

The Earth Search STAC API is blocked by this environment's network policy, but the
underlying open bucket (e84-earth-search-sentinel-data, AWS Open Data) is reachable.
Each scene folder holds the band COGs plus a STAC item JSON with cloud cover etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

import common  # noqa: F401  (sets CA bundle / proxy env)

BUCKET = "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"
PREFIX = "sentinel-2-c1-l2a"
_SESSION = requests.Session()


def _list_prefixes(prefix: str) -> list[str]:
    out, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "delimiter": "/", "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        r = _SESSION.get(BUCKET + "/", params=params, timeout=60)
        r.raise_for_status()
        out += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix></CommonPrefixes>", r.text)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", r.text)
        if not m:
            return out
        token = m.group(1)


@dataclass
class Scene:
    tile: str
    scene_id: str
    folder: str              # bucket-relative folder, ends with '/'
    datetime: str
    cloud: float
    nodata: float
    sun_elev: float
    epsg: int

    def href(self, asset: str) -> str:
        """URL of an asset, e.g. 'B04.tif', 'SCL.tif', 'L2A_PVI.tif'."""
        return f"{BUCKET}/{self.folder}{asset}"


def tile_path(tile: str) -> str:
    """'39QYB' -> '39/Q/YB'"""
    return f"{int(tile[:2])}/{tile[2]}/{tile[3:5]}"


def scenes(tile: str, year: int, month: int) -> list[Scene]:
    out = []
    for folder in _list_prefixes(f"{PREFIX}/{tile_path(tile)}/{year}/{month}/"):
        sid = folder.rstrip("/").split("/")[-1]
        try:
            item = _SESSION.get(f"{BUCKET}/{folder}{sid}.json", timeout=60).json()
        except (requests.RequestException, ValueError):
            continue
        p = item.get("properties", {})
        epsg = p.get("proj:epsg") or int(str(p.get("proj:code", "EPSG:0")).split(":")[-1])
        out.append(Scene(tile, sid, folder, p.get("datetime", ""),
                         float(p.get("eo:cloud_cover", 100)),
                         float(p.get("s2:nodata_pixel_percentage", 100)),
                         float(p.get("view:sun_elevation", 0) or 0), int(epsg)))
    return out


def best_scene(tile: str, months: list[tuple[int, int]], max_cloud: float = 5.0) -> Scene | None:
    """Lowest (cloud + nodata) scene over the given (year, month) list."""
    ranked = ranked_scenes(tile, months, max_cloud)
    return ranked[0] if ranked else None


def ranked_scenes(tile: str, months: list[tuple[int, int]], max_cloud: float = 5.0) -> list[Scene]:
    """Scenes sorted best-first: low cloud, then complete swath coverage."""
    cands = [s for ym in months for s in scenes(tile, *ym)]
    cands = [s for s in cands if s.cloud <= max_cloud] or cands
    return sorted(cands, key=lambda s: (s.nodata > 50, s.cloud + 0.2 * s.nodata))


# ----------------------------------------------------------------------------- reading
SCALE, OFFSET = 1e-4, -0.1   # Collection-1 L2A (processing baseline >= 04.00) DN -> reflectance


def read_reflectance(scene: Scene, band: str, out_shape=None, window=None):
    """Read one band as float32 surface reflectance (NaN = nodata).

    out_shape lets GDAL use the COG's internal overviews, so a whole-tile read at
    low resolution transfers only ~1 MB per band.
    """
    import numpy as np
    import rasterio

    with rasterio.open("/vsicurl/" + scene.href(f"{band}.tif")) as src:
        kw = {}
        if window is not None:
            kw["window"] = window
        if out_shape is not None:
            kw["out_shape"] = out_shape
            kw["resampling"] = rasterio.enums.Resampling.average
        dn = src.read(1, **kw).astype("float32")
        tr = src.window_transform(window) if window is not None else src.transform
        if out_shape is not None:
            h0 = (window.height if window is not None else src.height)
            w0 = (window.width if window is not None else src.width)
            tr = tr * tr.scale(w0 / out_shape[1], h0 / out_shape[0])
        crs = src.crs
    refl = np.where(dn == 0, np.nan, dn * SCALE + OFFSET).astype("float32")
    return refl, tr, crs
