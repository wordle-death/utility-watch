"""Run collectors.

    python -m collectors.run power            # all power feeds
    python -m collectors.run water            # S&WB advisory areas
    python -m collectors.run power --dry-run  # fetch and parse, write nothing

Each source runs on its own; one failing feed does not stop the others.
The run exits with an error only if every source failed, so a single broken
feed does not send failure emails every 15 minutes. Failures are recorded in
data/status.json and printed in the job summary.
"""

import argparse
import json
import os
import sys
import traceback

from . import power, sources, water
from . import common
from .common import iso, now_utc, read_json, write_json


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

    if not dry_run:
        status = read_json(common.DATA / "status.json", {})
        for result in results:
            status[result["source"]] = {"last_success": iso(now), "last_error": None}
        for key, error in failures.items():
            status.setdefault(key, {"last_success": None})
            status[key]["last_error"] = error
            status[key]["last_error_at"] = iso(now)
        write_json(common.DATA / "status.json", status)

    report = {"run_at": iso(now), "group": group, "dry_run": dry_run, "results": results, "failures": failures}
    print(json.dumps(report, indent=1))
    lines = [f"### {group} collection {'(dry run) ' if dry_run else ''}at {iso(now)}"]
    lines += [f"- {r['source']}: " + ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("source", "sample")) for r in results]
    lines += [f"- **{k} failed:** {v}" for k, v in failures.items()]
    _summary(lines)
    return 1 if jobs and len(failures) == len(jobs) else 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["power", "water"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    sys.exit(run(args.group, args.dry_run))


if __name__ == "__main__":
    main()
