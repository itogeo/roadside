One JSON file per state whose data comes from a plain ArcGIS feature service. build.py loads every *.json here
through the generic adapter; Montana and Idaho are hand-coded in build.py only because Montana needs a scraper
for its text. Copy template.json.example, fill it in, delete the fields you don't have. See docs/adding-a-state.md.
