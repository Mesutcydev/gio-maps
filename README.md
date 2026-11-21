# Gio

Gio is an offline map and navigation app for iPhone with an on-device AI assistant. Maps, turn-by-turn
routing, place search and the assistant all run on the phone, with no account and no connection needed.

This repository hosts Gio's downloadable offline region packs and the pipeline that builds them.

## Support

Questions, bugs or a city you'd like added: [open an issue](https://github.com/Mesutcydev/gio-maps/issues).

Privacy: see [PRIVACY.md](PRIVACY.md).

## Region packs

Each pack is a GitHub release tagged `<region>-<yyyymmdd>` with four files: `basemap.pmtiles` (Protomaps vector
tiles), `valhalla_tiles.tar` (routing graph), `places.sqlite` (search index) and `pack.json` (versions, sizes,
SHA-256 checksums). The app verifies every file before installing it. The `catalog` release holds
`catalog.json`, the index the app reads.

Regions live in [`regions/`](regions): Türkiye and its cities (İstanbul, Ankara, İzmir, Antalya, Bursa,
Kapadokya, Trabzon, Bodrum, Konya) and world cities (London, Paris, Berlin, Rome, Barcelona, Amsterdam, Lisbon,
Athens, New York, Tokyo, Dubai, Seoul) and Egypt (all of Egypt, Cairo).

To build: Actions › Build region packs › Run workflow, with region ids (`istanbul,ankara`) or `all`.

## Data and licences

Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open
Database License (ODbL). Basemap tiles are extracted from [Protomaps](https://protomaps.com) builds; routing uses
[Valhalla](https://github.com/valhalla/valhalla). Source extracts come from Geofabrik and BBBike.
