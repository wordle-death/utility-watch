"""Keep a copy of S&WB's boil-water advisory areas and log every change.

The layer holds every advisory polygon S&WB has published since 2019. The
saved copy never drops an area: one that disappears from S&WB's layer stays
in the copy, geometry included, marked with when it was removed.
"""

from . import common
from .common import append_jsonl, iso, read_json, short_hash, write_json


def _key(feature):
    props = feature.get("properties") or {}
    return str(props.get("GlobalID") or props.get("OBJECTID") or feature.get("id"))


def _fingerprint(feature):
    return short_hash(
        repr(sorted((feature.get("properties") or {}).items())),
        repr(feature.get("geometry")),
    )


def update_swbno(payload, now):
    base = common.DATA / "water" / "swbno"
    incoming = (payload or {}).get("features") or []
    if not incoming:
        raise ValueError("S&WB layer returned no features; keeping the previous copy")
    previous = read_json(base / "advisories.geojson", {"features": []})
    saved = {_key(f): f for f in previous.get("features") or []}

    changes, live_keys = [], set()
    for feature in incoming:
        key = _key(feature)
        live_keys.add(key)
        old = saved.get(key)
        if old is None:
            change = "added"
        elif old.get("removed_at"):
            change = "restored"
        elif _fingerprint(old) != _fingerprint(feature):
            change = "updated"
        else:
            continue
        saved[key] = feature
        changes.append({"time": iso(now), "key": key, "change": change, "properties": feature.get("properties")})

    for key, feature in saved.items():
        if key not in live_keys and not feature.get("removed_at"):
            feature["removed_at"] = iso(now)
            changes.append({"time": iso(now), "key": key, "change": "removed", "properties": feature.get("properties")})

    features = [saved[k] for k in sorted(saved)]
    write_json(base / "advisories.geojson", {"type": "FeatureCollection", "features": features})
    append_jsonl(base / "changes.jsonl", changes)
    return {"source": "swbno", "advisory_areas": len(live_keys), "kept_total": len(features), "changes": len(changes)}
