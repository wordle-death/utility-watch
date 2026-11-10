"""Turn repeated snapshots of a utility's live outage map into a log of outages.

Live maps only show what is out right now. Each run compares the current
snapshot with the outages still open from earlier runs:

- an outage seen for the first time is opened;
- an outage still present is updated, and customer-hours are added for the
  time since it was last seen, at the customer count seen last time;
- an outage no longer present is closed and written to the monthly log.

When a feed reports its own end time (Idaho Power does), that time is used.
Otherwise the end is estimated as the midpoint between the last run that saw
the outage and the first run that did not, and that window is kept.
"""

from datetime import timedelta

from . import common
from .common import append_jsonl, iso, parse_iso, read_json, write_json

# Keep IDs of recently closed outages so a feed that lists restored outages
# does not log the same outage twice.
CLOSED_MEMORY = timedelta(days=7)


def _event_record(event, now):
    return {
        "id": str(event["id"]),
        "start": iso(event.get("start")) or iso(now),
        "start_basis": "reported" if event.get("start") else "first_seen",
        "first_seen": iso(now),
        "last_seen": iso(now),
        "customers": event.get("customers", 0),
        "peak_customers": event.get("customers", 0),
        "customer_hours_observed": 0.0,
        "cause": event.get("cause"),
        "status": event.get("status"),
        "kind": event.get("kind"),
        "lat": event.get("lat"),
        "lon": event.get("lon"),
        "zips": event.get("zips") or [],
        "places": event.get("places") or [],
        "etr": iso(event.get("etr")),
    }


def _close(record, end, basis):
    record = dict(record)
    record["end"] = iso(end)
    record["end_basis"] = basis
    start = parse_iso(record["start"])
    hours = max((end - start).total_seconds() / 3600, 0) if start else None
    record["duration_hours"] = round(hours, 2) if hours is not None else None
    record["customer_hours_observed"] = round(record["customer_hours_observed"], 1)
    return record


def update(source_key, events, now, restored=None):
    """Apply one snapshot. Returns a summary dict.

    events:   normalized outages currently on the map.
    restored: optional normalized outages the feed reports as restored, each
              with an "end" datetime.
    """
    base = common.DATA / "power" / source_key
    state = read_json(base / "active.json", {"events": {}, "closed_recent": {}})
    active = state["events"]
    closed_recent = state["closed_recent"]
    restored_by_id = {str(r["id"]): r for r in (restored or [])}

    opened, closed = 0, []
    seen = set()
    for event in events:
        start = event.get("start")
        if start is not None and start > now:
            continue  # scheduled for the future; count it once it starts
        event_id = str(event["id"])
        seen.add(event_id)
        record = active.get(event_id)
        if record is None:
            active[event_id] = _event_record(event, now)
            opened += 1
            continue
        hours = (now - parse_iso(record["last_seen"])).total_seconds() / 3600
        record["customer_hours_observed"] += record["customers"] * max(hours, 0)
        customers = event.get("customers", 0)
        record.update(
            last_seen=iso(now),
            customers=customers,
            peak_customers=max(record["peak_customers"], customers),
            cause=event.get("cause") or record.get("cause"),
            status=event.get("status"),
            etr=iso(event.get("etr")),
        )

    for event_id in [i for i in active if i not in seen]:
        record = active.pop(event_id)
        reported = restored_by_id.get(event_id)
        if reported and reported.get("end"):
            end, basis = reported["end"], "reported"
            hours = (end - parse_iso(record["last_seen"])).total_seconds() / 3600
            record["customer_hours_observed"] += record["customers"] * max(hours, 0)
        else:
            # The outage ended sometime between the last sighting and now.
            # Use the midpoint, and keep the window so the uncertainty is visible.
            last_seen = parse_iso(record["last_seen"])
            end, basis = last_seen + (now - last_seen) / 2, "midpoint_estimate"
            record["end_window"] = [record["last_seen"], iso(now)]
            hours = (end - last_seen).total_seconds() / 3600
            record["customer_hours_observed"] += record["customers"] * max(hours, 0)
        closed.append(_close(record, end, basis))
        closed_recent[event_id] = iso(end)

    # Restored outages that ended between runs and were never seen open.
    for event_id, reported in restored_by_id.items():
        if event_id in closed_recent or event_id in active or not reported.get("end"):
            continue
        record = _event_record(reported, now)
        record["first_seen"] = None
        record["customer_hours_observed"] = 0.0
        closed_record = _close(record, reported["end"], "reported")
        if closed_record["duration_hours"] is not None:
            closed_record["customer_hours_observed"] = round(
                record["customers"] * closed_record["duration_hours"], 1
            )
        closed.append(closed_record)
        closed_recent[event_id] = iso(reported["end"])

    cutoff = now - CLOSED_MEMORY
    state["closed_recent"] = {
        i: t for i, t in closed_recent.items() if parse_iso(t) and parse_iso(t) >= cutoff
    }
    write_json(base / "active.json", state)
    closed.sort(key=lambda r: (r["end"] or "", r["id"]))
    append_jsonl(base / "events" / f"{now:%Y-%m}.jsonl", closed)
    return {
        "source": source_key,
        "on_map": len(events),
        "active": len(active),
        "opened": opened,
        "closed": len(closed),
        "customers_out": sum(r["customers"] for r in active.values()),
    }
