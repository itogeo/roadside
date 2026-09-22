#!/usr/bin/env python3
"""
Export data/markers.geojson to GPX and KML for GPS units, Gaia/OsmAnd/CalTopo, Garmin, and Google My Maps.

Writes:
  dist/roadside-markers.gpx        all standing markers (waypoints)
  dist/roadside-markers-MT.gpx / -ID.gpx
  dist/roadside-markers.kml        same, styled by state, text in the description balloon

Usage: python pipeline/export_poi.py
"""
from __future__ import annotations
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
FC = json.loads((ROOT / "data" / "markers.geojson").read_text())
STATE_NAME = {"MT": "Montana", "ID": "Idaho"}
COLOR = {"MT": "ff527a5e", "ID": "ff3b57b0"}  # KML is aabbggrr


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
           '<gpx version="1.1" creator="Roadside (github: roadside-markers)" xmlns="http://www.topografix.com/GPX/1/1">',
           '<metadata><name>Roadside — Montana &amp; Idaho highway markers</name>'
           '<desc>Official roadside historical and geological markers. Compilation CC BY 4.0; texts © issuing agency.</desc></metadata>']
    for f in features:
        lon, lat = f["geometry"]["coordinates"]; p = f["properties"]
        out.append(f'<wpt lat="{lat:.6f}" lon="{lon:.6f}"><name>{escape(p["title"])}</name>'
                   f'<desc>{escape(desc(p))}</desc><type>{escape(p.get("topic") or "Historical marker")}</type>'
                   f'<sym>Flag, Blue</sym><cmt>{escape(p["id"])}</cmt></wpt>')
    out.append('</gpx>')
    path.write_text("\n".join(out), encoding="utf-8")


def kml(features, path: Path):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Roadside — Montana &amp; Idaho highway markers</name>']
    for st, c in COLOR.items():
        out.append(f'<Style id="{st}"><IconStyle><color>{c}</color><scale>0.9</scale>'
                   '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>')
    for st in ("MT", "ID"):
        out.append(f'<Folder><name>{STATE_NAME[st]}</name>')
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
    gpx(feats, DIST / "roadside-markers.gpx")
    for st in ("MT", "ID"):
        gpx([f for f in feats if f["properties"]["state"] == st], DIST / f"roadside-markers-{st}.gpx")
    kml(feats, DIST / "roadside-markers.kml")
    site = ROOT / "site" / "dist"; site.mkdir(exist_ok=True)
    for f in DIST.glob("roadside-markers*"): (site / f.name).write_bytes(f.read_bytes())
    print(f"{len(feats)} standing markers → {DIST}")


if __name__ == "__main__":
    main()
