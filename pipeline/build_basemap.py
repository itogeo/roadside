#!/usr/bin/env python3
"""
Build a self-contained, public-domain basemap (states, counties, highways, town labels) as one PMTiles file,
from US Census cartographic boundary + TIGER road files and Natural Earth populated places. No API keys, no tile
host — the site loads it by HTTP range requests straight from the repo / GitHub Pages.

Layers written:
  state     polygons (nationwide)
  county    polygons (nationwide)
  road      interstates nationwide + US/state highways for every state that has markers in the dataset
  place     label points: Natural Earth cities (ranked by population) + Census incorporated places for small towns

Requires: tippecanoe on PATH, pip install pyogrio shapely
Usage:    python pipeline/build_basemap.py   →  site/tiles/basemap.pmtiles
"""
from __future__ import annotations
import json, os, subprocess, tempfile, urllib.request
from pathlib import Path
import pyogrio
from shapely import from_wkb
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "tiles" / "basemap.pmtiles"
CACHE = Path(os.environ.get("ROADSIDE_CACHE", "/tmp/base")); CACHE.mkdir(parents=True, exist_ok=True)
CB = "https://www2.census.gov/geo/tiger/GENZ2023/shp/"
TIGER = "https://www2.census.gov/geo/tiger/TIGER2023/"
NE = "https://naciscdn.org/naturalearth/10m/cultural/"
FIPS = {"AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09","DE":"10","DC":"11","FL":"12","GA":"13","HI":"15","ID":"16","IL":"17","IN":"18","IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24","MA":"25","MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31","NV":"32","NH":"33","NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38","OH":"39","OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46","TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54","WI":"55","WY":"56"}


def dl(url: str) -> Path:
    p = CACHE / url.rsplit("/", 1)[1]
    if not p.exists():
        print("  downloading", p.name)
        p.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Roadside/0.1"})).read())
    return p


def read(zip_path: Path, where=None):
    """Yield (properties dict, shapely geometry) without needing geopandas."""
    meta, _, geoms, fields = pyogrio.raw.read(f"zip://{zip_path}", where=where)
    names = list(meta["fields"])
    for i, wkb in enumerate(geoms):
        yield {n: fields[j][i] for j, n in enumerate(names)}, from_wkb(wkb)


def to_ndjson(zip_path: Path, out, keep: dict, minzoom: int, where=None, transform=None, point=False):
    """Stream a shapefile zip into newline-delimited GeoJSON with a trimmed property set and a per-feature minzoom."""
    n = 0
    for row, geom in read(zip_path, where):
        props = {k2: row[k1] for k1, k2 in keep.items()}
        if transform:
            props = transform(props, row, geom)
        if props is None:
            continue
        mz = props.pop("_minzoom", minzoom)
        g = geom.representative_point() if point else geom
        out.write(json.dumps({"type": "Feature", "tippecanoe": {"minzoom": mz}, "properties": props,
                              "geometry": mapping(g)}, separators=(",", ":")) + "\n"); n += 1
    print(f"  {zip_path.name}: {n} features")


def main():
    markers = json.loads((ROOT / "data" / "markers.geojson").read_text())
    states_with_markers = sorted({f["properties"]["state"] for f in markers["features"]} & set(FIPS))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    layers = []

    def layer(name):
        p = tmp / f"{name}.ndjson"; layers.append((name, p)); return open(p, "w")

    with layer("state") as f:
        to_ndjson(dl(CB + "cb_2023_us_state_500k.zip"), f, {"STUSPS": "abbr", "NAME": "name"}, minzoom=0)
    with layer("county") as f:
        to_ndjson(dl(CB + "cb_2023_us_county_500k.zip"), f, {"NAME": "name", "STUSPS": "state"}, minzoom=5)
    with layer("road") as f:
        def rd(p, r, g):
            cls = {"I": "interstate", "U": "us", "S": "state"}.get(p["rt"])
            if not cls: return None
            return {"name": p["name"] or "", "cls": cls, "_minzoom": {"interstate": 3, "us": 5, "state": 7}[cls]}
        to_ndjson(dl(TIGER + "PRIMARYROADS/tl_2023_us_primaryroads.zip"), f, {"FULLNAME": "name", "RTTYP": "rt"}, minzoom=3, transform=rd)
        for st in states_with_markers:
            to_ndjson(dl(TIGER + f"PRISECROADS/tl_2023_{FIPS[st]}_prisecroads.zip"), f, {"FULLNAME": "name", "RTTYP": "rt"},
                      minzoom=5, where="MTFCC = 'S1200'", transform=rd)
    with layer("place") as f:
        # Cities: Natural Earth populated places (public domain, has population) — ranks 1-3, labelled from zoom 4.
        def ne(p, r, g):
            if r["iso_a2"] != "US": return None
            pop = r["pop_max"] or 0
            rank = 1 if pop > 150000 else 2 if pop > 25000 else 3
            return {"name": p["name"], "rank": rank, "_minzoom": {1: 4, 2: 5, 3: 7}[rank]}
        to_ndjson(dl(NE + "ne_10m_populated_places_simple.zip"), f, {"name": "name"}, minzoom=4, transform=ne, point=True)
        # Small towns: Census incorporated places only (no CDPs), shown from zoom 8; skipped if Natural Earth already has the name.
        ne_names = set()
        for row, geom in read(dl(NE + "ne_10m_populated_places_simple.zip")):
            if row["iso_a2"] == "US": ne_names.add((row["name"], row["adm1name"]))
        def small(p, r, g):
            if r["LSAD"] == "57": return None
            if (p["name"], r["STATE_NAME"]) in ne_names: return None
            return {"name": p["name"], "rank": 4, "_minzoom": 8}
        to_ndjson(dl(CB + "cb_2023_us_place_500k.zip"), f, {"NAME": "name"}, minzoom=8, transform=small, point=True)

    cmd = ["tippecanoe", "-o", str(OUT), "--force", "-Z0", "-z10", "--simplification=6", "--detect-shared-borders",
           "--coalesce-densest-as-needed", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping",
           "--attribution=US Census Bureau, Natural Earth (public domain)", "--quiet"]
    for name, p in layers:
        cmd += ["-L", f"{name}:{p}"]
    subprocess.run(cmd, check=True)
    print(f"→ {OUT}  {OUT.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
