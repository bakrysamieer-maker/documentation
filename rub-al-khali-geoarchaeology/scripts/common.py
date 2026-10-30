"""Shared paths, network settings and small geodesy helpers for the project.

Every script imports this module first so that GDAL/rasterio reach the
cloud-optimised GeoTIFFs (COGs) through the session's HTTPS proxy and CA bundle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"            # downloaded rasters (git-ignored, re-creatable)
INTERIM = DATA / "interim"    # intermediate rasters (git-ignored)
REFERENCE = DATA / "reference"
PROCESSED = DATA / "processed"
OUTPUTS = ROOT / "outputs"
MAPS = OUTPUTS / "maps"
FIGURES = OUTPUTS / "figures"
CANDIDATES = OUTPUTS / "candidates"
REPORTS = ROOT / "reports"

for _d in (RAW, INTERIM, REFERENCE, PROCESSED, MAPS, FIGURES, CANDIDATES, REPORTS):
    _d.mkdir(parents=True, exist_ok=True)

# --- network: route GDAL's libcurl through the proxy with the proxy's CA bundle ---
_CA = "/root/.ccr/ca-bundle.crt"
if os.path.exists(_CA):
    os.environ.setdefault("CURL_CA_BUNDLE", _CA)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _CA)
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if _proxy:
    os.environ.setdefault("GDAL_HTTP_PROXY", _proxy.replace("http://", ""))
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff,.json,.xml")


def load_yaml(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def download(url: str, dest: Path, session=None) -> int:
    """Stream a URL to disk (skips files already present). Returns the file size."""
    import requests

    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    get = (session or requests).get
    with get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.rename(dest)
    return dest.stat().st_size


# ---------------------------------------------------------------- analysis grids
UTM = "EPSG:32640"   # UTM zone 40N; every analysis layer uses this CRS


def grid(name: str):
    """Return (transform, width, height) of a named grid written by 05_fetch_dem30_grids.py."""
    import rasterio

    g = json.loads((CONFIG / "grids.json").read_text())[name]
    return rasterio.transform.Affine(*g["transform"]), g["width"], g["height"]


def write_raster(path: Path, arr, transform, crs=UTM, nodata=None, descriptions=None, dtype=None):
    """Write a 2-D or 3-D (bands first) array as a tiled, compressed GeoTIFF."""
    import numpy as np
    import rasterio

    a = arr if arr.ndim == 3 else arr[None]
    dtype = dtype or a.dtype
    if nodata is None and np.issubdtype(np.dtype(dtype), np.floating):
        nodata = np.nan
    prof = dict(driver="GTiff", width=a.shape[2], height=a.shape[1], count=a.shape[0], dtype=dtype,
                crs=crs, transform=transform, nodata=nodata, compress="deflate", tiled=True,
                blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    if np.issubdtype(np.dtype(dtype), np.floating):
        prof["predictor"] = 3
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(a.astype(dtype))
        if descriptions:
            dst.descriptions = tuple(descriptions)


def read_raster(path: Path, band: int = 1):
    import rasterio

    with rasterio.open(path) as src:
        return src.read(band), src.transform


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"
