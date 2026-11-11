"""Build a timeline of New Orleans boil-water advisories from S&WB press releases.

    python -m collectors.swbno_releases            # update data/water/swbno/
    python -m collectors.swbno_releases --dry-run  # fetch, print a summary, write nothing

S&WB's map layer says where each advisory applied but not when it was lifted.
Its press releases follow a pattern (issued, testing in progress, canceled),
each with a timestamp. This module:

1. saves every press release that mentions a boil-water advisory;
2. groups them into advisories, from the "issued" release to the "canceled" one;
3. matches each advisory to its map areas by date, and multiplies people by
   hours under advisory.

Grouping and matching use titles and dates, so they can be wrong. Every
advisory keeps the IDs of the releases and map areas it was built from, and
is flagged when a step was uncertain.
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import common
from .common import iso, parse_iso, read_json, write_json
from .power import FeedError

LIST_URL = "https://www.swbno.org/PressReleases"
DETAIL_URL = "https://www.swbno.org/PressReleases/Details/{}"
LOCAL = ZoneInfo("America/Chicago")
MAX_PAGES = 150
ITEM = re.compile(
    r'href="/PressReleases/Details/(\d+)"[^>]*>\s*<h4[^>]*>(.*?)</h4>\s*(?:<p>(.*?)</p>)?', re.S)
STOPWORDS = set("""a an the for of in and to is are at on new orleans precautionary boil water advisory advisories
bwa issued canceled cancelled lifted testing progress portion portions area areas neighborhood limited remains effect
swbno update updated majority part parts all entire following""".split())
ALIASES = {"westbank": "west bank", "eastbank": "east bank", "n.o.": "new orleans", "no east": "east"}


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def parse_list(page_html):
    """Releases on one list page: [{id, published, title, summary}]."""
    releases = []
    for release_id, heading, summary in ITEM.findall(page_html):
        heading = _text(heading)
        stamp, _, title = heading.partition(" - ")
        try:
            published = datetime.strptime(stamp.strip(), "%A, %B %d %Y, %I:%M %p").replace(tzinfo=LOCAL)
        except ValueError:
            continue
        releases.append({"id": int(release_id), "published": iso(published), "title": title.strip(),
                         "summary": _text(summary)})
    return releases


def fetch_page(page, search="boil"):
    """One list page (pages count from 1). search=None lists every release."""
    params = {"sortBy": "PRDate", "sortDir": "desc", "page": page, "pageSize": 25}
    if search:
        params["search"] = search
    request = urllib.request.Request(f"{LIST_URL}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": common.USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", "replace")


def collect(known, fetch=fetch_page, pause=1.0):
    """Fetch list pages, newest first, until a page holds nothing new.

    Uses the site's search for "boil"; if that returns nothing, reads the
    unfiltered list instead.
    """
    for search in ("boil", None):
        found = {}
        for page in range(1, MAX_PAGES + 1):
            items = parse_list(fetch(page, search))
            new = [r for r in items if str(r["id"]) not in known and r["id"] not in found]
            for release in new:
                found[release["id"]] = release
            if not items or not new:
                break
            time.sleep(pause)
        if page > 1 or items:
            return list(found.values())
    raise FeedError("S&WB press release list returned no items; its layout may have changed")


def is_boil(release):
    return "boil" in (release["title"] + " " + release["summary"]).lower()


def classify(title):
    t = title.lower()
    lifted = re.search(r"\b(cancel+ed|lifted|rescinded)\b", t)
    if lifted and re.search(r"remains? in effect|majority|partial", t):
        return "partial_lift"
    if lifted:
        return "lifted"
    if "testing in progress" in t or "testing underway" in t:
        return "testing"
    if "boil" in t and ("issued" in t or "issues" in t or t.startswith("precautionary boil water advisory")):
        return "issued"
    return "update"


def area_tokens(title):
    t = title.lower()
    for alias, plain in ALIASES.items():
        t = t.replace(alias, plain)
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS and len(w) > 1}


def build_advisories(releases):
    """Group boil-water releases into advisories, oldest first."""
    advisories, open_ones = [], []
    for release in sorted((r for r in releases if is_boil(r)), key=lambda r: (r["published"], r["id"])):
        kind = classify(release["title"])
        when = parse_iso(release["published"])
        tokens = area_tokens(release["title"])
        open_ones = [a for a in open_ones if when - parse_iso(a["issued_at"]) <= timedelta(days=14)]

        def best(candidates):
            scored = [(len(tokens & set(a["area_tokens"])), a["issued_at"], a) for a in candidates]
            return max(scored, key=lambda s: (s[0], s[1])) if scored else (0, None, None)

        overlap, _, match = best(open_ones)
        if kind == "issued":
            if match and overlap and when - parse_iso(match["issued_at"]) <= timedelta(days=3):
                match["release_ids"].append(release["id"])  # a re-issue or correction
                continue
            advisory = {"issued_at": release["published"], "lifted_at": None, "title": release["title"],
                        "area_tokens": sorted(tokens), "release_ids": [release["id"]], "flags": []}
            advisories.append(advisory)
            open_ones.append(advisory)
        elif match is None:
            continue  # an update or lift with no advisory on record; nothing to attach it to
        else:
            if overlap == 0 and len(open_ones) > 1:
                match["flags"].append("release_matched_by_time_only")
            match["release_ids"].append(release["id"])
            if kind == "partial_lift":
                match["partial_lift_at"] = release["published"]
            elif kind == "lifted":
                match["lifted_at"] = release["published"]
                open_ones.remove(match)
    for advisory in advisories:
        if advisory["lifted_at"]:
            hours = (parse_iso(advisory["lifted_at"]) - parse_iso(advisory["issued_at"])).total_seconds() / 3600
            advisory["hours"] = round(hours, 1)
        else:
            advisory["hours"] = None
            advisory["flags"].append("no_lift_release_found")
    return advisories


def attach_areas(advisories, counts):
    """Match map areas to advisories by local date, then add people-hours."""
    by_day = {}
    for advisory in advisories:
        day = parse_iso(advisory["issued_at"]).astimezone(LOCAL).date()
        by_day.setdefault(day, []).append(advisory)
        advisory.update(area_keys=[], people=0, housing_units=0, upper_bound=False)
    unmatched = []
    for row in counts:
        if not row.get("begin"):
            continue
        day = parse_iso(row["begin"]).astimezone(LOCAL).date()
        candidates = [a for offset in (0, -1, 1) for a in by_day.get(day + timedelta(days=offset), [])]
        if not candidates:
            unmatched.append(row["key"])
            continue
        tokens = area_tokens(row.get("title") or "")
        target = max(candidates, key=lambda a: (len(tokens & set(a["area_tokens"])),
                                                -abs((parse_iso(a["issued_at"]).astimezone(LOCAL).date() - day).days)))
        if len(candidates) > 1 and not tokens & set(target["area_tokens"]):
            target["flags"].append("area_matched_by_date_only")
        target["area_keys"].append(row["key"])
        target["people"] += row["people"]
        target["housing_units"] += row["housing_units"]
        target["upper_bound"] = target["upper_bound"] or row["method"] != "blocks_inside"
    for advisory in advisories:
        if not advisory["area_keys"]:
            advisory["flags"].append("no_map_area")
            advisory["people"] = advisory["housing_units"] = None
        if len(advisory["area_keys"]) > 1:
            advisory["flags"].append("multiple_areas_summed_may_overlap")
        known = advisory["people"] is not None and advisory["hours"] is not None
        advisory["person_hours"] = round(advisory["people"] * advisory["hours"]) if known else None
        advisory["flags"] = sorted(set(advisory["flags"]))
    return unmatched


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    base = common.DATA / "water" / "swbno"
    saved = read_json(base / "releases.json", {"releases": {}})["releases"]
    new = collect(saved)
    for release in new:
        saved[str(release["id"])] = release
    releases = list(saved.values())
    advisories = build_advisories(releases)
    counts = read_json(base / "advisory_counts.json", {"advisories": []})["advisories"]
    unmatched = attach_areas(advisories, counts)
    complete = [a for a in advisories if a["person_hours"] is not None]
    by_year = {}
    for advisory in complete:
        year = advisory["issued_at"][:4]
        entry = by_year.setdefault(year, {"advisories": 0, "person_hours": 0})
        entry["advisories"] += 1
        entry["person_hours"] += advisory["person_hours"]
    summary = {
        "new_releases": len(new), "boil_releases": sum(is_boil(r) for r in releases),
        "advisories": len(advisories), "with_lift_time": sum(a["lifted_at"] is not None for a in advisories),
        "with_map_area": sum(bool(a["area_keys"]) for a in advisories), "complete": len(complete),
        "map_areas_unmatched": len(unmatched), "by_year": dict(sorted(by_year.items())),
        "earliest": min((a["issued_at"] for a in advisories), default=None),
        "latest": advisories[-3:],
    }
    print(json.dumps(summary, indent=1))
    if not args.dry_run:
        write_json(base / "releases.json", {"source": LIST_URL, "releases": saved})
        write_json(base / "advisory_timeline.json", {
            "method": "Advisories grouped from S&WB press releases (issued to canceled); map areas matched by "
                      "date; people from 2020 Census blocks. See flags on each advisory for uncertain steps.",
            "map_areas_unmatched": unmatched, "by_year_complete_only": summary["by_year"], "advisories": advisories})
    return 0


if __name__ == "__main__":
    sys.exit(main())
