#!/usr/bin/env python3
"""
Build a self-contained, public-domain basemap (states, counties, highways, town labels) as one PMTiles file,
from US Census cartographic boundary + TIGER road files. No API keys, no tile host — the site loads it by
HTTP range requests straight from the repo / GitHub Pages.

Layers written:
  (place labels use Natural Earth populated places for cities and Census incorporated places for small towns)
  state     polygons (nationwide)
  county    polygons (nationwide)
  road      interstates nationwide + US/state highways for every state that has markers in the dataset
  place     town/city label points (nationwide; ranked by population so labels thin out when zoomed out)

Requires: tippecanoe on PATH, pip install pyogrio shapely
Usage:    python pipeline/build_basemap.py   →  site/tiles/basemap.pmtiles
"""
from __future__ import annotations
import difflib, json, os, re, subprocess, tempfile, urllib.request
from pathlib import Path
import pyogrio
from shapely import from_wkb
from shapely.geometry import mapping
from shapely.strtree import STRtree

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


GOVT = re.compile(r"\b(?:unified|consolidated|metropolitan)\s+government\b")
def norm_place(s: str) -> str:
    """Normalise a place name so Census legal names and Natural Earth's informal ones compare equal:
    'Boise City' == 'Boise', 'Butte-Silver Bow (balance)' == 'Butte', 'Ft.  Worth' == 'Fort Worth'."""
    s = re.sub(r"\([^)]*\)", " ", s.lower())
    s = GOVT.sub(" ", s)
    s = re.sub(r"^\s*(?:town|city|village)\s+of\s+", " ", s)
    s = re.sub(r"\bft\.?\b", "fort", s)
    s = re.sub(r"\bmt\.?\b", "mount", s)
    s = re.sub(r"\bst\.?\b", "saint", s)
    s = re.sub(r"\bcity\s*$", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def variants(s: str) -> set[str]:
    """Census writes some names as 'legal name (common name)' — 'El Paso de Robles (Paso Robles)'.
    Both halves are legitimate names to match on."""
    out = {norm_place(s)}
    for m in re.findall(r"\(([^)]*)\)", s):
        if m.strip().lower() != "balance" and not GOVT.search(m.lower()):
            out.add(norm_place(m))
    return {v for v in out if v}


QUAL = {"east", "west", "north", "south", "new", "old", "upper", "lower", "big", "little", "great"}
def same_place(a: str, b: str) -> bool:
    """True if two place names denote the same town. Prefix match handles the consolidated-government
    suffixes; the ratio catches Natural Earth's typos ('Barlett'/'Bartlett'). A leading direction word is
    never fuzzy-matched away, so genuinely distinct neighbours ('West Yellowstone' vs 'Yellowstone',
    'East Peoria' vs 'Peoria') stay separate."""
    for x in variants(a):
        for y in variants(b):
            if x == y or x.startswith(y + " ") or y.startswith(x + " "):
                return True
            if x.split()[0] in QUAL or y.split()[0] in QUAL:
                continue
            if difflib.SequenceMatcher(None, x, y).ratio() >= 0.80:
                return True
    return False


def main():
    markers = json.loads((ROOT / "data" / "markers.geojson").read_text())
    states_with_markers = sorted({f["properties"]["state"] for f in markers["features"]})
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
        # Cities: Natural Earth populated places (public domain, carries population, which the Census
        # boundary file does not). Ranked 1-3 by population and labelled from zoom 4 / 5 / 7.
        ne_us = [(row["name"], row["adm1name"], row["pop_max"] or 0, geom)
                 for row, geom in read(dl(NE + "ne_10m_populated_places_simple.zip")) if row["iso_a2"] == "US"]
        n = 0
        for name, _, pop, geom in ne_us:
            rank = 1 if pop > 150000 else 2 if pop > 25000 else 3
            f.write(json.dumps({"type": "Feature", "tippecanoe": {"minzoom": {1: 4, 2: 5, 3: 7}[rank]},
                                "properties": {"name": name, "rank": rank},
                                "geometry": mapping(geom)}, separators=(",", ":")) + "\n"); n += 1
        print(f"  ne_10m_populated_places_simple.zip: {n} features")
        # Small towns: Census incorporated places only (no CDPs), from zoom 8. A Census place is skipped when
        # Natural Earth already labels the same town: matched by name+state, or — because the two disagree on
        # legal names ('Boise City'/'Boise', 'Butte-Silver Bow (balance)'/'Butte') — by an NE point falling
        # inside the Census polygon with a matching name. Without the second test those cities label twice.
        ne_names = {(nm, adm) for nm, adm, _, _ in ne_us}
        tree, ne_pts = STRtree([g for _, _, _, g in ne_us]), [nm for nm, _, _, _ in ne_us]
        dropped = []
        def small(p, r, g):
            if r["LSAD"] == "57": return None
            if (p["name"], r["STATE_NAME"]) in ne_names: return None          # same name, same state
            for i in tree.query(g, predicate="contains"):                      # same town, different legal name
                if same_place(p["name"], ne_pts[i]):
                    dropped.append((p["name"], ne_pts[i])); return None
            return {"name": p["name"], "rank": 4, "_minzoom": 8}
        to_ndjson(dl(CB + "cb_2023_us_place_500k.zip"), f, {"NAME": "name"}, minzoom=8, transform=small, point=True)
        print(f"  deduped against Natural Earth by location: {len(dropped)} Census places")

    cmd = ["tippecanoe", "-o", str(OUT), "--force", "-Z0", "-z10", "--simplification=6", "--detect-shared-borders",
           "--coalesce-densest-as-needed", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping",
           "--attribution=US Census Bureau (public domain); populated places from Natural Earth (public domain)", "--quiet"]
    for name, p in layers:
        cmd += ["-L", f"{name}:{p}"]
    subprocess.run(cmd, check=True)
    print(f"→ {OUT}  {OUT.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
