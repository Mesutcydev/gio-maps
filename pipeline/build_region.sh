#!/bin/sh
# Build one offline region pack into OUT_DIR:
#   basemap.pmtiles, valhalla_tiles.tar, places.sqlite, pack.json
#
# Usage (from the repo root):
#   pipeline/build_region.sh pipeline/regions/istanbul.json OUT_DIR
#
# Needs: curl, osmium (osmium-tool), pmtiles, docker, python3, sudo.
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 REGION_JSON OUT_DIR" >&2
  exit 2
fi
REGION_JSON=$1
OUT_DIR=$2
HERE=$(cd "$(dirname "$0")" && pwd)

jget() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$REGION_JSON" "$1"
}

ID=$(jget id)
PBF=$(jget pbf)
CLIP=$(jget clip)          # prints True or False
MAXZOOM=$(jget maxzoom)
BBOX=$(python3 -c 'import json,sys; print(",".join(map(str, json.load(open(sys.argv[1], encoding="utf-8"))["bbox"])))' "$REGION_JSON")
VERSION=$(date -u +%Y%m%d)
echo "== building $ID $VERSION"

mkdir -p "$OUT_DIR"
OUT=$(cd "$OUT_DIR" && pwd)   # absolute, so docker -v gets a real path
WORK="$OUT/work"
mkdir -p "$WORK"

echo "== source extract"
curl -fL --retry 3 -o "$WORK/source.osm.pbf" "$PBF"
if [ "$CLIP" = True ]; then
  osmium extract -b "$BBOX" --strategy=smart --overwrite -o "$WORK/region.osm.pbf" "$WORK/source.osm.pbf"
else
  mv "$WORK/source.osm.pbf" "$WORK/region.osm.pbf"
fi

echo "== basemap"
KEY=$(curl -fsS https://build-metadata.protomaps.dev/builds.json | python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["key"])')
echo "protomaps build: $KEY"
pmtiles extract "https://build.protomaps.com/$KEY" "$OUT/basemap.pmtiles" --bbox="$BBOX" --maxzoom="$MAXZOOM"

echo "== routing tiles"
mkdir -p "$WORK/valhalla"
cp "$WORK/region.osm.pbf" "$WORK/valhalla/"
docker run --rm -v "$WORK/valhalla:/custom_files" \
  -e serve_tiles=False -e build_tar=True -e build_elevation=False \
  -e build_admins=True -e build_time_zones=True -e use_tiles_ignore_pbf=False \
  ghcr.io/valhalla/valhalla-scripted:latest
# The container runs as root, so its output must be handed back before cleanup.
sudo chown -R "$(id -u)" "$WORK/valhalla" 2>/dev/null || true
if [ ! -f "$WORK/valhalla/valhalla_tiles.tar" ]; then
  echo "valhalla_tiles.tar was not produced" >&2
  exit 1
fi
mv "$WORK/valhalla/valhalla_tiles.tar" "$OUT/"

echo "== places"
osmium tags-filter "$WORK/region.osm.pbf" \
  nwr/amenity nwr/shop nwr/tourism nwr/leisure nwr/office nwr/healthcare nwr/historic \
  n/place w/highway nwr/railway=station,halt,tram_stop nwr/public_transport=station \
  nwr/aeroway=aerodrome,terminal \
  -o "$WORK/places.osm.pbf" --overwrite
osmium export "$WORK/places.osm.pbf" -f geojsonseq -u type_id -o "$WORK/places.geojsonseq" --overwrite
python3 "$HERE/places.py" "$WORK/places.geojsonseq" "$OUT/places.sqlite"

echo "== pack.json"
python3 - "$REGION_JSON" "$OUT" "$VERSION" <<'EOF'
import hashlib, json, os, sys

region_json, out, version = sys.argv[1:4]
with open(region_json, encoding="utf-8") as f:
    region = json.load(f)
files = []
for name in ("basemap.pmtiles", "valhalla_tiles.tar", "places.sqlite"):
    path = os.path.join(out, name)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    files.append({"name": name, "bytes": os.path.getsize(path), "sha256": digest.hexdigest()})
pack = {
    "id": region["id"],
    "name": region["name"],
    "version": version,
    "bbox": region["bbox"],
    "attribution": "© OpenStreetMap contributors",
    "files": files,
}
with open(os.path.join(out, "pack.json"), "w", encoding="utf-8") as f:
    json.dump(pack, f, ensure_ascii=False, indent=2)
    f.write("\n")
EOF

rm -rf "$WORK"
ls -la "$OUT"
