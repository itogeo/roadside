#!/usr/bin/env python3
"""
Roadside — build the marker dataset for Montana + Idaho.

Pulls only officially published sources:
  * Montana DOT   : Historical_Highway_Marker feature service (titles + locations)
  * Montana DOT   : travinfo/geomarkers.aspx (full text for ~50 geologic markers)
  * Idaho ITD     : HistoricalMarkerSigns_ViewLayer feature service (full text)

Writes:
  data/markers.geojson   canonical dataset (also copied to site/data/)
  data/markers.csv       flat export
  data/build_report.json coverage stats

Usage: python pipeline/build.py
"""
from __future__ import annotations
import csv, html, json, re, sys, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "site" / "data"
UA = "Roadside/0.1 (open-source roadside marker map)"

MT_URL = ("https://gis.mtmdt.us/server/rest/services/MDTGIS/Historical_Highway_Marker/"
          "MapServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson")
MT_GEO_URL = "https://www.mdt.mt.gov/travinfo/geomarkers.aspx"
ID_URL = ("https://services1.arcgis.com/Qqv4dYPC8Vv8e3c3/arcgis/rest/services/"
          "HistoricalMarkerSigns_ViewLayer/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson")

ID_TOPIC = {1: "Education", 2: "Geology / natural history", 3: "Mining / industry", 4: "Railroad",
            5: "Transportation", 6: "Native American", 7: "Oregon / California Trail",
            8: "Farming / agriculture", 9: "Lewis & Clark", 10: "Pioneer / settlement",
            11: "Military", 12: "Engineering / technology", 99: "Other"}
ID_STATUS = {0: "removed", 1: "active", 99: "unknown"}
MT_TYPE = {"HISTORICAL": "History", "GEOLOGIC": "Geology / natural history", "INDIAN": "Native American",
           "LEWIS AND CLARK": "Lewis & Clark", "LEWIS & CLARK": "Lewis & Clark"}


def fetch(url: str, retries: int = 3) -> bytes:
    for i in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            print(f"  retry {i+1} after error: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


SMALL = {"a","an","and","at","but","by","for","in","of","on","or","the","to","vs"}
def smart_title(s: str) -> str:
    """Title-case MDT's ALL-CAPS titles without mangling Mc/Mac names, apostrophes or small words."""
    if not s.isupper():
        return s
    words = []
    for i, w in enumerate(s.lower().split()):
        if i and w in SMALL:
            words.append(w); continue
        w = re.sub(r"(^|[-/(\"“])(\w)", lambda m: m.group(1) + m.group(2).upper(), w)
        w = re.sub(r"^(mc|mac)(\w)", lambda m: m.group(1).capitalize() + m.group(2).upper(), w)
        w = re.sub(r"[’']S$", "'s", w)
        words.append(w)
    return " ".join(words)


def norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def scrape_mt_geologic(page: str) -> dict[str, dict]:
    """Return {normalized title: {text, location, lat, lon, pdf, title}} from MDT's geologic markers page."""
    i = page.find("1. Kootenai Falls and the Belt Supergroup")
    body = page[max(0, i - 2000):]
    parts = re.split(r"<h[2-4][^>]*>\s*(\d+)\.\s*([^<]+)</h[2-4]>", body)
    out = {}
    for k in range(1, len(parts) - 2, 3):
        title, chunk = parts[k + 1].strip(), parts[k + 2]
        pdf = re.search(r'href="([^"]+\.pdf)"', chunk, re.I)
        txt = re.sub(r"<script.*?</script>", "", chunk, flags=re.S)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
        txt = re.sub(r"\s+", " ", txt).strip()
        m = re.match(r"(?P<loc>.*?)\s*GPS Latitude:\s*(?P<lat>-?[\d.]+)\s*Longitude:\s*(?P<lon>-?[\d.]+)\s*"
                     r"(?:View/Download a PDF of the Road Sign\s*)?(?P<text>.*)", txt, re.S)
        rec = {"text": txt, "location": None, "lat": None, "lon": None,
               "pdf": (pdf.group(1) if pdf else None)}
        if m:
            rec.update(text=m.group("text").strip(), location=m.group("loc").strip(),
                       lat=float(m.group("lat")), lon=float(m.group("lon")))
        # some signs list two GPS points (east/west-bound); strip any leftover coordinate lines
        rec["text"] = re.sub(r"^(?:\([^)]*\)\s*)?(?:GPS\s*)?Latitude:\s*-?[\d.]+\s*Longitude:\s*-?[\d.]+\s*"
                             r"(?:View/Download a PDF of the Road Sign\s*)?", "", rec["text"]).strip()
        rec["text"] = re.split(r"\bBack to (?:Top|Map)\b|\bAccessibility\s+Privacy", rec["text"], flags=re.I)[0].strip()
        rec["title"] = re.sub(r"\s+", " ", title)
        out.setdefault(norm_title(rec["title"]), []).append(rec)
    return out


STOP = {"the","a","an","of","and","in","on","at","to"}
def tokens(s: str) -> set[str]:
    return {t for t in norm_title(s).split() if t not in STOP}


def match_geo(title: str, lat: float, lon: float, geo: dict[str, list]) -> dict | None:
    """Pick the MDT geologic page entry with the best title overlap that is also physically close.
    MDT's GIS titles and web-page titles differ in wording, and some titles repeat at several sites,
    so we score = token Jaccard, and require the page's GPS point to be within ~0.15° (~10 mi)."""
    tt = tokens(title)
    if not tt:
        return None
    best, best_score = None, 0.0
    for recs in geo.values():
        for r in recs:
            if r["lat"] is None:
                continue
            if (r["lat"] - lat) ** 2 + (r["lon"] - lon) ** 2 > 0.15 ** 2:
                continue
            gt = tokens(r["title"])
            score = len(tt & gt) / len(tt | gt)
            if score > best_score:
                best, best_score = r, score
    return best if best_score >= 0.4 else None


def build_montana() -> list[dict]:
    print("Montana: fetching MDT feature service…")
    gj = json.loads(fetch(MT_URL))
    print("Montana: fetching geologic marker texts…")
    geo = scrape_mt_geologic(fetch(MT_GEO_URL).decode("utf-8", "ignore"))
    feats, matched = [], 0
    for f in gj["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        title = (p.get("TITLE") or "").strip()
        g = match_geo(title, lat, lon, geo)
        if g: matched += 1
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
                "id": f"MT-{p['OBJECTID']}",
                "state": "MT",
                "title": smart_title(title),
                "text": g["text"] if g else None,
                "text_source": ("Montana DOT, travinfo/geomarkers.aspx" if g else None),
                "text_status": "official" if g else "pending",
                "topic": MT_TYPE.get(p.get("MARKER_TYPE"), p.get("MARKER_TYPE")),
                "status": (p.get("STATUS") or "").lower() or None,
                "travel_dir": p.get("TRAVEL_DIR"),
                "location_note": (g or {}).get("location"),
                "sign_pdf": (g or {}).get("pdf"),
                "image_url": None, "image_license": None, "image_credit": None,
                "wikidata_qid": None,
                "source_url": MT_URL.split("/query")[0],
                "source_agency": "Montana Department of Transportation",
                "source_id": str(p["OBJECTID"]),
            },
        })
    print(f"Montana: {len(feats)} markers, {matched} with official text")
    return feats


def build_idaho() -> list[dict]:
    print("Idaho: fetching ITD feature service…")
    gj = json.loads(fetch(ID_URL))
    feats = []
    from collections import Counter
    n_by_sign = Counter(f["properties"].get("SignNumber") for f in gj["features"])
    for f in gj["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        text = (p.get("MainText") or "").strip() or None
        # a few sign numbers are two physical signs (one per direction); keep both, make the id unique
        mid = f"ID-{p['SignNumber']}" + (f"-{p['OBJECTID']}" if n_by_sign[p.get("SignNumber")] > 1 else "")
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
                "id": mid,
                "state": "ID",
                "title": (p.get("Title") or "").strip(),
                "subtitle": (p.get("Subtitle") or "").strip() or None,
                "text": text,
                "text_source": "Idaho Transportation Department, HistoricalMarkerSigns_ViewLayer" if text else None,
                "text_status": "official" if text else "pending",
                "topic": ID_TOPIC.get(p.get("Topic")),
                "status": ID_STATUS.get(p.get("Status"), "unknown"),
                "route": p.get("Route"),
                "milepost": p.get("Milepost"),
                "county": p.get("County"),
                "date_installed": p.get("DateInstalled"),
                "image_url": None, "image_license": None, "image_credit": None,
                "wikidata_qid": None,
                "source_url": ID_URL.split("/query")[0],
                "source_agency": "Idaho Transportation Department / Idaho State Historical Society",
                "source_id": str(p.get("SignNumber")),
            },
        })
    print(f"Idaho: {len(feats)} markers, {sum(1 for x in feats if x['properties']['text'])} with official text")
    return feats


def build_generic(cfg: dict) -> list[dict]:
    """Any state whose markers are a plain ArcGIS feature service: pipeline/sources/<xx>.json drives this."""
    st = cfg["state"]; fm = cfg["fields"]
    url = cfg["url"].rstrip("/") + f"/query?where={cfg.get('where', '1=1')}&outFields=*&outSR=4326&f=geojson"
    print(f"{st}: fetching {cfg['agency']}…")
    gj = json.loads(fetch(url))
    feats = []
    g = lambda p, k: (p.get(fm[k]) if fm.get(k) else None)
    for f in gj["features"]:
        if not f.get("geometry"): continue
        p = f["properties"]; lon, lat = f["geometry"]["coordinates"]
        text = (str(g(p, "text") or "")).strip() or None
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {"id": f"{st}-{g(p, 'id')}", "state": st, "title": smart_title(str(g(p, "title") or "").strip()),
                "subtitle": g(p, "subtitle"), "text": text, "text_source": f"{cfg['agency']}, {cfg['url']}" if text else None,
                "text_status": "official" if text else "pending",
                "topic": cfg.get("topic_map", {}).get(str(g(p, "topic")), g(p, "topic")),
                "status": cfg.get("status_map", {}).get(str(g(p, "status")), (str(g(p, "status")).lower() if g(p, "status") else "unknown")),
                "route": g(p, "route"), "milepost": g(p, "milepost"), "county": g(p, "county"),
                "image_url": None, "image_license": None, "image_credit": None, "wikidata_qid": None,
                "source_url": cfg["url"], "source_agency": cfg["agency"], "source_id": str(g(p, "id"))}})
    print(f"{st}: {len(feats)} markers, {sum(1 for x in feats if x['properties']['text'])} with official text")
    return feats


def apply_contributions(feats: list[dict]) -> list[dict]:
    """Fold data/contributions/*.json (accepted GitHub issues, see ingest_issues.py) on top of the state sources."""
    cdir = ROOT / "data" / "contributions"
    if not cdir.exists(): return feats
    by_id = {f["properties"]["id"]: f for f in feats}
    for path in sorted(cdir.glob("*.json")):
        c = json.loads(path.read_text()); ref = f"community, GitHub issue #{c['issue']}"
        if c.get("kind") == "fix" and c.get("id") in by_id:
            p = by_id[c["id"]]["properties"]
            if c.get("what") == "Sign has been removed": p["status"] = "removed"
            elif c.get("what") == "Text has an error" and c.get("correction"): p["text"], p["text_source"], p["text_status"] = c["correction"], ref, "community"
            elif c.get("what") == "Title is wrong" and c.get("correction"): p["title"] = c["correction"]
            elif c.get("what") == "Location is off" and "lat" in c: by_id[c["id"]]["geometry"]["coordinates"] = [c["lon"], c["lat"]]
            p["contributions"] = (p.get("contributions") or []) + [c["url"]]
        elif c.get("kind") == "add" and "lat" in c and c.get("title"):
            st = (c.get("state") or "XX")[:2].upper(); mid = f"{st}-community-{c['issue']}"
            if mid in by_id: continue
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": {"id": mid, "state": st, "title": c["title"], "text": c.get("text"), "text_source": ref if c.get("text") else None,
                    "text_status": "community" if c.get("text") else "pending", "topic": None, "status": "active",
                    "image_url": c.get("image_url"), "image_license": None, "image_credit": None, "wikidata_qid": None,
                    "source_url": c["url"], "source_agency": "Community submission", "source_id": str(c["issue"]), "contributions": [c["url"]]}})
            by_id[mid] = feats[-1]
    return feats


def main() -> None:
    feats = build_montana() + build_idaho()
    for cfg_path in sorted((ROOT / "pipeline" / "sources").glob("*.json")):
        feats += build_generic(json.loads(cfg_path.read_text()))
    feats = apply_contributions(feats)
    gj = {"type": "FeatureCollection",
          "name": "roadside-markers",
          "license": "CC BY 4.0 (compilation). Marker texts © their issuing agency; see text_source.",
          "generated": time.strftime("%Y-%m-%d"),
          "features": feats}
    DATA.mkdir(exist_ok=True); SITE_DATA.mkdir(parents=True, exist_ok=True)
    for out in (DATA / "markers.geojson", SITE_DATA / "markers.geojson"):
        out.write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")))
    cols = ["id", "state", "title", "topic", "status", "text_status", "text", "route", "milepost",
            "county", "source_agency", "source_url"]
    with (DATA / "markers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(cols + ["lat", "lon"])
        for f in feats:
            p = f["properties"]; lon, lat = f["geometry"]["coordinates"]
            w.writerow([p.get(c) for c in cols] + [lat, lon])
    rep = {}
    for st in sorted({f["properties"]["state"] for f in feats}):
        s = [f["properties"] for f in feats if f["properties"]["state"] == st]
        rep[st] = {"markers": len(s), "active": sum(1 for p in s if p["status"] != "removed"),
                   "with_official_text": sum(1 for p in s if p["text"]),
                   "topics": sorted({p["topic"] for p in s if p["topic"]})}
    (DATA / "build_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
