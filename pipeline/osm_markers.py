#!/usr/bin/env python3
"""
Roadside — pull community-mapped markers from OpenStreetMap to complement the official state sources.

Why this exists: state DOT feeds only carry the state's *own* signs. OSM has the city, county, museum,
trail and private markers nobody else publishes. Montana: 419 OSM nodes against 356 in the MDT feed.

What it will and will not treat as sign text
--------------------------------------------
The rule for this project is that `text` must be *exactly what the sign says*. OSM has one tag that
means that and several that don't:

  inscription   = the words ON the object.        -> eligible for `text`
  description   = someone's note ABOUT the object -> NEVER used as `text`
  name          = a label, often the mapper's own -> used as `title` only

Even `inscription` is a volunteer transcription with no attestation, so it is never marked
"official" — it lands as text_status="community" with the OSM node id and version recorded, so any
claim can be traced to a specific edit and re-checked. Short inscriptions are kept out of `text`
entirely: on a plaque, a 20-character inscription is a name or a date, not the sign's wording.

Licensing
---------
OSM is ODbL 1.0: attribution AND share-alike. That is a different licence from the official state
data in this dataset, so every OSM-derived record carries its own `license` field rather than
inheriting the collection's. See PLAN.md — if the whole compilation moves to ODbL this gets simpler.

Usage:  python pipeline/osm_markers.py            # states already in markers.geojson
        python pipeline/osm_markers.py MT ID WY   # explicit states
        python pipeline/osm_markers.py --smoke    # offline self-test, no network
"""
from __future__ import annotations
import json, math, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "osm_cache"
UA = "Roadside/0.1 (open-source roadside marker map; https://github.com/itogeo/roadside)"

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]

# An inscription shorter than this is a name, a date or a fragment — not the wording of a sign.
MIN_INSCRIPTION = 60

# Tag combinations that denote a historical marker people read at the roadside.
OVERPASS_BODY = """
  node["historic"="memorial"]["memorial"~"^(plaque|stone|memorial_plaque|marker)$"](area.a);
  node["historic"="marker"](area.a);
  node["tourism"="information"]["information"="board"]["board_type"~"^(history|nature)$"](area.a);
"""

STATE_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# Order matters: first match wins, so the topics that identify *whose* story a sign tells come before
# the generic industry ones. A Nez Perce sign that happens to mention a mine is not a mining sign.
TOPIC_HINTS = [
    (r"lewis|clark|corps of discovery", "Lewis & Clark"),
    (r"\b(tribe|tribal|indian|nez perce|blackfeet|crow|salish|shoshone|kootenai|assiniboine)\b",
     "Native American"),
    (r"oregon trail|california trail|emigrant", "Oregon / California Trail"),
    (r"\b(fort|battle|regiment|veteran|war)\b", "Military"),
    (r"railroad|railway|depot|locomotive", "Railroad"),
    (r"\b(mine|mining|smelter|ore)\b", "Mining / industry"),
    (r"geolog|glacier|volcan|fossil|formation|basalt", "Geology / natural history"),
    (r"school|college|university|academy", "Education"),
    (r"\b(farm|ranch|irrigat|homestead)\b", "Farming / agriculture"),
]


# ---------------------------------------------------------------- network

def overpass(query: str, retries: int = 3) -> list[dict]:
    """POST an Overpass QL query, trying the mirrors in turn. Overpass 504s on big areas, so callers
    should keep each query to one state."""
    last = None
    for attempt in range(retries):
        for ep in ENDPOINTS:
            try:
                req = urllib.request.Request(
                    ep, data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read())["elements"]
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"    {ep.split('/')[2]}: {type(e).__name__} {e}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass failed after {retries} rounds: {last}")


def fetch_state(state: str, refresh: bool = False) -> list[dict]:
    """Raw OSM elements for one state, cached on disk so a rebuild doesn't re-hammer Overpass."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{state}.json"
    if cached.exists() and not refresh:
        print(f"{state}: using cached OSM extract ({cached.name})")
        return json.loads(cached.read_text())["elements"]
    q = f'[out:json][timeout:280];area["ISO3166-2"="US-{state}"]->.a;({OVERPASS_BODY});out body meta;'
    print(f"{state}: querying Overpass…")
    els = overpass(q)
    cached.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "elements": els}))
    print(f"{state}: {len(els)} nodes")
    return els


# ---------------------------------------------------------------- shaping

def clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


# Mappers sometimes put a description of the plaque INTO the inscription tag, e.g. "This plaque,
# located just in front of the Park City Kwik Stop, tells the story of…". That is writing about the
# sign, not the sign's words, so it must not become `text`. These patterns catch the giveaway: the
# object referred to in the third person, or its position described relative to something else.
META_PATTERNS = [
    re.compile(r"\bthis (?:plaque|plague|sign|marker|memorial|monument|board|display)\b[^.]{0,90}?"
               r"\b(?:tells|commemorates|describes|depicts|shows|marks|explains|is located|located|stands|sits)\b",
               re.I),
    # NB: deliberately no bare "near" here — "located near here / near the confluence" is ordinary
    # plaque wording. Only positions given relative to some other named thing signal a description.
    re.compile(r"\blocated\s+(?:just\s+)?(?:in front of|behind|next to|beside|across from|"
               r"at the corner of|on the grounds of)\b", re.I),
    re.compile(r"\bthe (?:plaque|sign|marker|inscription)\s+(?:reads|says|states)\b", re.I),
]


def looks_like_description(s: str) -> bool:
    return any(p.search(s) for p in META_PATTERNS)


def sign_text(tags: dict) -> tuple[str | None, str | None]:
    """Return (text, why_rejected). Only `inscription` is ever eligible — see module docstring.
    When in doubt this rejects: a missing transcription is recoverable, a wrong one presented as the
    sign's words is not."""
    ins = clean(tags.get("inscription"))
    if not ins:
        return None, "no inscription tag"
    if len(ins) < MIN_INSCRIPTION:
        return None, f"inscription too short ({len(ins)} chars) to be the sign's wording"
    if looks_like_description(ins):
        return None, "inscription describes the sign rather than quoting it"
    return ins, None


def guess_topic(tags: dict) -> str | None:
    hay = " ".join(str(tags.get(k, "")) for k in ("name", "inscription", "subject", "description")).lower()
    for pat, topic in TOPIC_HINTS:
        if re.search(pat, hay):
            return topic
    return None


def to_feature(el: dict, state: str) -> dict | None:
    tags = el.get("tags") or {}
    lat, lon = el.get("lat"), el.get("lon")
    if lat is None or lon is None:
        return None
    title = clean(tags.get("name")) or clean(tags.get("inscription:short")) or None
    text, why = sign_text(tags)
    if not title and not text:
        return None  # an untitled, untranscribed point is not usable on the map
    oid = el["id"]
    ver = el.get("version")
    node_url = f"https://www.openstreetmap.org/node/{oid}"
    # An OSM image tag often points at a third-party site whose licence we do not know; only accept
    # Wikimedia Commons, which is free by construction.
    commons = clean(tags.get("wikimedia_commons"))
    image_url = None
    if commons and commons.lower().startswith("file:"):
        image_url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(commons[5:])
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": {
            "id": f"{state}-OSM{oid}",
            "state": state,
            "title": title or (text[:60] + "…"),
            "subtitle": None,
            "text": text,
            # community, never "official": an OSM inscription is an unattested volunteer transcription
            "text_source": f"OpenStreetMap contributors, node/{oid}" + (f" v{ver}" if ver else "") if text else None,
            "text_status": "community" if text else "pending",
            # why an inscription that exists was not accepted as the sign's words — kept so the
            # judgement is auditable rather than invisible
            "text_rejected": (why if (not text and tags.get("inscription")) else None),
            "topic": guess_topic(tags),
            "status": "active",
            "route": clean(tags.get("addr:street")),
            "milepost": None,
            "county": None,
            "image_url": image_url,
            "image_license": "See Wikimedia Commons file page" if image_url else None,
            "image_credit": "Wikimedia Commons" if image_url else None,
            "wikidata_qid": clean(tags.get("wikidata")) or clean(tags.get("subject:wikidata")),
            "source_url": node_url,
            "source_agency": "OpenStreetMap contributors",
            "source_id": str(oid),
            "osm_version": ver,
            "license": "ODbL 1.0",
        },
    }


# ---------------------------------------------------------------- dedup

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def norm_title(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def title_overlap(a: str | None, b: str | None) -> float:
    ta, tb = set(norm_title(a).split()), set(norm_title(b).split())
    ta -= {"the", "a", "of", "and", "in", "on", "at", "to", "marker", "monument", "memorial", "historical"}
    tb -= {"the", "a", "of", "and", "in", "on", "at", "to", "marker", "monument", "memorial", "historical"}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_duplicate(osm_feat: dict, official: list[dict], radius_m: float = 120.0) -> dict | None:
    """An OSM node close to an official marker with an overlapping title is the same sign.
    The official record wins — it has the agency behind it."""
    olon, olat = osm_feat["geometry"]["coordinates"]
    ot = osm_feat["properties"]["title"]
    for f in official:
        lon, lat = f["geometry"]["coordinates"]
        if abs(lat - olat) > 0.01 or abs(lon - olon) > 0.02:
            continue
        d = haversine_m(olat, olon, lat, lon)
        if d > radius_m:
            continue
        if title_overlap(ot, f["properties"].get("title")) >= 0.34 or d <= 25.0:
            return f
    return None


def build(states: list[str], official: list[dict], refresh: bool = False) -> tuple[list[dict], dict]:
    out, report = [], {}
    for st in states:
        els = fetch_state(st, refresh=refresh)
        off_st = [f for f in official if f["properties"].get("state") == st]
        feats, dup, notext = [], 0, 0
        for el in els:
            f = to_feature(el, st)
            if not f:
                continue
            if is_duplicate(f, off_st):
                dup += 1
                continue
            if not f["properties"]["text"]:
                notext += 1
            feats.append(f)
        out += feats
        report[st] = {"osm_nodes": len(els), "kept": len(feats),
                      "dropped_as_duplicate_of_official": dup,
                      "kept_without_sign_text": notext,
                      "kept_with_community_text": len(feats) - notext}
        print(f"{st}: kept {len(feats)} ({len(feats)-notext} with inscription), "
              f"dropped {dup} duplicates of official markers")
    return out, report


# ---------------------------------------------------------------- smoke test

def _smoke() -> int:
    """Offline checks of the rules that matter, so a regression can't quietly widen what counts as sign text."""
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, want {want!r}")

    long_ins = ("In 1870 the mining town of Marysville was established and named for the first "
                "pioneer woman here, Mary Ralston, by Thomas Cruse.")
    check("inscription accepted", sign_text({"inscription": long_ins})[0], long_ins)
    check("description never used as text", sign_text({"description": long_ins})[0], None)
    check("name never used as text", sign_text({"name": long_ins})[0], None)
    check("short inscription rejected", sign_text({"inscription": "Fort Benton City Hall"})[0], None)
    check("whitespace collapsed", sign_text({"inscription": "  A   b\n\nc  " + "x" * 60})[0],
          "A b c " + "x" * 60)
    check("length measured after collapsing", sign_text({"inscription": "a" + " " * 80 + "b"})[0], None)

    f = to_feature({"id": 42, "version": 3, "lat": 46.5, "lon": -112.0,
                    "tags": {"name": "Chief Joseph", "inscription": long_ins, "historic": "memorial"}}, "MT")
    check("id format", f["properties"]["id"], "MT-OSM42")
    check("never official", f["properties"]["text_status"], "community")
    check("odbl recorded", f["properties"]["license"], "ODbL 1.0")
    check("node traceable", f["properties"]["text_source"], "OpenStreetMap contributors, node/42 v3")
    check("topic from inscription", f["properties"]["topic"], "Mining / industry")
    check("identity topic beats industry",
          guess_topic({"name": "Nez Perce Crossing", "inscription": "…past the old mine…"}),
          "Native American")
    check("no topic when nothing matches", guess_topic({"name": "Smith Plaque"}), None)

    meta = ("This plague, located just in front of the Park City Kwik Stop, tells the story of the "
            "site where William Clark and other members of the Corps of Discovery camped.")
    check("description-in-inscription rejected", sign_text({"inscription": meta})[0], None)
    check("rejection reason recorded", sign_text({"inscription": meta})[1],
          "inscription describes the sign rather than quoting it")
    genuine = ("This memorial is dedicated to all the people buried on this land. People from "
               "different cultures lived on 'The Poor Farm' located near here from 1888 onward.")
    check("genuine plaque wording still accepted", sign_text({"inscription": genuine})[0], genuine)

    f2 = to_feature({"id": 43, "lat": 46.5, "lon": -112.0,
                     "tags": {"name": "Some Plaque", "description": long_ins}}, "MT")
    check("description-only -> no text", f2["properties"]["text"], None)
    check("description-only -> pending", f2["properties"]["text_status"], "pending")

    f3 = to_feature({"id": 44, "lat": 46.5, "lon": -112.0, "tags": {"historic": "marker"}}, "MT")
    check("untitled+untranscribed dropped", f3, None)

    f4 = to_feature({"id": 45, "lat": 46.5, "lon": -112.0,
                     "tags": {"name": "X", "image": "https://www.hmdb.org/m.asp?m=188961"}}, "MT")
    check("unknown-licence image refused", f4["properties"]["image_url"], None)
    f5 = to_feature({"id": 46, "lat": 46.5, "lon": -112.0,
                     "tags": {"name": "X", "wikimedia_commons": "File:Test sign.jpg"}}, "MT")
    check("commons image accepted", f5["properties"]["image_url"],
          "https://commons.wikimedia.org/wiki/Special:FilePath/Test%20sign.jpg")

    official = [{"geometry": {"type": "Point", "coordinates": [-112.0, 46.5]},
                 "properties": {"state": "MT", "title": "Marysville Montana"}}]
    near = to_feature({"id": 47, "lat": 46.50005, "lon": -112.00005,
                       "tags": {"name": "Marysville Montana Marker"}}, "MT")
    far = to_feature({"id": 48, "lat": 46.9, "lon": -112.9, "tags": {"name": "Marysville Montana"}}, "MT")
    check("near+same name = duplicate", is_duplicate(near, official) is not None, True)
    check("far = not duplicate", is_duplicate(far, official), None)

    check("haversine ~111km/deg", round(haversine_m(46.0, -112.0, 47.0, -112.0) / 1000), 111)

    for f in fails:
        print("  FAIL", f)
    print(f"smoke: {'all checks passed' if not fails else str(len(fails)) + ' FAILED'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if "--smoke" in argv:
        return _smoke()
    refresh = "--refresh" in argv
    states = [a.upper() for a in argv if re.fullmatch(r"[A-Za-z]{2}", a)]
    markers_path = DATA / "markers.geojson"
    official = json.loads(markers_path.read_text())["features"] if markers_path.exists() else []
    if not states:
        states = sorted({f["properties"]["state"] for f in official}) or ["MT", "ID"]
    bad = [s for s in states if s not in STATE_NAME]
    if bad:
        print(f"unknown state code(s): {bad}", file=sys.stderr)
        return 2
    feats, report = build(states, official, refresh=refresh)
    gj = {"type": "FeatureCollection", "name": "roadside-markers-osm",
          "license": "ODbL 1.0 — © OpenStreetMap contributors. Share-alike applies to this layer.",
          "generated": time.strftime("%Y-%m-%d"), "features": feats}
    DATA.mkdir(exist_ok=True)
    (DATA / "osm_markers.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")))
    (DATA / "osm_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n→ data/osm_markers.geojson  {len(feats)} markers")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
