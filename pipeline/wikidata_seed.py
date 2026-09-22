#!/usr/bin/env python3
"""
Generate a QuickStatements v1 batch that creates one Wikidata item per standing marker.

Wikidata had zero marker items in Montana or Idaho as of Sep 2026 (checked via SPARQL against
commemorative plaque Q721747 and interpretive sign Q104530379 within the two-state bbox), so this
is a blank-slate seed. Modeling follows the Indiana / North Carolina / Michigan state-marker
projects, which each got a dedicated external-ID property (P9546, P9492, P12604): the batch uses
the state sign number as an alias now and README notes how to propose the ID properties.

Each item gets:
  Len / Den            label + description
  P31  Q104530379      instance of: interpretive sign
  P625                 coordinate location
  P17   Q30            country: United States
  P131                 located in: county (data/wikidata_counties.json), else the state
  P137                 operator: the state agency (STATE table below)
  S854 / S813          reference: source service URL + retrieval date
  Aen                  alias: "<STATE>-<agency number>"

Run:  python pipeline/wikidata_seed.py   →  dist/wikidata_quickstatements.txt
Then paste into https://quickstatements.toolforge.org/ (batch mode, v1) under your own account.
Review the first 10 lines by hand; run in batches of ~100. States not in STATE are skipped.
"""
from __future__ import annotations
import json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FC = json.loads((ROOT / "data" / "markers.geojson").read_text())
COUNTIES = json.loads((ROOT / "data" / "wikidata_counties.json").read_text())
STATE = {"MT": ("Montana", "Q1212", "Q5558259", "Montana Department of Transportation historical highway marker"),
         "ID": ("Idaho", "Q1221", "Q4925016", "Idaho highway historical marker")}
INSTANCE = "Q104530379"  # interpretive sign
TODAY = time.strftime("+%Y-%m-%dT00:00:00Z/11")

def q(s: str) -> str:
    return '"' + s.replace('"', "'").strip() + '"'

def main():
    lines, skipped = [], []
    feats = [f for f in FC["features"] if f["properties"].get("status") != "removed" and f["properties"]["state"] in STATE]
    # Wikidata refuses two items with identical label + description; disambiguate repeats with the agency number
    from collections import Counter
    key = lambda p: (p["title"].rstrip(".").lower(), p["state"], p.get("county"))
    dupes = {k for k, n in Counter(key(f["properties"]) for f in feats).items() if n > 1}
    for f in feats:
        p = f["properties"]
        st, st_q, agency_q, kind = STATE[p["state"]]
        county_q = COUNTIES.get(p["state"], {}).get(p.get("county") or "")
        lon, lat = f["geometry"]["coordinates"]
        title = p["title"].rstrip(".")
        if not title:
            skipped.append(p["id"]); continue
        desc = f"{kind} in {p['county']} County, {st}, United States" if p.get("county") else f"{kind} in {st}, United States"
        if key(p) in dupes:
            desc += f" (sign {p['id'].split('-',1)[1]}" + (f", {p['travel_dir']}" if p.get("travel_dir") else "") + ")"
        ref = f'\tS854\t{q(p["source_url"])}\tS813\t{TODAY}'
        lines += ["CREATE",
                  f"LAST\tLen\t{q(title)}",
                  f"LAST\tDen\t{q(desc)}",
                  f"LAST\tAen\t{q(p['id'])}",
                  f"LAST\tP31\t{INSTANCE}{ref}",
                  f"LAST\tP625\t@{lat:.6f}/{lon:.6f}{ref}",
                  f"LAST\tP17\tQ30",
                  f"LAST\tP137\t{agency_q}{ref}",
                  f"LAST\tP131\t{county_q or st_q}{ref}"]
    out = ROOT / "dist" / "wikidata_quickstatements.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    n = sum(1 for l in lines if l == "CREATE")
    print(f"{n} items → {out}  (skipped {len(skipped)} with empty titles: {skipped})")

if __name__ == "__main__":
    main()
