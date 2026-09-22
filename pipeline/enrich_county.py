#!/usr/bin/env python3
"""Assign a county (name + FIPS) to every marker via point-in-polygon on Census cartographic boundaries.
Fills `county` where the state layer didn't supply one (Montana) and adds `county_fips` everywhere.
Usage: python pipeline/enrich_county.py  (downloads ~12 MB from census.gov on first run)"""
from __future__ import annotations
import io, json, urllib.request, zipfile
from pathlib import Path
import shapefile
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
GJ = ROOT / "data" / "markers.geojson"
CB = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
CACHE = Path("/tmp/cb_2023_us_county_500k.zip")

def main():
    if not CACHE.exists():
        CACHE.write_bytes(urllib.request.urlopen(urllib.request.Request(CB, headers={"User-Agent": "Roadside/0.1"})).read())
    z = zipfile.ZipFile(CACHE)
    base = [n for n in z.namelist() if n.endswith(".shp")][0][:-4]
    r = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), dbf=io.BytesIO(z.read(base + ".dbf")), shx=io.BytesIO(z.read(base + ".shx")))
    polys, meta = [], []
    for sr in r.iterShapeRecords():
        if sr.record["STATEFP"] in ("16", "30"):  # ID, MT
            polys.append(shape(sr.shape.__geo_interface__)); meta.append((sr.record["NAME"], sr.record["GEOID"]))
    tree = STRtree(polys)
    fc = json.loads(GJ.read_text()); filled = 0
    for f in fc["features"]:
        pt = Point(*f["geometry"]["coordinates"]); p = f["properties"]
        hits = [i for i in tree.query(pt) if polys[i].covers(pt)]
        if not hits:
            i = min(range(len(polys)), key=lambda k: polys[k].distance(pt))  # a few points sit just across a line
        else:
            i = hits[0]
        name, fips = meta[i]
        if not p.get("county"): p["county"] = name; filled += 1
        p["county_fips"] = fips
    GJ.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
    (ROOT / "site" / "data" / "markers.geojson").write_text(GJ.read_text())
    print(f"county filled for {filled} markers; county_fips set on {len(fc['features'])}")

if __name__ == "__main__":
    main()
