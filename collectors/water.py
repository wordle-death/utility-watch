"""Keep a copy of S&WB's boil-water advisory areas and log every change.

The layer holds every advisory polygon S&WB has published since 2019. Saving
it on a schedule keeps boundaries even if S&WB later edits or removes them.
"""

from . import common
from .common import append_jsonl, iso, read_json, short_hash, write_json


def _key(feature):
    props = feature.get("properties") or {}
    return str(props.get("OBJECTID") or props.get("GlobalID") or feature.get("id"))


def _fingerprint(feature):
    return short_hash(
        repr(sorted((feature.get("properties") or {}).items())),
        repr(feature.get("geometry")),
    )


def update_swbno(payload, now):
    base = common.DATA / "water" / "swbno"
    features = sorted((payload or {}).get("features") or [], key=_key)
    if not features:
        raise ValueError("S&WB layer returned no features; keeping the previous copy")
    previous = read_json(base / "advisories.geojson", {"features": []})
    before = {_key(f): f for f in previous.get("features") or []}
    after = {_key(f): f for f in features}

    changes = []
    for key, feature in after.items():
        if key not in before:
            changes.append({"time": iso(now), "objectid": key, "change": "added", "properties": feature.get("properties")})
        elif _fingerprint(before[key]) != _fingerprint(feature):
            changes.append({"time": iso(now), "objectid": key, "change": "updated", "properties": feature.get("properties")})
    for key, feature in before.items():
        if key not in after:
            changes.append({"time": iso(now), "objectid": key, "change": "removed", "properties": feature.get("properties")})

    write_json(base / "advisories.geojson", {"type": "FeatureCollection", "features": features})
    append_jsonl(base / "changes.jsonl", changes)
    return {"source": "swbno", "advisory_areas": len(features), "changes": len(changes)}
