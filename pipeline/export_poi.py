#!/usr/bin/env python3
"""
Export data/markers.geojson to GPX and KML for GPS units, Gaia/OsmAnd/CalTopo, Garmin, and Google My Maps.

Writes (to dist/ and site/dist/):
  roadside-markers.gpx         all standing markers (waypoints)
  roadside-markers-<ST>.gpx    one per state
  roadside-markers.kml         same, styled by state, text in the description balloon

Usage: python pipeline/export_poi.py
"""
from __future__ import annotations
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
FC = json.loads((ROOT / "data" / "markers.geojson").read_text())
PALETTE = ["ff527a5e", "ff3b57b0", "ff8a6a3b", "ff6b5e9a", "ff3a8aa2", "ffb08a3b"]  # KML aabbggrr, cycles per state


def standing(features):
    return [f for f in features if f["properties"].get("status") != "removed"]


def desc(p: dict) -> str:
    bits = []
    if p.get("subtitle"): bits.append(p["subtitle"])
    bits.append(p["text"] if p.get("text") else "Sign text not yet published online by the state.")
    if p.get("route"): bits.append(f"{p['route']}" + (f" MP {p['milepost']}" if p.get("milepost") else ""))
    bits.append(f"Source: {p['source_agency']} (#{p['source_id']})")
    return "\n\n".join(bits)


def gpx(features, path: Path):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="Roadside (github.com/itogeo/roadside)" xmlns="http://www.topografix.com/GPX/1/1">',
           '<metadata><name>Roadside — official highway markers</name>'
           '<desc>Official roadside historical and geological markers. Compilation CC BY 4.0; texts © issuing agency.</desc></metadata>']
    for f in features:
        lon, lat = f["geometry"]["coordinates"]; p = f["properties"]
        out.append(f'<wpt lat="{lat:.6f}" lon="{lon:.6f}"><name>{escape(p["title"])}</name>'
                   f'<desc>{escape(desc(p))}</desc><type>{escape(p.get("topic") or "Historical marker")}</type>'
                   f'<sym>Flag, Blue</sym><cmt>{escape(p["id"])}</cmt></wpt>')
    out.append('</gpx>')
    path.write_text("\n".join(out), encoding="utf-8")


def kml(features, states, path: Path):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Roadside — official highway markers</name>']
    for i, st in enumerate(states):
        out.append(f'<Style id="{st}"><IconStyle><color>{PALETTE[i % len(PALETTE)]}</color><scale>0.9</scale>'
                   '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>')
    for st in states:
        out.append(f'<Folder><name>{st}</name>')
        for f in features:
            p = f["properties"]
            if p["state"] != st: continue
            lon, lat = f["geometry"]["coordinates"]
            out.append(f'<Placemark><name>{escape(p["title"])}</name><styleUrl>#{st}</styleUrl>'
                       f'<description><![CDATA[{desc(p).replace(chr(10), "<br>")}]]></description>'
                       f'<Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point></Placemark>')
        out.append('</Folder>')
    out.append('</Document></kml>')
    path.write_text("\n".join(out), encoding="utf-8")


def main():
    DIST.mkdir(exist_ok=True)
    feats = standing(FC["features"])
    states = sorted({f["properties"]["state"] for f in feats})
    gpx(feats, DIST / "roadside-markers.gpx")
    for st in states:
        gpx([f for f in feats if f["properties"]["state"] == st], DIST / f"roadside-markers-{st}.gpx")
    kml(feats, states, DIST / "roadside-markers.kml")
    site = ROOT / "site" / "dist"; site.mkdir(parents=True, exist_ok=True)
    for f in DIST.glob("roadside-markers*"): (site / f.name).write_bytes(f.read_bytes())
    print(f"{len(feats)} standing markers in {len(states)} states → {DIST}")


if __name__ == "__main__":
    main()
