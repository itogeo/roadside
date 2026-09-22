# Adding a state

Roadside only uses **official** sources: the state DOT, historical society, or SHPO that runs the marker program.
That keeps the rights clean and lets us say every record is what the state itself published.

## 1. Find the data

Try, in order:

1. Search ArcGIS Online: `https://www.arcgis.com/sharing/rest/search?q=historical%20markers%20<State>&f=json`
   — look for a `Feature Service` owned by a `.gov` org.
2. The state DOT's open-data hub (`gis-<dot>.opendata.arcgis.com` or `data.<state>.gov`).
3. The state historical society's site — many have a marker "guide" PDF even when there's no service.
4. Ask. A one-line email to the marker program coordinator usually gets a shapefile.

Good signs: a field with the full inscription, a status field, route/milepost. If there's no text field, still add
the state — locations and titles are useful, and `text_status: pending` tells us where to follow up.

## 2. Describe it in one file

Copy `pipeline/sources/template.json.example` to `pipeline/sources/<xx>.json` and map the fields.
Only `state`, `agency`, `url`, `fields.id`, and `fields.title` are required. Run `python pipeline/build.py`
and check `data/build_report.json` for your state's counts.

## 3. Roads for the basemap

`python pipeline/build_basemap.py` automatically adds US/state highways for every state present in the dataset.
It costs about 1 MB per state.

## 4. Open a PR

Include the source URL and whatever the agency's site says about reuse in the PR description. That's it.

If the state's data needs real scraping (like Montana's geologic-marker text), add a function in `build.py`
following `build_montana()` and mention it in the PR.
