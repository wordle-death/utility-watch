"""Run collectors.

    python -m collectors.run power            # all power feeds
    python -m collectors.run water            # S&WB advisory areas
    python -m collectors.run power --dry-run  # fetch and parse, write nothing

Each source runs on its own; one failing feed does not stop the others.
Failures are recorded in data/status-<group>.json and the job summary. A
scheduled run exits with an error only when a source first goes 6 hours
without a successful run, so a broken feed sends one failure email, not one
every 15 minutes. A dry run exits with an error if any source fails.
"""

import argparse
import json
import os
import sys
import traceback

from . import power, sources, water
from . import common
from datetime import timedelta

from .common import iso, now_utc, parse_iso, read_json, write_json

STALE_AFTER = timedelta(hours=6)
# Refresh last_success at most hourly, so status files do not change every run.
HEARTBEAT = timedelta(minutes=55)


def _record_status(group, now, results, failures):
    """Update data/status-<group>.json; return sources that just went stale."""
    path = common.DATA / f"status-{group}.json"
    status = read_json(path, {})
    for result in results:
        entry = status.get(result["source"], {})
        last = parse_iso(entry.get("last_success"))
        if entry.get("last_error") or last is None or now - last >= HEARTBEAT:
            status[result["source"]] = {"last_success": iso(now), "last_error": None}
    newly_stale = []
    for key, error in failures.items():
        entry = status.setdefault(key, {"last_success": None})
        entry["last_error"] = error
        entry.setdefault("failing_since", iso(now))
        healthy_at = parse_iso(entry.get("last_success")) or parse_iso(entry["failing_since"])
        if now - healthy_at >= STALE_AFTER and not entry.get("alerted"):
            entry["alerted"] = True
            newly_stale.append(key)
    write_json(path, status)
    return newly_stale


def _summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def run(group, dry_run=False):
    now = now_utc()
    results, failures = [], {}
    jobs = list(sources.POWER_SOURCES.items()) if group == "power" else [("swbno", None)]

    for key, collect in jobs:
        try:
            if group == "power":
                current, restored = collect()
                if dry_run:
                    results.append({
                        "source": key,
                        "on_map": len(current),
                        "restored_listed": len(restored or []),
                        "customers_out": sum(e["customers"] for e in current),
                        "sample": {k: str(v) for k, v in (current[0] if current else {}).items()},
                        "raw_sample": sources.RAW_SAMPLES.get(key),
                    })
                else:
                    results.append(power.update(key, current, now, restored))
            else:
                payload = sources.fetch_swbno()
                if dry_run:
                    results.append({"source": key, "advisory_areas": len((payload or {}).get("features") or [])})
                else:
                    results.append(water.update_swbno(payload, now))
        except Exception as exc:
            failures[key] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    alert = []
    if not dry_run:
        alert = _record_status(group, now, results, failures)

    report = {"run_at": iso(now), "group": group, "dry_run": dry_run, "results": results, "failures": failures}
    print(json.dumps(report, indent=1))
    lines = [f"### {group} collection {'(dry run) ' if dry_run else ''}at {iso(now)}"]
    lines += [f"- {r['source']}: " + ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("source", "sample", "raw_sample")) for r in results]
    lines += [f"- **{k} failed:** {v}" for k, v in failures.items()]
    lines += [f"- **{k} has had no successful run for {STALE_AFTER}.**" for k in alert]
    _summary(lines)
    if dry_run:
        return 1 if failures else 0
    return 1 if alert else 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["power", "water"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    sys.exit(run(args.group, args.dry_run))


if __name__ == "__main__":
    main()
