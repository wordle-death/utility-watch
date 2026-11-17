"""Turn repeated snapshots of a utility's live outage map into a log of outages.

Live maps only show what is out right now. Each run compares the current
snapshot with the outages still open from earlier runs:

- an outage seen for the first time is opened;
- an outage still present is updated, and customer-hours are added for the
  time since it was last seen, at the customer count seen last time;
- an outage no longer present is closed and written to the log for the month
  it ended.

When a feed reports its own end time (Idaho Power does), that time is used.
Otherwise the end is estimated as the midpoint between the last run that saw
the outage and the first run that did not, and that window is kept.

Safeguards:
- An outage without an ID is an error, so a renamed field cannot merge every
  outage into one.
- A snapshot that suddenly shows nothing while several outages were open is
  held for one run before anything is closed, so a feed hiccup does not close
  and later reopen every outage.

Planned work: a feed may list maintenance before it begins (an event with
"pending" set). Nothing is counted while it is pending. For work first seen
pending, customer-hours and duration count only time in progress, with the
switch between pending and in progress placed at the midpoint between runs,
and a listing that vanishes without ever being seen in progress is logged
with zero customer-hours. Work first seen already in progress is treated like
any other outage, including hours estimated back to its listed start.
Records saved before this rule existed are migrated on their next run; a
migrated record that is still pending has its earlier hours set to zero and
is flagged.
"""

from collections import defaultdict
from datetime import timedelta

from . import common
from .common import append_jsonl, iso, parse_iso, read_json, write_json

# Remember outages logged from a feed's restored list, so they are logged once.
CLOSED_MEMORY = timedelta(days=7)
# An empty snapshot with at least this many outages open is held for one run.
EMPTY_GUARD = 3


class FeedError(Exception):
    """The feed's response cannot be trusted as a snapshot."""


def _hours(later, earlier):
    return max((later - earlier).total_seconds() / 3600, 0)


def _new_record(event, now):
    start = event.get("start")
    customers = event.get("customers", 0)
    pending = bool(event.get("pending"))
    return {
        "id": event["id"],
        "start": iso(start) or iso(now),
        "start_basis": "reported" if start else "first_seen",
        "first_seen": iso(now),
        "last_seen": iso(now),
        "customers": customers,
        "peak_customers": customers,
        # Hours between the reported start and the first run that saw it,
        # at the first count seen. Kept apart from hours actually observed.
        "customer_hours_before_first_seen": round(customers * _hours(now, start), 1) if start and not pending else 0.0,
        "customer_hours_observed": 0.0,
        "planned": event.get("planned"),  # True, False, or None when the feed does not say
        "pending": pending,
        # Listed in advance: duration is then the time in progress, not the time since first seen.
        "opened_pending": pending,
        "in_progress_hours": 0.0,
        # First run that saw the outage actually under way (for planned work listed in advance).
        "in_progress_first_seen": None if pending else iso(now),
        "max_gap_minutes": 0,
        "cause": event.get("cause"),
        "status": event.get("status"),
        "kind": event.get("kind"),
        "lat": event.get("lat"),
        "lon": event.get("lon"),
        "zips": event.get("zips") or [],
        "places": event.get("places") or [],
        "etr": iso(event.get("etr")),
    }


def _migrate(record, event, now):
    """Bring a record saved before planned work was tracked up to date."""
    record["planned"] = event.get("planned")
    record["migrated_from_older_record"] = True
    if event.get("pending"):
        # Still only listed: the hours the older code added were not outage time.
        record.update(pending=True, opened_pending=True, in_progress_hours=0.0, in_progress_first_seen=None,
                      customer_hours_observed=0.0, customer_hours_before_first_seen=0.0)
    else:
        record.update(pending=False, opened_pending=False, in_progress_hours=0.0,
                      in_progress_first_seen=record.get("first_seen") or iso(now))


def _close(record, end, basis):
    record = dict(record)
    record["end"] = iso(end)
    record["end_basis"] = basis
    start = parse_iso(record["start"])
    record["duration_hours"] = round(_hours(end, start), 2) if start else None
    if record.get("opened_pending"):
        # Listed in advance: the listed start is the window's start, not when power went off.
        record["duration_hours"] = round(record.get("in_progress_hours", 0.0), 2)
    record["in_progress_hours"] = round(record.get("in_progress_hours", 0.0), 2)
    record["customer_hours_observed"] = round(record["customer_hours_observed"], 1)
    record["customer_hours"] = round(
        record["customer_hours_observed"] + record.get("customer_hours_before_first_seen", 0), 1
    )
    return record


def _normalize_ids(events):
    """Validate IDs and make duplicates within one snapshot distinct."""
    counts = defaultdict(int)
    for event in events:
        if event.get("id") in (None, "", "None"):
            raise FeedError("an outage has no ID; the feed's fields may have changed")
        base = str(event["id"])
        counts[base] += 1
        event["id"] = base if counts[base] == 1 else f"{base}#{counts[base]}"
    return events


def update(source_key, events, now, restored=None):
    """Apply one snapshot. Returns a summary dict.

    events:   normalized outages currently on the map.
    restored: optional normalized outages the feed reports as restored, each
              with an "end" datetime.
    """
    base = common.DATA / "power" / source_key
    state = read_json(base / "active.json", {"events": {}, "logged_recent": {}})
    active = state["events"]
    logged_recent = state.get("logged_recent", {})
    events = _normalize_ids(list(events))
    restored = _normalize_ids(list(restored or []))
    restored_by_id = {r["id"]: r for r in restored}

    current = [e for e in events if e["id"] in active or e.get("start") is None or e["start"] <= now]
    if not current and len(active) >= EMPTY_GUARD and state.get("empty_streak", 0) == 0:
        state["empty_streak"] = 1
        write_json(base / "active.json", state)
        return {"source": source_key, "on_map": 0, "active": len(active), "opened": 0, "closed": 0,
                "customers_out": sum(r["customers"] for r in active.values()), "held_empty_snapshot": True}
    state["empty_streak"] = 0

    opened, closed, seen = 0, [], set()
    for event in current:
        event_id = event["id"]
        seen.add(event_id)
        record = active.get(event_id)
        if record is None:
            active[event_id] = _new_record(event, now)
            opened += 1
            continue
        last_seen = parse_iso(record["last_seen"])
        pending = bool(event.get("pending"))
        if "pending" not in record and "pending" in event:
            _migrate(record, event, now)
        gap = _hours(now, last_seen)
        # Hours in progress over the gap: all of it, none, or half when the state changed between runs.
        was, now_pending = bool(record.get("pending")), pending
        counted = gap if not was and not now_pending else 0.0 if was and now_pending else gap / 2
        record["customer_hours_observed"] += record["customers"] * counted
        record["in_progress_hours"] = record.get("in_progress_hours", 0.0) + counted
        record["max_gap_minutes"] = max(record["max_gap_minutes"], round(gap * 60))
        if "in_progress_first_seen" in record and record["in_progress_first_seen"] is None and not pending:
            record["in_progress_first_seen"] = iso(now)
        if "pending" in record:
            record["pending"] = pending
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
        last_seen = parse_iso(record["last_seen"])
        reported = restored_by_id.get(event_id)
        if reported and reported.get("end"):
            end, basis = max(reported["end"], last_seen), "reported"
        else:
            # Ended sometime between the last sighting and now: use the midpoint
            # and keep the window so the uncertainty is visible.
            end, basis = last_seen + (now - last_seen) / 2, "midpoint_estimate"
            record["end_window"] = [record["last_seen"], iso(now)]
            record["max_gap_minutes"] = max(record["max_gap_minutes"], round(_hours(now, last_seen) * 60))
        if not record.get("pending"):
            record["customer_hours_observed"] += record["customers"] * _hours(end, last_seen)
            record["in_progress_hours"] = record.get("in_progress_hours", 0.0) + _hours(end, last_seen)
        closed.append(_close(record, end, basis))
        logged_recent[event_id] = iso(now)

    # Restored outages that started and ended between runs, never seen open.
    cutoff = now - CLOSED_MEMORY
    for event_id, reported in restored_by_id.items():
        end = reported.get("end")
        if not end or end < cutoff or event_id in logged_recent or event_id in active:
            continue
        record = _new_record(dict(reported, pending=False), now)
        record.update(first_seen=None, last_seen=None, customer_hours_before_first_seen=0.0,
                      in_progress_first_seen=None, opened_pending=False)
        closed_record = _close(record, end, "reported")
        # Never observed open: estimate from the reported duration instead.
        closed_record["customer_hours"] = round(reported.get("customers", 0) * (closed_record["duration_hours"] or 0), 1)
        closed_record["customer_hours_basis"] = "reported_duration"
        closed.append(closed_record)
        logged_recent[event_id] = iso(now)

    state["logged_recent"] = {i: t for i, t in logged_recent.items() if parse_iso(t) >= cutoff}
    state.pop("closed_recent", None)
    write_json(base / "active.json", state)

    by_month = defaultdict(list)
    for row in sorted(closed, key=lambda r: (r["end"], r["id"])):
        by_month[row["end"][:7]].append(row)
    for month, rows in by_month.items():
        append_jsonl(base / "events" / f"{month}.jsonl", rows)

    return {
        "source": source_key,
        "on_map": len(current),
        "active": len(active),
        "opened": opened,
        "closed": len(closed),
        "customers_out": sum(r["customers"] for r in active.values()),
    }
