#!/usr/bin/env python3
"""
Turn GitHub issues filed through the site's "Add a missing marker" / "Fix this entry" forms into
data/contributions/<issue>.json, which build.py merges on top of the state sources.

Only issues carrying the `accepted` label are ingested — a maintainer adds that label after a glance,
so a stranger can't rewrite the dataset by filing an issue. Closed issues are skipped.

Env: GITHUB_TOKEN (any token that can read issues), REPO (owner/name)
"""
from __future__ import annotations
import json, os, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions"
REPO = os.environ.get("REPO"); TOKEN = os.environ.get("GITHUB_TOKEN")
if not REPO:
    sys.exit("set REPO=owner/name")


def gh(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    return json.load(urllib.request.urlopen(req))


def fields(body: str) -> dict:
    """Issue-form bodies render as '### Label\\n\\nvalue' blocks; parse them back into a dict."""
    out = {}
    for m in re.finditer(r"### (.+?)\n\n(.*?)(?=\n### |\Z)", body or "", re.S):
        v = m.group(2).strip()
        out[m.group(1).strip().lower()] = "" if v in ("_No response_", "None") else v
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    issues = gh(f"https://api.github.com/repos/{REPO}/issues?labels=marker,accepted&state=open&per_page=100")
    n = 0
    for it in issues:
        if "pull_request" in it: continue
        f = fields(it["body"]); labels = {l["name"] for l in it["labels"]}
        rec = {"issue": it["number"], "url": it["html_url"], "kind": "fix" if "fix" in labels else "add"}
        if m := re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", f.get("coordinates", "") + " " + f.get("coordinates on record", "")):
            rec["lat"], rec["lon"] = float(m.group(1)), float(m.group(2))
        for k, v in (("marker id", "id"), ("marker title", "title"), ("state", "state"), ("sign text", "text"),
                     ("correction", "correction"), ("what's wrong", "what"), ("photo link", "image_url"), ("anything else", "notes"), ("notes", "notes")):
            if f.get(k): rec[v] = f[k]
        (OUT / f"{it['number']}.json").write_text(json.dumps(rec, indent=2)); n += 1
    print(f"{n} accepted contributions → {OUT}")


if __name__ == "__main__":
    main()
