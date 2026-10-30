"""Helpers for web maps: warp rasters to Web Mercator and embed them as data URIs."""
from __future__ import annotations

import base64
import io

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject


def to_mercator(arr, src_t, src_crs="EPSG:4326", bands_first=False, resampling=Resampling.bilinear,
                max_px=None):
    """Warp a 2-D (or bands-first 3-D) array to EPSG:3857.

    Returns (array, [[south, west], [north, east]]) - the bounds Leaflet's ImageOverlay needs.
    """
    a = arr if bands_first else arr[None]
    h, w = a.shape[1:]
    b = rasterio.transform.array_bounds(h, w, src_t)
    dst_t, W, H = calculate_default_transform(src_crs, "EPSG:3857", w, h, *b)
    if max_px and max(W, H) > max_px:
        s = max(W, H) / max_px
        dst_t = dst_t * dst_t.scale(s, s)
        W, H = int(W / s), int(H / s)
    out = np.zeros((a.shape[0], H, W), a.dtype)
    for i in range(a.shape[0]):
        reproject(a[i], out[i], src_transform=src_t, src_crs=src_crs, dst_transform=dst_t,
                  dst_crs="EPSG:3857", resampling=resampling)
    wb = rasterio.transform.array_bounds(H, W, dst_t)
    tr = Transformer.from_crs(3857, 4326, always_xy=True)
    lo0, la0 = tr.transform(wb[0], wb[1])
    lo1, la1 = tr.transform(wb[2], wb[3])
    return out, [[la0, lo0], [la1, lo1]]


def block_max(arr: np.ndarray, f: int) -> np.ndarray:
    """Downsample by an integer factor keeping the block maximum (NaN-aware). Rasterio reads
    cannot use 'max' resampling, and averaging would wash out sparse bright features."""
    h, w = (arr.shape[0] // f) * f, (arr.shape[1] // f) * f
    blocks = arr[:h, :w].reshape(h // f, f, w // f, f)
    with np.errstate(all="ignore"):
        return np.nanmax(np.nanmax(blocks, axis=3), axis=1)


def data_uri(img_array: np.ndarray, fmt="PNG", max_px=2200, quality=85):
    """Encode an (H, W, 3|4) uint8 array; WebP keeps transparency at a fraction of PNG size."""
    img = Image.fromarray(img_array)
    if max(img.size) > max_px:
        s = max_px / max(img.size)
        img = img.resize((int(img.size[0] * s), int(img.size[1] * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format=fmt, **({"quality": quality} if fmt in ("JPEG", "WEBP") else {"optimize": True}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()
