#!/usr/bin/env python3
"""
Roadside — attach MDT's own photographs of the Montana signs.

Montana's marker text is not missing. MDT photographed the signs and serves the JPEGs as ArcGIS
feature-service attachments; 341 of 356 markers have at least one, and 283 of the 297 markers with
no transcribed text have one. The photographs are close enough to read.

That matters more than any transcription: showing the photograph IS the sign's exact wording, with
no transcription step to get wrong. Text remains useful for search; the photo is the evidence.

Which photo
-----------
Markers carry up to three, named "Photo 1/2/3.jpg". MDT's convention is consistent across every
marker checked: Photo 1 is the close-up you can read, Photo 2 is the wider setting, Photo 3 is the
view the sign looks out on. So: lowest photo number wins, falling back to the largest file if the
names don't carry numbers.

Hotlinked, not copied. The service sends `access-control-allow-origin` and the originals are 3-5 MB,
so the site lazy-loads them only when a marker's panel is opened. Nothing is stored in this repo,
which also means no question about redistributing MDT's photographs — the browser fetches them from
MDT, the same as following a link.

Usage:  python pipeline/sign_photos.py            # refresh the index and stamp markers.geojson
        python pipeline/sign_photos.py --smoke    # offline self-test
"""
from __future__ import annotations
import json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "site" / "data"
INDEX = DATA / "sign_photos.json"
UA = {"User-Agent": "Roadside/0.1 (open-source roadside marker map; https://github.com/itogeo/roadside)"}

MDT_LAYER = ("https://gis.mtmdt.us/server/rest/services/MDTGIS/"
             "Historical_Highway_Marker/MapServer/0")
CREDIT = "Montana Department of Transportation"
# MDT publishes no explicit reuse licence for these photographs; the service's copyrightText is just
# the agency name. We hotlink rather than copy, and say plainly whose photograph it is.
LICENSE = "© Montana Department of Transportation — hotlinked from the MDT feature service"

BATCH = 50


def fetch(url: str, retries: int = 3) -> bytes:
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            print(f"    retry {i+1}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def photo_rank(info: dict) -> tuple[int, int]:
    """Sort key: lowest photo number first; ties (and unnumbered names) fall back to largest file."""
    m = re.search(r"(\d+)", info.get("name") or "")
    return (int(m.group(1)) if m else 99, -int(info.get("size") or 0))


def best_photo(infos: list[dict]) -> dict | None:
    images = [a for a in infos if str(a.get("contentType", "")).startswith("image/")]
    return sorted(images, key=photo_rank)[0] if images else None


def attachment_url(object_id: int | str, attachment_id: int | str) -> str:
    return f"{MDT_LAYER}/{object_id}/attachments/{attachment_id}"


def build_index() -> dict:
    """{ '<OBJECTID>': {url, name, size, count} } for every Montana marker that has a photograph."""
    ids = json.loads(fetch(MDT_LAYER + "/query?where=1%3D1&returnIdsOnly=true&f=json"))["objectIds"]
    print(f"MT: {len(ids)} markers in the MDT layer")
    index: dict[str, dict] = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        url = f"{MDT_LAYER}/queryAttachments?objectIds={','.join(map(str, chunk))}&f=json"
        for group in json.loads(fetch(url)).get("attachmentGroups", []):
            oid = group.get("parentObjectId")
            infos = group.get("attachmentInfos") or []
            pick = best_photo(infos)
            if not pick:
                continue
            index[str(oid)] = {
                "url": attachment_url(oid, pick["id"]),
                "name": pick.get("name"),
                "size": pick.get("size"),
                "count": len(infos),
            }
        print(f"  {min(i + BATCH, len(ids))}/{len(ids)}", end="\r")
        time.sleep(0.5)
    print()
    print(f"MT: {len(index)} markers have a photograph ({100*len(index)/max(len(ids),1):.0f}%)")
    return index


def stamp(index: dict) -> tuple[int, int]:
    """Write image_url/credit/licence onto the Montana features of markers.geojson (both copies)."""
    path = DATA / "markers.geojson"
    gj = json.loads(path.read_text())
    stamped = had_text = 0
    for f in gj["features"]:
        p = f["properties"]
        if p.get("state") != "MT":
            continue
        rec = index.get(str(p.get("source_id")))
        if not rec:
            continue
        p["image_url"] = rec["url"]
        p["image_credit"] = CREDIT
        p["image_license"] = LICENSE
        p["image_count"] = rec["count"]
        stamped += 1
        if (p.get("text") or "").strip():
            had_text += 1
    out = json.dumps(gj, ensure_ascii=False, separators=(",", ":"))
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    for dest in (path, SITE_DATA / "markers.geojson"):
        dest.write_text(out)
    return stamped, stamped - had_text


def _smoke() -> int:
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, want {want!r}")

    infos = [{"id": 712, "name": "Photo 2.jpg", "size": 4_100_000, "contentType": "image/jpeg"},
             {"id": 713, "name": "Photo 1.jpg", "size": 3_800_000, "contentType": "image/jpeg"},
             {"id": 714, "name": "Photo 3.jpg", "size": 5_900_000, "contentType": "image/jpeg"}]
    check("picks the close-up, not the biggest file", best_photo(infos)["id"], 713)
    check("order in the list is irrelevant", best_photo(list(reversed(infos)))["id"], 713)
    check("unnumbered names fall back to largest",
          best_photo([{"id": 1, "name": "a.jpg", "size": 10, "contentType": "image/jpeg"},
                      {"id": 2, "name": "b.jpg", "size": 99, "contentType": "image/jpeg"}])["id"], 2)
    check("non-images ignored",
          best_photo([{"id": 9, "name": "notes.pdf", "size": 10, "contentType": "application/pdf"}]), None)
    check("no attachments -> None", best_photo([]), None)
    check("url shape", attachment_url(3, 713), MDT_LAYER + "/3/attachments/713")
    for f in fails:
        print("  FAIL", f)
    print(f"smoke: {'all checks passed' if not fails else str(len(fails)) + ' FAILED'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if "--smoke" in argv:
        return _smoke()
    if "--reuse" in argv and INDEX.exists():
        index = json.loads(INDEX.read_text())["photos"]
        print(f"using cached index: {len(index)} markers")
    else:
        index = build_index()
        INDEX.write_text(json.dumps(
            {"source": MDT_LAYER, "credit": CREDIT, "license": LICENSE,
             "generated": time.strftime("%Y-%m-%d"), "photos": index}, indent=2))
    total, newly_readable = stamp(index)
    print(f"\n→ data/sign_photos.json  {len(index)} photographs indexed")
    print(f"→ markers.geojson        {total} Montana markers now carry a sign photo")
    print(f"                         {newly_readable} of them had no transcribed text — "
          f"those signs become readable for the first time")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
