"""Count the people and households inside each S&WB boil-water advisory area.

    python -m collectors.households            # update data/water/swbno/advisory_counts.json
    python -m collectors.households --dry-run  # compute and print a summary, write nothing

Method: a 2020 Census block counts toward an advisory when the block's
interior point falls inside the advisory polygon. Counts come from the 2020
Census (people, housing units, occupied housing units).

Advisory areas smaller than a block (a few street segments) contain no
interior points. For those, every block the area touches is counted and the
result is marked as an upper bound.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import common
from .common import fetch_json, from_epoch_ms, iso, read_json, short_hash, write_json
from .power import FeedError

STATE, COUNTY = "22", "071"  # Orleans Parish, Louisiana
TIGER_BLOCKS = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/2/query"
CENSUS_DHC = "https://api.census.gov/data/2020/dec/dhc"
SMALL_AREA_PEOPLE = 100  # below this, also count touching blocks


def load_blocks():
    """Orleans Parish blocks: [{geoid, lat, lon, people, units, occupied}], cached in the repo."""
    path = common.DATA / "census" / f"blocks-{STATE}{COUNTY}.json"
    key = os.environ.get("CENSUS_API_KEY")
    cached = read_json(path, None)
    # Reuse the saved table, unless a key has since been added and it lacks occupancy.
    if cached and (cached.get("has_occupied") or not key):
        return cached["blocks"]
    points = fetch_json(TIGER_BLOCKS, params={
        "where": f"STATE='{STATE}' AND COUNTY='{COUNTY}'",
        "outFields": "GEOID,INTPTLAT,INTPTLON,POP100,HU100", "returnGeometry": "false", "f": "json"}, timeout=120)
    if points.get("exceededTransferLimit") or not points.get("features"):
        raise FeedError("TIGERweb block list was empty or cut short")
    # The Census API needs a free key. Without one, occupied households are left blank.
    occupied = _occupied_units(key) if key else {}
    blocks = []
    for feature in points["features"]:
        a = feature["attributes"]
        blocks.append({"geoid": a["GEOID"], "lat": float(a["INTPTLAT"]), "lon": float(a["INTPTLON"]),
                       "people": int(a["POP100"] or 0), "units": int(a["HU100"] or 0),
                       "occupied": occupied.get(a["GEOID"])})
    if sum(b["people"] for b in blocks) < 300_000:
        raise FeedError("Orleans Parish block total is too low; the block list is incomplete")
    if key and sum(b["occupied"] is None for b in blocks) > len(blocks) * 0.02:
        # Do not cache a table without occupancy; try again next run.
        raise FeedError("Census occupied-housing table did not join to the block list")
    blocks.sort(key=lambda b: b["geoid"])
    write_json(path, {"source": "2020 Census (TIGERweb block counts; occupied units from DHC table H3)",
                      "has_occupied": bool(key), "blocks": blocks})
    return blocks


def _occupied_units(key):
    """Occupied housing units by block GEOID, from 2020 Census table H3."""
    query = urllib.parse.urlencode({"get": "H3_002N", "for": "block:*",
                                    "in": f"state:{STATE} county:{COUNTY} tract:*", "key": key})
    request = urllib.request.Request(f"{CENSUS_DHC}?{query}", headers={"User-Agent": common.USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise FeedError(f"Census API HTTP {exc.code}: {exc.read()[:200]!r}")
    try:
        table = json.loads(body)
    except ValueError:
        raise FeedError(f"Census API did not return JSON: {body[:200]!r}")
    header, rows = table[0], table[1:]
    col = {name: header.index(name) for name in header}
    return {row[col["state"]] + row[col["county"]] + row[col["tract"]] + row[col["block"]]: int(row[col["H3_002N"]])
            for row in rows}


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygons(geometry):
    """GeoJSON Polygon or MultiPolygon as a list of polygons, each a list of rings."""
    if not geometry:
        return []
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    return []


def contains(geometry, lon, lat):
    for rings in polygons(geometry):
        # Even-odd across rings, so holes are excluded.
        if sum(_in_ring(lon, lat, ring) for ring in rings) % 2 == 1:
            return True
    return False


def bbox(geometry):
    xs = [p[0] for rings in polygons(geometry) for ring in rings for p in ring]
    ys = [p[1] for rings in polygons(geometry) for ring in rings for p in ring]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def count_inside(geometry, blocks):
    box = bbox(geometry)
    people = units = occupied = n = 0
    if box:
        for b in blocks:
            if box[0] <= b["lon"] <= box[2] and box[1] <= b["lat"] <= box[3] and contains(geometry, b["lon"], b["lat"]):
                people += b["people"]; units += b["units"]; occupied += b["occupied"] or 0; n += 1
    known = any(b["occupied"] is not None for b in blocks)
    return {"people": people, "housing_units": units, "occupied_households": occupied if known else None, "blocks": n}


def touching_geoids(geometry):
    """GEOIDs of blocks an area touches, asked of TIGERweb one polygon at a time."""
    geoids = set()
    for rings in polygons(geometry):
        result = fetch_json(TIGER_BLOCKS, params={
            "geometry": json.dumps({"rings": rings, "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryPolygon", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
            "where": f"STATE='{STATE}' AND COUNTY='{COUNTY}'", "outFields": "GEOID",
            "returnGeometry": "false", "f": "json"}, timeout=60)
        if "features" not in result:
            raise FeedError("TIGERweb intersect query failed")
        geoids.update(f["attributes"]["GEOID"] for f in result["features"])
    return geoids


def _fingerprint(feature):
    return short_hash(repr(feature.get("geometry")))


def build(features, blocks, previous=None, touching=touching_geoids):
    by_geoid = {b["geoid"]: b for b in blocks}
    previous = {row["key"]: row for row in (previous or [])}
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        key = str(props.get("GlobalID") or props.get("OBJECTID"))
        fingerprint = _fingerprint(feature)
        old = previous.get(key)
        have_occupancy = any(b["occupied"] is not None for b in blocks)
        if old and old.get("geometry_hash") == fingerprint and (old.get("occupied_households") is not None or not have_occupancy):
            counts = {k: old[k] for k in ("people", "housing_units", "occupied_households", "blocks", "method")}
        else:
            counts = count_inside(feature.get("geometry"), blocks)
            counts["method"] = "blocks_inside"
            if counts["people"] < SMALL_AREA_PEOPLE and feature.get("geometry"):
                hit = [by_geoid[g] for g in touching(feature["geometry"]) if g in by_geoid]
                counts = {"people": sum(b["people"] for b in hit), "housing_units": sum(b["units"] for b in hit),
                          "occupied_households": sum(b["occupied"] or 0 for b in hit)
                          if any(b["occupied"] is not None for b in blocks) else None, "blocks": len(hit),
                          "method": "blocks_touching_upper_bound"}
        rows.append({
            "key": key, "objectid": props.get("OBJECTID"), "title": props.get("Advisory_Title"),
            "status": props.get("Adv_Status"), "begin": iso(from_epoch_ms(props.get("Public_Begin_DT"))),
            "end": iso(from_epoch_ms(props.get("Public_End_DT"))), "removed_at": feature.get("removed_at"),
            "geometry_hash": fingerprint, **counts,
        })
    rows.sort(key=lambda r: (r["begin"] or "", r["key"]))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    base = common.DATA / "water" / "swbno"
    if args.dry_run:
        from . import sources
        features = sources.fetch_swbno()["features"]
    else:
        features = read_json(base / "advisories.geojson", {"features": []})["features"]
    blocks = load_blocks()
    previous = read_json(base / "advisory_counts.json", {"advisories": []})["advisories"]
    rows = build(features, blocks, previous)
    summary = {
        "advisories": len(rows),
        "parish_people": sum(b["people"] for b in blocks),
        "parish_occupied_households": sum(b["occupied"] or 0 for b in blocks),
        "upper_bound_rows": sum(r["method"] != "blocks_inside" for r in rows),
        "zero_rows": sum(r["people"] == 0 for r in rows),
        "largest": max(rows, key=lambda r: r["people"], default=None),
        "latest": rows[-3:],
    }
    print(json.dumps(summary, indent=1))
    if not args.dry_run:
        write_json(base / "advisory_counts.json", {
            "method": "2020 Census blocks whose interior point is inside the advisory area; "
                      "areas under 100 people count every touching block as an upper bound",
            "advisories": rows})
    return 0


if __name__ == "__main__":
    sys.exit(main())
