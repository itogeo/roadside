# Roadside

An open map of every official roadside historical and geological marker in Montana and Idaho —
with the sign text, where the state publishes it — so you can read the sign without pulling over.

**Live site:** https://itogeo.github.io/roadside/

## What's in the box

```
pipeline/build.py           Pulls the official state sources, normalizes, writes GeoJSON + CSV. Stdlib only.
pipeline/enrich_county.py   Point-in-polygon county + FIPS from Census boundaries (needs shapely, pyshp).
pipeline/export_poi.py      GPX + KML for Garmin, Gaia, OsmAnd, CalTopo, Google My Maps.
pipeline/wikidata_seed.py   QuickStatements batch to create one Wikidata item per standing marker.
data/markers.geojson        The dataset (673 markers, 637 standing). Also copied to site/data/ for the map.
data/markers.csv            Flat export of the same.
data/wikidata_counties.json County QIDs used by the seed script.
dist/                       Built exports: .gpx (all / MT / ID), .kml, wikidata_quickstatements.txt
pipeline/build_basemap.py   Public-domain basemap (states, counties, highways, towns) from Census → one PMTiles file.
pipeline/ingest_issues.py   Pulls accepted GitHub issues (from the site's forms) into data/contributions/.
pipeline/serve.py           Local dev server with Range support (PMTiles needs it).
pipeline/sources/           One JSON per additional state — see docs/adding-a-state.md.
site/index.html             Static MapLibre site. No build step, no API keys, no outside services.
site/tiles/basemap.pmtiles  12 MB nationwide basemap, served by range requests from this folder.
site/tiles/markers.pmtiles  The markers as vector tiles (300 KB) for anyone who wants them that way.
site/fonts/                 Self-hosted glyphs for map labels.
```

## Sources (v0.1)

| State | Locations + titles | Sign text | Where it comes from |
|---|---|---|---|
| Montana | 356 markers | 59 (the geologic series) | MDT `Historical_Highway_Marker` feature service; text scraped from `mdt.mt.gov/travinfo/geomarkers.aspx` |
| Idaho | 317 markers (281 standing) | 316 | ITD `HistoricalMarkerSigns_ViewLayer` feature service (`MainText` field), run with the Idaho State Historical Society |

Montana's *historical* marker texts are not published online by MDT — they exist in the Montana Historical
Society's book *Montana's Historical Highway Markers* and on HMdb.org. Those records are in the dataset with
`text_status: "pending"` and a title/location, so they can be filled in once MDT/MHS share the text.
Robert Fletcher's original 1938 booklet *Montana Highway Historical Markers* may be public domain
(US works from 1930–1963 needed renewal); worth checking the Stanford Copyright Renewal Database before
transcribing the surviving Fletcher-era signs from it.

## Schema

Every feature carries: `id`, `state`, `title`, `subtitle`, `text`, `text_source`, `text_status`
(`official` | `pending`), `topic`, `status` (`active` | `removed` | …), `route`, `milepost`, `county`,
`image_url` / `image_license` / `image_credit` (empty for now — Wikimedia Commons and user uploads planned),
`wikidata_qid` (empty for now), `source_url`, `source_agency`, `source_id`.

## Hosting

Free and unmanaged by design. Fork → Settings → Pages → source "GitHub Actions". The `Deploy site` workflow
publishes `site/` and the `Monthly data rebuild` workflow keeps the data fresh and opens a PR you can merge.
There is no server, no token, no tile host and no account other than GitHub. MapLibre reads the basemap and
markers straight out of the repo with HTTP range requests. If you'd rather have a richer basemap, MapLibre
can load a Mapbox or OpenFreeMap style instead — swap the `style` object in `index.html` — but then your
fork depends on that service.

## Build

```
pip install shapely pyshp          # only enrich_county.py needs these
python pipeline/build.py           # ~5 s
python pipeline/enrich_county.py   # county / FIPS on every marker
python pipeline/export_poi.py      # dist/*.gpx, dist/*.kml
python pipeline/wikidata_seed.py   # dist/wikidata_quickstatements.txt
python pipeline/build_basemap.py   # needs tippecanoe on PATH; ~1 min, 12 MB
python pipeline/serve.py           # http://localhost:8000 (plain http.server can't serve PMTiles)
```

## Using the POI files

- **Garmin / Gaia GPS / OsmAnd / CalTopo / Organic Maps:** import `dist/roadside-markers.gpx`. Every one of these
  can alert on approach to a waypoint, so you get "marker ahead" without installing anything new.
- **Google My Maps:** import `dist/roadside-markers.kml` (or the .gpx). Balloon shows the sign text.
- **Apple / Google Maps turn-by-turn:** no bulk import; use the site's Directions link per marker.

## Seeding Wikidata

As of Sep 2026 Wikidata has **no** marker items in Montana or Idaho, so `dist/wikidata_quickstatements.txt`
is a blank-slate seed of 637 items (instance of *interpretive sign* Q104530379, coordinates, county, operator
agency, sourced to the state feature service). Paste it into <https://quickstatements.toolforge.org/> in
batches of ~100 under your own account after checking the first few by hand. Follow-ups worth doing on-wiki:

1. Propose two external-ID properties, "Idaho Highway Historical Marker ID" and "Montana Historical Highway
   Marker ID", mirroring the Indiana (P9546), North Carolina (P9492) and Michigan (P12604) marker programs.
   Until they exist, the state id is stored as an alias (e.g. `ID-13`, `MT-1`).
2. Create program items ("Idaho Highway Historical Marker Program", "Montana historical highway marker
   system") and add `part of` (P361) on each sign.
3. Link Wikimedia Commons photos (P18) and HMdb IDs (P7883, 454 items worldwide already use it).
4. Write the QIDs back into `wikidata_qid` in this dataset.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: the site's "Fix this entry" / "Add a missing marker" links
file structured GitHub issues; label one `accepted` and the monthly rebuild merges it. Adding a state is one JSON
file ([docs/adding-a-state.md](docs/adding-a-state.md)).

## Roadmap

- Wikidata nearest-neighbor join → Wikipedia article + Commons photo per marker
- Photo upload + OCR queue for the Montana texts
- "Approaching marker" mode: watch position, read the sign aloud via Web Speech (the Read aloud button already exists)
- More states: any DOT/SHPO with an ArcGIS feature service that has a text field drops in with ~40 lines

## Licenses

- Code: MIT (see `LICENSE`)
- Compiled dataset: CC BY 4.0 (see `DATA_LICENSE`) — attribute "Roadside contributors"
- Marker texts remain © their issuing agency (Montana DOT; Idaho Transportation Department / Idaho State
  Historical Society) and are reproduced here as published public information. Each record names its source.
- Basemap: OpenFreeMap / OpenMapTiles / © OpenStreetMap contributors
