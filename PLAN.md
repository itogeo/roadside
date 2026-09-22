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

| | Markers | Standing | With sign text | With sign photo | **Readable** |
|---|---|---|---|---|---|
| Montana | 356 | 356 | 59 | 340 | **341 (96%)** |
| Idaho | 317 | 281 | 316 | — | **316 (>99%)** |
| **Total** | **673** | **637** | **375** | **340** | **657 (98%)** |

"Readable" = you can read what the sign says, from text or photograph.

## Montana sign text — solved by photograph (2026-09-22)

83% of Montana markers show a title and nothing else. This is not an engineering problem — MDT's
`Historical_Highway_Marker` feature service has **no text field at all** (schema checked 2026-09-22:
SIGN_SIZE, LATITUDE, LONGITUDE, TITLE, TRAVEL_DIR, CAMPING_ACCESS, MARKER_TYPE, SIGN_TYPE, OWNERSHIP,
STATUS, MATERIAL). The 59 we have come from scraping the geologic-series web page.

**MDT has already published the answer as photographs.** The same ArcGIS layer exposes JPEG
attachments (`hasAttachments: true`), and they are photographs of the signs themselves, taken close
enough that the full text reads cleanly. Surveyed 2026-09-22:

| | |
|---|---|
| MT markers with ≥1 photo | **341 / 356 (96%)** |
| Of the 297 markers with no text, how many have a photo | **283 (95%)** |
| Photo files total | 895, 2.90 GB (avg 3.2 MB, typically 3264×2448) |
| CORS | open — `access-control-allow-origin` echoes the request origin, so the site may hotlink directly, no key |
| `copyrightText` on the service | "Montana Department of Transportation" — no explicit reuse licence published |

Endpoint shape: `.../MapServer/0/{objectId}/attachments` lists them,
`.../MapServer/0/{objectId}/attachments/{id}` returns the JPEG. `queryAttachments?objectIds=…`
batches up to ~50 at a time.

This reframes the problem. The Montana sign text is not unpublished — it is published as pixels.
Two consequences:

1. **Showing the photo satisfies "exactly what the sign says" with zero transcription risk**, which
   no text pipeline can claim. This is the strongest version of the product: you read the actual sign.
2. Transcription (OCR or otherwise) becomes an *optional* searchability layer on top, and any
   transcription must be marked as such and displayed next to the photo that evidences it — never
   promoted to `text_status: "official"`.

Sizing, measured on a real marker photo (legibility confirmed by eye at each size):

| Width | Per photo | × 341 markers |
|---|---|---|
| 1000 px JPEG q72 | 139 KB | 46 MB |
| 1280 px JPEG q72 | 215 KB | 72 MB |
| 1280 px WebP q78 | 200 KB | **67 MB** |
| 1600 px WebP q78 | 286 KB | 95 MB |

1280 px is legible and is the recommended cache size. Hotlinking the 3 MB originals is the
zero-storage option but is the wrong call for a site whose whole point is roadside use on a weak
signal. **Built and live** — `pipeline/sign_photos.py`, hotlinked rather than cached. The service sends
permissive CORS, nothing is stored in this repo, and the browser fetches from MDT exactly as it
would by following a link, so no question of redistributing MDT's photographs arises. Photos are
lazy-loaded, so a 3-5 MB original is only fetched when someone opens that marker.

Still open: MDT publishes no explicit reuse licence (the service's `copyrightText` is just the
agency name), so the caption credits them by name. Worth confirming with MDT. If the originals ever
prove too heavy in practice, the measured fallback is a 1280 px WebP cache at ~200 KB each, ~67 MB
for all 341 — but that reopens the redistribution question that hotlinking avoids.

Other text routes, now secondary:
1. Ask Montana Historical Society for the marker texts as data (they hold
   *Montana's Historical Highway Markers*). Still worth doing — it would give attested text.
2. Robert Fletcher's 1938 *Montana Highway Historical Markers* may be public domain — US works
   1930–1963 needed renewal. Check the Stanford Copyright Renewal Database before transcribing.
3. Community transcription through the `add-marker` / `fix-marker` issue forms, folded in by
   `ingest_issues.py` on the monthly rebuild — now much easier, since a transcriber can work from
   the photo rather than having to drive to the sign.

Ruled out as a text source: OpenStreetMap. Only 22 of 419 Montana marker nodes carry `inscription`,
and most of those are short fragments (a name or a date), not the sign's wording.

Ruled out as an image source: Wikimedia Commons has 4 files in `Category:Historical markers in
Montana` and 0 in the Idaho category — not viable here, though Virginia has 165 for later. OSM's one
Montana `image` tag points at hmdb.org, which is copyrighted.

Idaho needs none of this: ITD already publishes `MainText` for 316 of 317. Its layer reports
`hasAttachments: true` but every attachment list comes back empty.

## Next

- [x] **OpenStreetMap adapter** — `pipeline/osm_markers.py`, built 2026-09-22. Writes
      `data/osm_markers.geojson` + `data/osm_report.json`. Run `--smoke` for an offline self-test
      of the text rules; raw extracts are cached under `data/osm_cache/` so a rebuild neither
      re-hammers Overpass nor breaks when Overpass 504s (it did, twice, during development).

      First run: **178 markers added** (MT 126, ID 52) beyond the official feeds, with 38 correctly
      dropped as duplicates of markers the states already publish. Only 17 carry sign text.

      The value here is breadth, not text — markers no DOT publishes: the Anaconda Smelter Stack,
      Whoop-Up Trail Monument, Blackfeet Nation markers, county and museum plaques.

- [ ] **Decide the licence, then merge the OSM layer into `markers.geojson`.** The adapter
      deliberately writes a *separate* file and is not wired into `build.py`, because merging is the
      licensing decision, not an engineering one. OSM is ODbL: attribution **and share-alike**. The
      compilation currently says CC BY 4.0. Options: (a) move the whole compilation to ODbL —
      simplest to explain, most in the spirit of the project; (b) keep OSM as a separate,
      separately-licensed layer the site loads alongside. Until this is settled every OSM record
      carries its own `license: "ODbL 1.0"` field so nothing is silently relicensed.
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

## The verbatim rule

`text` must be **exactly what the sign says**. This is the project's one non-negotiable, and it
drives real code:

- OSM's `inscription` (words ON the object) is eligible. `description` (a note ABOUT the object) is
  never used as text, and `name` is a title only.
- Even `inscription` is an unattested volunteer transcription, so it lands as
  `text_status: "community"` with the OSM node id **and version**, never `"official"`.
- Inscriptions under 60 characters are rejected — on a plaque that is a name or a date, not wording.
- Inscriptions that describe the sign instead of quoting it are rejected. This is not hypothetical:
  a Park City node had *"This plague, located just in front of the Park City Kwik Stop, tells the
  story of…"* sitting in its `inscription` tag. `looks_like_description()` catches that shape.
- Every rejection is recorded on the feature in `text_rejected`, so the judgement is auditable
  rather than invisible.

When in doubt the adapter rejects. A missing transcription is recoverable; a wrong one presented as
the sign's words is the one failure this project cannot afford.

## Notes for a future maintainer

- `pages.yml` needs `configure-pages` with `enablement: true`, and even then the workflow token
  cannot create the Pages site on a repo where Pages has never been on — that took a one-off
  `gh api -X POST repos/itogeo/roadside/pages -f build_type=workflow` as a repo admin.
- Census and Natural Earth disagree on legal city names. `build_basemap.py` dedupes by location
  plus a name matcher for exactly this reason; see `same_place()`.
- The site is static with no build step. `pipeline/serve.py` exists because
  `python -m http.server` has no Range support and PMTiles will not load without it.
