"""Step 14 - published site coordinates for training/validation (clues 2, 4).

STATUS: written but NOT YET RUN. zenodo.org, osf.io and files.osf.io must be allowed in the
cloud environment's network settings (a new session picks the change up).

Sources:
  Dellmour, R. et al. (2026) Stone and water governed early human settlement of the desert.
  Nature, doi:10.1038/s41586-026-11180-5. Data and code: Zenodo 10.5281/zenodo.21758429
  (MIT-licensed code); field data, GPS coordinates: OSF osf.io/4mw23. The supplementary table
  lists 125 investigated localities with coordinates, palaeolake deposits and archaeology.

The tables' exact layout is unknown until they can be downloaded, so columns are matched by
name (latitude/longitude, archaeology, palaeolake, trilith) and the matches are printed for
checking. Output: data/reference/published_sites.csv (one row per locality, with citation),
data/processed/site_alignments.geojson (RANSAC lines through >= 3 trilith sites, if any).
"""
from __future__ import annotations

import importlib
import io
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box

from common import OUTPUTS, PROCESSED, RAW, REFERENCE, UTM, download, load_yaml

CITATION = "Dellmour et al. 2026, Nature, doi:10.1038/s41586-026-11180-5 (Zenodo 21758429; OSF 4mw23)"
S = requests.Session()
dest = RAW / "published_sites"


def zenodo_files(record="21758429"):
    meta = S.get(f"https://zenodo.org/api/records/{record}", timeout=60).json()
    return [(f["key"], f["links"]["self"]) for f in meta.get("files", [])]


def osf_files(node="4mw23", url=None, out=None):
    out = [] if out is None else out
    url = url or f"https://api.osf.io/v2/nodes/{node}/files/osfstorage/"
    while url:
        js = S.get(url, timeout=60).json()
        for item in js.get("data", []):
            a = item["attributes"]
            if a["kind"] == "folder":
                osf_files(url=item["relationships"]["files"]["links"]["related"]["href"], out=out)
            else:
                out.append((a["name"], item["links"]["download"]))
        url = js.get("links", {}).get("next")
    return out


files = []
for fetch in (zenodo_files, osf_files):
    try:
        files += fetch()
    except Exception as exc:
        print(f"{fetch.__name__} failed: {type(exc).__name__}: {exc}")
tables = [(n, u) for n, u in files if re.search(r"\.(xlsx|xls|csv)$", n, re.I)]
print("candidate tables:", [n for n, _ in tables])

rows = []
for name, url in tables:
    p = download(url, dest / name, session=S)
    frames = (pd.read_excel(dest / name, sheet_name=None) if name.lower().endswith(("xlsx", "xls"))
              else {"csv": pd.read_csv(dest / name)})
    for sheet, df in frames.items():
        cols = {c: str(c).lower() for c in df.columns}
        lat = next((c for c, l in cols.items() if re.search(r"\blat", l)), None)
        lon = next((c for c, l in cols.items() if re.search(r"\blon|\blong", l)), None)
        if lat is None or lon is None:
            continue
        arch = [c for c, l in cols.items() if re.search(r"archaeolog|artefact|artifact|lithic|site type", l)]
        lake = [c for c, l in cols.items() if re.search(r"palaeolake|paleolake|lacustrine|lake", l)]
        print(f"{name}/{sheet}: lat={lat!r} lon={lon!r} archaeology={arch} palaeolake={lake}")
        for _, r in df.iterrows():
            try:
                la, lo = float(r[lat]), float(r[lon])
            except (TypeError, ValueError):
                continue
            yes = lambda cs: any(str(r[c]).strip().lower() not in ("", "nan", "0", "no", "none", "false", "-")
                                 for c in cs)
            text = " ".join(str(r[c]) for c in df.columns).lower()
            rows.append({"source_file": f"{name}/{sheet}", "lat": la, "lon": lo,
                         "is_archaeological": yes(arch), "is_palaeolake": yes(lake),
                         "is_trilith": "trilith" in text, "citation": CITATION})

sites = pd.DataFrame(rows)
if sites.empty:
    raise SystemExit("no coordinate tables could be parsed; check the printed file list")
ctx = load_yaml("aoi.yaml")["context_bbox"]
g = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(sites.lon, sites.lat), crs=4326)
g = g[g.intersects(box(*ctx))]
g.drop(columns="geometry").to_csv(REFERENCE / "published_sites.csv", index=False)
print(f"{len(g)} localities in the context box: {int(g.is_archaeological.sum())} archaeological, "
      f"{int(g.is_palaeolake.sum())} palaeolake, {int(g.is_trilith.sum())} trilith")

tril = g[g.is_trilith].to_crs(UTM)
if len(tril) >= 3:
    fit_alignments = importlib.import_module("12_anomalies_tracks").fit_alignments
    lines = fit_alignments(np.c_[tril.geometry.x, tril.geometry.y])
    gpd.GeoDataFrame(lines, crs=UTM).to_crs(4326).to_file(PROCESSED / "site_alignments.geojson")
    print(f"{len(lines)} trilith alignment lines written")
