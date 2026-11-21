#!/usr/bin/env python3
"""Convert an OSM GeoJSON sequence (osmium export -f geojsonseq) into a POI
sqlite database with an FTS5 index (Turkish keywords, diacritics removed).

Usage:
  places.py PLACES.geojsonseq OUT.sqlite
  places.py --selftest
"""
import json
import sqlite3
import sys

CATEGORY_KEYS = [
    "amenity", "shop", "tourism", "healthcare", "leisure", "office", "historic",
    "railway", "public_transport", "aeroway", "place", "highway",
]
STREET_VALUES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "pedestrian",
}
KEYWORDS = {
    "pharmacy": "eczane",
    "fuel": "benzinlik akaryakıt benzin istasyonu",
    "hospital": "hastane",
    "clinic": "klinik sağlık",
    "doctors": "doktor",
    "dentist": "diş hekimi",
    "restaurant": "restoran lokanta yemek",
    "cafe": "kafe kahve",
    "fast_food": "fast food",
    "bar": "bar",
    "pub": "bar",
    "bank": "banka",
    "atm": "atm bankamatik",
    "parking": "otopark",
    "supermarket": "market süpermarket",
    "convenience": "market bakkal",
    "bakery": "fırın",
    "place_of_worship": "cami ibadethane",
    "school": "okul",
    "university": "üniversite",
    "hotel": "otel",
    "hostel": "hostel pansiyon",
    "police": "polis karakol",
    "fire_station": "itfaiye",
    "post_office": "postane ptt",
    "toilets": "tuvalet wc",
    "charging_station": "şarj istasyonu",
    "car_repair": "oto tamir sanayi",
    "car_wash": "oto yıkama",
    "museum": "müze",
    "attraction": "turistik yer",
    "viewpoint": "manzara seyir",
    "park": "park",
    "station": "istasyon tren metro",
    "tram_stop": "tramvay durağı",
    "aerodrome": "havalimanı havaalanı",
    "bus_station": "otogar terminal",
    "ferry_terminal": "iskele vapur",
    "marketplace": "pazar",
    "mall": "avm alışveriş merkezi",
    "city": "şehir",
    "town": "ilçe",
    "village": "köy",
    "suburb": "semt mahalle",
    "neighbourhood": "mahalle",
    "street": "sokak cadde",
}

SCHEMA = """
CREATE TABLE poi(id INTEGER PRIMARY KEY, name TEXT NOT NULL, alt_names TEXT, category TEXT NOT NULL, keywords TEXT, addr TEXT, lat REAL NOT NULL, lon REAL NOT NULL);
CREATE INDEX poi_lat ON poi(lat);
CREATE VIRTUAL TABLE poi_fts USING fts5(name, alt_names, keywords, addr, content='poi', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
"""
INSERT = "INSERT INTO poi(name, alt_names, category, keywords, addr, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)"
BATCH_SIZE = 5000
TR_FOLD = str.maketrans("ıİğĞşŞçÇöÖüÜâÂîÎûÛ", "iIgGsScCoOuUaAiIuU")


def iter_features(lines):
    for line in lines:
        line = line.strip("\x1e \t\r\n")
        if line:
            yield json.loads(line)


def _mean(ring):
    if not ring:
        return None
    n = len(ring)
    return [sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n]


def representative_point(geom):
    kind, coords = geom.get("type"), geom.get("coordinates")
    if kind == "Point":
        return coords
    if kind == "LineString" and coords:
        return coords[len(coords) // 2]
    if kind == "Polygon" and coords:
        return _mean(coords[0])
    if kind == "MultiPolygon" and coords and coords[0]:
        return _mean(coords[0][0])
    return None


def classify(props):
    """Category string for a feature, or None if it is not a POI."""
    for key in CATEGORY_KEYS:
        value = props.get(key)
        if value:
            if key == "highway":
                return "street" if value in STREET_VALUES else None
            return value
    return None


def address(props):
    street = " ".join(p for p in (props.get("addr:street"), props.get("addr:housenumber")) if p)
    area = props.get("addr:district") or props.get("addr:city") or ""
    return f"{street}, {area}".strip(" ,")


def poi_row(feature):
    props = feature.get("properties") or {}
    name = (props.get("name") or "").strip()
    category = classify(props)
    if not name or category is None:
        return None
    point = representative_point(feature.get("geometry") or {})
    if not point:
        return None
    lon, lat = round(float(point[0]), 6), round(float(point[1]), 6)
    # FTS unicode61 strips ş/ö/ü/ç/ğ diacritics but keeps ı distinct, so "kadikoy" would miss "Kadıköy":
    # index an ASCII-folded copy of the name too.
    folded = name.translate(TR_FOLD).lower()
    alt_names = " ".join(v for v in (props.get("name:en"), props.get("alt_name"), folded) if v)
    return (name, alt_names, category, KEYWORDS.get(category, ""), address(props), lat, lon)


def build(features, conn):
    """Insert POIs from GeoJSON feature dicts into conn and rebuild the FTS index.
    Returns {category: count}."""
    conn.executescript(SCHEMA)
    counts = {}
    seen_streets = set()
    batch = []
    for feature in features:
        row = poi_row(feature)
        if row is None:
            continue
        category = row[2]
        if category == "street":
            key = (row[0], round(row[5], 2), round(row[6], 2))
            if key in seen_streets:
                continue
            seen_streets.add(key)
        batch.append(row)
        counts[category] = counts.get(category, 0) + 1
        if len(batch) >= BATCH_SIZE:
            conn.executemany(INSERT, batch)
            batch.clear()
    conn.executemany(INSERT, batch)
    conn.commit()
    conn.execute("INSERT INTO poi_fts(poi_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO poi_fts(poi_fts) VALUES('optimize')")
    conn.commit()
    return counts


def report(counts):
    print(f"{sum(counts.values())} POIs")
    for category, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {category}: {n}")


def main(src, dst):
    with open(dst, "wb"):  # truncate a stale db so a rerun does not hit "table exists"
        pass
    conn = sqlite3.connect(dst)
    with open(src, encoding="utf-8") as f:
        counts = build(iter_features(f), conn)
    conn.execute("VACUUM")
    conn.close()
    report(counts)


def selftest():
    lines = [
        '\x1e{"type":"Feature","properties":{"name":"Merkez Eczanesi","amenity":"pharmacy"},"geometry":{"type":"Point","coordinates":[28.97,41.01]}}\n',
        '\x1e{"type":"Feature","properties":{"name":"İstiklal Caddesi","highway":"residential"},"geometry":{"type":"LineString","coordinates":[[28.97,41.03],[28.98,41.035],[28.99,41.04]]}}\n',
        '\x1e{"type":"Feature","properties":{"name":"Çınar Kafe","amenity":"cafe"},"geometry":{"type":"Polygon","coordinates":[[[28.9,41.0],[28.91,41.0],[28.91,41.01],[28.9,41.01],[28.9,41.0]]]}}\n',
    ]
    conn = sqlite3.connect(":memory:")
    counts = build(iter_features(lines), conn)
    assert counts == {"pharmacy": 1, "street": 1, "cafe": 1}, counts
    for term, expected in [("eczane", "Merkez Eczanesi"), ("istiklal", "İstiklal Caddesi"), ("kahve", "Çınar Kafe"),
                           ("cinar", "Çınar Kafe")]:
        rows = conn.execute(
            "SELECT poi.name FROM poi JOIN poi_fts ON poi.id = poi_fts.rowid WHERE poi_fts MATCH ?",
            (term,),
        ).fetchall()
        assert rows == [(expected,)], (term, rows)
    print("selftest ok")


if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] == "--selftest":
    selftest()
elif __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
