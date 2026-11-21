#!/usr/bin/env python3
"""Write catalog.json from this repo's pack releases.

Each pack release is tagged <id>-<yyyymmdd> and carries a pack.json. The newest version of each id wins.
Output: {"packs": [{"id", "name", "version", "bytes", "path", "bbox"}]}, read by the app's download manager at
https://github.com/<repo>/releases/download/catalog/catalog.json. Needs the gh CLI with GH_TOKEN.
"""
import json
import re
import subprocess
import sys

repo, out = sys.argv[1], sys.argv[2]
tags = subprocess.run(["gh", "release", "list", "-R", repo, "--limit", "500", "--json", "tagName", "-q", ".[].tagName"],
                      check=True, capture_output=True, text=True).stdout.split()
latest = {}
for tag in tags:
    match = re.fullmatch(r"([a-z0-9]+)-(\d{8})", tag)
    if match and match[2] > latest.get(match[1], ("", ""))[0]:
        latest[match[1]] = (match[2], tag)

packs = []
for pack_id, (version, tag) in sorted(latest.items()):
    raw = subprocess.run(["gh", "release", "download", tag, "-R", repo, "-p", "pack.json", "-O", "-"],
                         check=True, capture_output=True, text=True).stdout
    manifest = json.loads(raw)
    packs.append({"id": pack_id, "name": manifest["name"], "version": version, "path": tag,
                  "bytes": sum(f["bytes"] for f in manifest["files"]), "bbox": manifest["bbox"]})

with open(out, "w", encoding="utf-8") as f:
    json.dump({"packs": packs}, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"{len(packs)} packs in catalog")
