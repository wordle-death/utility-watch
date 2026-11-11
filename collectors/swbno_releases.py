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
swbno update updated updates majority part parts all entire following no nola area only still place city parish
board sewerage swb issues order called expanded reinstated scheduled customers""".split())
# Place names that share words ("East Bank" and "New Orleans East") become single tokens.
PHRASES = [
    (r"east\s?bank", "eastbank"),
    (r"new orleans east|eastern new orleans|n\.?\s?o\.? east|\bno east|\bthe east\b", "noeast"),
    (r"west\s?bank", "westbank"),
    (r"lower (9th|ninth)( ward)?|\bl9w\b", "lower9"),
    (r"venetian isles?", "venetian"),
]
# Areas S&WB names as a whole and has drawn for other advisories. An advisory
# for one of these with no map of its own reuses that drawing.
NAMED_AREAS = ("eastbank", "westbank", "lower9", "venetian")
# Releases dated before this were posted in bulk when the site's archive was
# loaded (a "lifted" notice minutes before its "issued" one), so their times
# are upload times, not event times. They are left out of the timeline.
ARCHIVE_BEFORE = "2009-06-01"
LONG_HOURS = 96  # advisories longer than this are flagged for a hand check


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def parse_list(page_html):
    """Releases on one list page: [{id, published, title, summary}]."""
    releases, unreadable = [], 0
    for release_id, heading, summary in ITEM.findall(page_html):
        parts = re.split(r"\s[-\u2013\u2014]\s", _text(heading), maxsplit=1)
        try:
            published = datetime.strptime(parts[0].strip(), "%A, %B %d %Y, %I:%M %p").replace(tzinfo=LOCAL)
        except ValueError:
            unreadable += 1
            continue
        releases.append({"id": int(release_id), "published": iso(published),
                         "title": parts[1].strip() if len(parts) > 1 else "", "summary": _text(summary)})
    # One odd heading is skipped; several mean the page layout changed.
    if unreadable > max(1, len(releases) // 5):
        raise FeedError(f"{unreadable} press release headings could not be read; the list layout may have changed")
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
            # New releases, and saved ones whose title has since been edited.
            new = [r for r in items if r["id"] not in found
                   and (str(r["id"]) not in known or known[str(r["id"])].get("title") != r["title"])]
            for release in new:
                found[release["id"]] = release
            if not items or not new:
                break
            if page == MAX_PAGES:
                raise FeedError(f"press release list still had new items at page {MAX_PAGES}; history would be cut short")
            time.sleep(pause)
        if page > 1 or items:
            return list(found.values())
    raise FeedError("S&WB press release list returned no items; its layout may have changed")


def is_boil(release):
    return "boil" in (release["title"] + " " + release["summary"]).lower()


LIFT_WORDS = re.compile(r"\b(cancel+ed|lifi?ted|lifts|lifi?ting|rescinded)\b", re.I)
REMAINDER = re.compile(r"\b(remains?|still|stays?|majority|partial|extends?|extended)\b")
TESTING = re.compile(r"\b(testing|sampling)\b.*\b(progress|underway|begun|begins)\b")
NOT_NEW = re.compile(r"\b(update[sd]?|remains?|still|stays?|continues|extends?|extended|chronicle|credit|council)\b")
OPENED = re.compile(r"\b(issued|issues|expanded|reinstated|called)\b")
PLAIN_NOTICE = re.compile(r"boil water (advisory|advisories|order)(( only)?( in effect)? for\b|$)")
LIMITING = re.compile(r"\b(limited|parts?|portions?|some|multiple|large|uptown)\b", re.I)


def _plain(title):
    """A title in lower case with hyphens and abbreviations evened out ("Boil-Water", "BWA")."""
    t = re.sub(r"[-\u2013\u2014]+", " ", html.unescape(title).lower())
    t = re.sub(r"\bbwa\b", "boil water advisory", t)
    return re.sub(r"\s+", " ", t).strip()


def classify(title):
    t = _plain(title)
    if LIFT_WORDS.search(t):
        # "Lifted for X; still in effect for Y" releases part of the area.
        return "partial_lift" if REMAINDER.search(t) else "lifted"
    if TESTING.search(t):
        return "testing"
    if NOT_NEW.search(t):
        return "update"  # "remains in effect", "update on ...": about an advisory already issued
    if "boil" in t and (OPENED.search(t) or PLAIN_NOTICE.search(t)):
        return "issued"
    return "update"


def area_tokens(title):
    t = title.lower()
    for pattern, token in PHRASES:
        t = re.sub(pattern, f" {token} ", t)
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS and len(w) > 1}


def lift_tokens(title):
    """Place names in the part of a title that says an advisory was lifted.

    "Canceled for Majority of East Bank; Advisory Remains for New Orleans East"
    lifts the East Bank, not New Orleans East.
    """
    clauses = [c for c in re.split(r";", title) if LIFT_WORDS.search(c)]
    return area_tokens(" ".join(clauses))


def build_advisories(releases, unattached=None):
    """Group boil-water releases into advisories, oldest first.

    Releases that belong to no advisory (a lift with no "issued" release on
    record, or the bulk-posted archive) are appended to `unattached`.
    """
    advisories, open_ones = [], []
    unattached = [] if unattached is None else unattached
    last_lift = None  # (release, advisory) of the most recent full lift

    def leave_out(release, kind, reason):
        unattached.append({"id": release["id"], "published": release["published"], "title": release["title"],
                           "kind": kind, "reason": reason})

    for release in sorted((r for r in releases if is_boil(r)), key=lambda r: (r["published"], r["id"])):
        kind = classify(release["title"])
        if release["published"] < ARCHIVE_BEFORE:
            leave_out(release, kind, "archive_posted_in_bulk")
            continue
        when = parse_iso(release["published"])
        tokens = lift_tokens(release["title"]) if kind in ("lifted", "partial_lift") else area_tokens(release["title"])
        open_ones = [a for a in open_ones if when - parse_iso(a["issued_at"]) <= timedelta(days=14)]

        def best(candidates):
            scored = [(len(tokens & set(a["area_tokens"])), a["issued_at"], a) for a in candidates]
            return max(scored, key=lambda s: (s[0], s[1])) if scored else (0, None, None)

        overlap, _, match = best(open_ones)
        if kind == "issued":
            smaller = min(len(tokens), len(match["area_tokens"])) if match else 0
            same_area = match and smaller and overlap / smaller >= 0.6
            if same_area and when - parse_iso(match["issued_at"]) <= timedelta(days=3):
                match["release_ids"].append(release["id"])  # a re-issue or correction
                if "expanded" in release["title"].lower():
                    # The larger area is counted from the first issue time, which overstates it.
                    match["flags"].append("area_expanded_after_issue")
                continue
            advisory = {"issued_at": release["published"], "lifted_at": None, "title": release["title"],
                        "area_tokens": sorted(tokens), "release_ids": [release["id"]], "flags": []}
            advisories.append(advisory)
            open_ones.append(advisory)
        elif match is None:
            # An update or lift with no advisory on record. Lifts matter: an advisory is missing.
            if kind in ("lifted", "partial_lift"):
                repeat = (last_lift and last_lift[0]["title"] == release["title"]
                          and when - parse_iso(last_lift[0]["published"]) <= timedelta(hours=1))
                if repeat:
                    last_lift[1]["release_ids"].append(release["id"])  # the same notice posted twice
                else:
                    leave_out(release, kind, "no_open_advisory")
        else:
            if overlap == 0 and kind == "lifted" and tokens and match["area_tokens"]:
                match["flags"].append("lift_names_a_different_place")
            elif overlap == 0 and len(open_ones) > 1:
                match["flags"].append("release_matched_by_time_only")
            match["release_ids"].append(release["id"])
            if kind == "partial_lift":
                # Only stop the clock if the lifted part is this advisory's own area;
                # "canceled for West Bank" does not lift an East Bank advisory.
                if overlap:
                    match.setdefault("partial_lift_at", release["published"])
                else:
                    match["flags"].append("partial_lift_of_unmatched_place_not_applied")
            elif kind == "lifted":
                match["lifted_at"] = release["published"]
                open_ones.remove(match)
                last_lift = (release, match)
    for advisory in advisories:
        # Count hours up to the first lift. When most of the area was released
        # early, the smaller area that stayed under advisory is not counted.
        end = advisory.get("partial_lift_at") or advisory["lifted_at"]
        if advisory.get("partial_lift_at"):
            advisory["flags"].append("remainder_after_partial_lift_not_counted")
        if end:
            hours = (parse_iso(end) - parse_iso(advisory["issued_at"])).total_seconds() / 3600
            advisory["hours"] = round(hours, 1)
            if hours > LONG_HOURS:
                advisory["flags"].append("unusually_long_check_by_hand")
        else:
            advisory["hours"] = None
            advisory["flags"].append("no_lift_release_found")
    return advisories


def named_areas(counts):
    """For each whole named area, the map area S&WB drew for it.

    Uses only drawings whose title names that area and no other place, and
    takes the largest, so a partial drawing is not mistaken for the whole.
    """
    chosen = {}
    for row in counts:
        tokens = area_tokens(row.get("title") or "")
        places = tokens & set(NAMED_AREAS)
        # The title must name this area and nothing else ("Almonaster to Canal, L9W" is a different shape).
        if len(places) != 1 or tokens != places or row["method"] != "blocks_inside" or LIMITING.search(row.get("title") or ""):
            continue
        name = next(iter(places))
        if name not in chosen or row["people"] > chosen[name]["people"]:
            chosen[name] = row
    return chosen


def attach_areas(advisories, counts, union=None):
    """Match map areas to advisories by date and name, then add people-hours.

    union(keys) returns (people, housing_units) for several areas without
    counting overlapping blocks twice; without it, areas are summed.
    """
    by_key = {row["key"]: row for row in counts}
    for advisory in advisories:
        advisory.update(area_keys=[], people=None, housing_units=None, upper_bound=False)
    unmatched = []
    for row in counts:
        if not row.get("begin"):
            continue
        day = parse_iso(row["begin"]).astimezone(LOCAL).date()
        tokens = area_tokens(row.get("title") or "")
        scored = []
        for advisory in advisories:
            gap = abs((parse_iso(advisory["issued_at"]).astimezone(LOCAL).date() - day).days)
            shared = len(tokens & set(advisory["area_tokens"]))
            # Within a day, the date is enough. Two or three days apart needs a shared place name.
            if gap <= 1 or (gap <= 3 and shared):
                scored.append((shared, -gap, advisory["issued_at"], advisory))
        if not scored:
            unmatched.append(row["key"])
            continue
        shared, _, _, target = max(scored, key=lambda item: item[:3])
        if len(scored) > 1 and not shared:
            target["flags"].append("area_matched_by_date_only")
        target["area_keys"].append(row["key"])

    named = named_areas(counts)

    for advisory in advisories:
        rows = [by_key[key] for key in advisory["area_keys"]]
        if len(rows) > 1 and union:
            advisory["people"], advisory["housing_units"], *summed = union(advisory["area_keys"])
            if summed and summed[0]:
                advisory["flags"].append("small_areas_summed_may_overlap")
        elif rows:
            advisory["people"] = sum(r["people"] for r in rows)
            advisory["housing_units"] = sum(r["housing_units"] for r in rows)
            if len(rows) > 1:
                advisory["flags"].append("multiple_areas_summed_may_overlap")
        else:
            # "the East Bank" names a whole area; "parts of the East Bank" does not.
            whole = not LIMITING.search(advisory["title"])
            reused = [named[t]["key"] for t in NAMED_AREAS if whole and t in advisory["area_tokens"] and t in named]
            if reused:
                if len(reused) > 1 and union:
                    advisory["people"], advisory["housing_units"] = union(reused)[:2]
                else:
                    advisory["people"] = sum(by_key[k]["people"] for k in reused)
                    advisory["housing_units"] = sum(by_key[k]["housing_units"] for k in reused)
                advisory["area_reused_from"] = reused
                advisory["flags"].append("area_from_named_area_lookup")
                other = set(advisory["area_tokens"]) - set(NAMED_AREAS)
                if other:
                    advisory["flags"].append("other_named_places_not_counted")
            else:
                advisory["flags"].append("no_map_area")
        advisory["upper_bound"] = any(r["method"] != "blocks_inside" for r in rows)
        if advisory["people"] is not None and advisory["issued_at"] < "2015":
            advisory["flags"].append("people_from_2020_census_for_earlier_year")
        known = advisory["people"] is not None and advisory["hours"] is not None
        advisory["person_hours"] = round(advisory["people"] * advisory["hours"]) if known else None
        advisory["flags"] = sorted(set(advisory["flags"]))
    return unmatched


def block_union(base, counts):
    """A union(keys) function that counts each Census block once across overlapping areas."""
    from . import households
    blocks = households.load_blocks()
    features = read_json(base / "advisories.geojson", {"features": []})["features"]
    geometry = {str((f.get("properties") or {}).get("GlobalID") or (f.get("properties") or {}).get("OBJECTID")):
                f.get("geometry") for f in features}
    by_key = {row["key"]: row for row in counts}

    by_geoid = {b["geoid"]: b for b in blocks}

    def union(keys):
        """(people, housing units, True if some small areas had to be summed without removing overlap)."""
        inside, people, units, summed = {}, 0, 0, False
        for key in keys:
            row = by_key[key]
            if row["method"] != "blocks_inside":
                # Too small to hold a block's interior point: every touching block is counted.
                if row.get("block_geoids") is not None:
                    inside.update((g, by_geoid[g]) for g in row["block_geoids"] if g in by_geoid)
                else:
                    people += row["people"]
                    units += row["housing_units"]
                    summed = True
                continue
            if not geometry.get(key):
                raise FeedError(f"advisory area {key} has a count but no shape on file")
            box = households.bbox(geometry[key])
            for b in blocks if box else []:
                if (b["geoid"] not in inside and box[0] <= b["lon"] <= box[2] and box[1] <= b["lat"] <= box[3]
                        and households.contains(geometry[key], b["lon"], b["lat"])):
                    inside[b["geoid"]] = b
        return (people + sum(b["people"] for b in inside.values()),
                units + sum(b["units"] for b in inside.values()), summed)

    return union


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
    unattached = []
    advisories = build_advisories(releases, unattached)
    counts = read_json(base / "advisory_counts.json", {"advisories": []})["advisories"]
    if not counts:
        raise FeedError("advisory_counts.json is missing or empty; run collectors.households first")
    unmatched = attach_areas(advisories, counts, block_union(base, counts))
    complete = [a for a in advisories if a["person_hours"] is not None]
    by_year = {}
    for advisory in complete:
        year = advisory["issued_at"][:4]
        entry = by_year.setdefault(year, {"advisories": 0, "person_hours": 0, "from_own_map": 0,
                                          "from_named_area_lookup": 0, "of_which_upper_bound": 0})
        entry["advisories"] += 1
        entry["person_hours"] += advisory["person_hours"]
        # Keep measured areas apart from areas borrowed from another advisory's drawing.
        entry["from_own_map" if advisory["area_keys"] else "from_named_area_lookup"] += advisory["person_hours"]
        if advisory["upper_bound"]:
            entry["of_which_upper_bound"] += advisory["person_hours"]
    summary = {
        "new_releases": len(new), "boil_releases": sum(is_boil(r) for r in releases),
        "advisories": len(advisories), "with_lift_time": sum(a["lifted_at"] is not None for a in advisories),
        "with_map_area": sum(bool(a["area_keys"]) for a in advisories), "complete": len(complete),
        "map_areas_unmatched": len(unmatched), "by_year": dict(sorted(by_year.items())),
        "releases_unattached": [u for u in unattached if u["reason"] != "archive_posted_in_bulk"],
        "releases_left_out_as_archive": sum(u["reason"] == "archive_posted_in_bulk" for u in unattached),
        "earliest": min((a["issued_at"] for a in advisories), default=None),
        "latest": advisories[-3:],
    }
    print(json.dumps(summary, indent=1))
    if not args.dry_run:
        write_json(base / "releases.json", {"source": LIST_URL, "releases": saved})
        write_json(base / "advisory_timeline.json", {
            "method": "Advisories grouped from S&WB press releases (issued to canceled); map areas matched by "
                      "date; people from 2020 Census blocks, for every year. Yearly totals separate advisories "
                      "with their own map (from_own_map) from those that reuse S&WB's drawing of a whole named "
                      "area (from_named_area_lookup); the reused East Bank drawing covers the whole East Bank, "
                      "which can be more than an advisory reached. Hours run from the issue release to the "
                      "first lift release. See flags on each advisory for uncertain steps.",
            "map_areas_unmatched": unmatched, "releases_unattached": unattached, "by_year_complete_only": summary["by_year"], "advisories": advisories})
    return 0


if __name__ == "__main__":
    sys.exit(main())
