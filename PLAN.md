# Roadside — Plan

**Live:** https://itogeo.github.io/roadside/ (GitHub Pages, deployed by `.github/workflows/pages.yml`)
**Repo:** https://github.com/itogeo/roadside
**Goal:** a free, open-source map of official roadside historical + geological markers, with the sign
text where a state publishes it, usable from anywhere and offline via GPX/KML.

_Last updated: 2026-09-22_

## Where it stands

Live and working, two states. Verified on the deployed site: page, `markers.geojson`, both PMTiles
(HTTP 206 range requests confirmed — PMTiles needs them and GitHub Pages does serve them), glyph
fonts, and the GPX/KML downloads all return 200.

| | Markers | Standing | With sign text |
|---|---|---|---|
| Montana | 356 | 356 | 59 |
| Idaho | 317 | 281 | 316 |
| **Total** | **673** | **637** | **375** |

## The real gap: Montana sign text

83% of Montana markers show a title and nothing else. This is not an engineering problem — MDT's
`Historical_Highway_Marker` feature service has **no text field at all** (schema checked 2026-09-22:
SIGN_SIZE, LATITUDE, LONGITUDE, TITLE, TRAVEL_DIR, CAMPING_ACCESS, MARKER_TYPE, SIGN_TYPE, OWNERSHIP,
STATUS, MATERIAL). The 59 we have come from scraping the geologic-series web page.

Routes to the remaining ~297, in order of expected yield:
1. Ask Montana Historical Society directly for the marker texts as data. They hold them
   (*Montana's Historical Highway Markers*). A state agency releasing text for a free public map is
   a reasonable ask and costs nothing to make.
2. Robert Fletcher's 1938 *Montana Highway Historical Markers* may be public domain — US works
   1930–1963 needed renewal. Check the Stanford Copyright Renewal Database before transcribing.
3. Community transcription through the `add-marker` / `fix-marker` issue forms, folded in by
   `ingest_issues.py` on the monthly rebuild.

Ruled out: OpenStreetMap. Only 22 of 419 Montana marker nodes carry `inscription` (checked via
Overpass 2026-09-22), so OSM adds markers but not text.

## Next

- [ ] **OpenStreetMap as a second source** (agreed 2026-09-22). Adds markers no state DOT
      publishes — city, county, museum, trail boards — and gives nationwide coverage immediately
      rather than state by state. MT: 419 OSM nodes vs our 356. VA: 682.
      Licensing needs deciding first: OSM is ODbL (attribution + share-alike), which does not
      compose cleanly with the current "compilation CC BY 4.0" line. Either keep OSM-derived
      records in a separately-licensed layer or move the compilation to ODbL. Decide before writing
      the adapter, not after.
- [ ] **State sweep.** For each state, find the official ArcGIS feature service and write
      `pipeline/sources/<xx>.json` (the generic adapter already reads every file in that directory;
      `sources/` currently holds only the README and template). Flag states that publish only PDFs
      or nothing — those become outreach.
- [ ] **Custom domain.** Native to Pages: a `CNAME` file in `site/` plus one DNS record at the
      registrar. Confirm the hostname first — `roadside.itugsbishop.com` was typed once and looks
      like a typo. Adding the file before the DNS record exists breaks the github.io URL.
- [ ] **Basemap rebuild on state change.** Wired into `rebuild.yml`, but the committed
      `site/tiles/basemap.pmtiles` still predates the city-label dedup fix, so Boise and Butte
      label twice until it is regenerated:
      `python pipeline/build_basemap.py` (~120 MB of Census/TIGER downloads, cached after the first run).

## Notes for a future maintainer

- `pages.yml` needs `configure-pages` with `enablement: true`, and even then the workflow token
  cannot create the Pages site on a repo where Pages has never been on — that took a one-off
  `gh api -X POST repos/itogeo/roadside/pages -f build_type=workflow` as a repo admin.
- Census and Natural Earth disagree on legal city names. `build_basemap.py` dedupes by location
  plus a name matcher for exactly this reason; see `same_place()`.
- The site is static with no build step. `pipeline/serve.py` exists because
  `python -m http.server` has no Range support and PMTiles will not load without it.
