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


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"
