"""Tests for the S&WB press-release timeline, on made-up releases."""

import unittest

from collectors import swbno_releases as sr

LIST_HTML = '''
<a class="p-4" href="/PressReleases/Details/5127"
   style="x">
    <h4 class="normal-subtitle dark">Thursday,  October 22 2026, 8:02 AM - Precautionary Boil Water Advisory Issued for a portion of New Orleans East</h4>
    <p>New Orleans, LA - Sewerage &amp; Water Board &hellip;</p>
</a>
<a class="p-4" href="/PressReleases/Details/5130" style="x">
    <h4 class="normal-subtitle dark">Friday, October 23 2026, 1:03 PM - Precautionary Boil Water Advisory Canceled for New Orleans East</h4>
    <p>Canceled.</p>
</a>'''


def rel(i, published, title):
    return {"id": i, "published": published, "title": title, "summary": "boil water advisory"}


class ReleaseTests(unittest.TestCase):
    def test_parse_list(self):
        items = sr.parse_list(LIST_HTML)
        self.assertEqual([i["id"] for i in items], [5127, 5130])
        self.assertEqual(items[0]["published"], "2026-10-22T13:02:00Z")  # 8:02 AM Central Daylight Time
        self.assertTrue(items[0]["title"].startswith("Precautionary Boil Water Advisory Issued"))

    def test_classify(self):
        self.assertEqual(sr.classify("Precautionary Boil Water Advisory Issued for Venetian Isles"), "issued")
        self.assertEqual(sr.classify("Testing in Progress: Precautionary Boil Water Advisory for West Bank"), "testing")
        self.assertEqual(sr.classify("Precautionary Boil Water Advisory Canceled for Venetian Isles"), "lifted")
        self.assertEqual(sr.classify("Boil Water Advisory Lifted for the Majority of West Bank; Limited portion remains in effect"), "partial_lift")
        self.assertEqual(sr.classify("Water Pressure Restored; Boil Water Advisory Remains in Effect"), "update")

    def test_collect_stops_when_nothing_new(self):
        calls = []
        found = sr.collect({}, fetch=lambda page, search: calls.append((page, search)) or LIST_HTML, pause=0)
        self.assertEqual(len(found), 2)
        self.assertEqual(calls, [(1, "boil"), (2, "boil")])

    def test_collect_falls_back_when_search_is_empty(self):
        found = sr.collect({}, fetch=lambda page, search: "" if search else LIST_HTML, pause=0)
        self.assertEqual(len(found), 2)

    def test_collect_fails_when_site_returns_nothing(self):
        with self.assertRaises(sr.FeedError):
            sr.collect({}, fetch=lambda page, search: "", pause=0)

    def test_two_overlapping_advisories_close_separately(self):
        releases = [
            rel(1, "2026-08-07T18:03:00Z", "Precautionary Boil Water Advisory Issued Venetian Isles"),
            rel(2, "2026-08-08T06:45:00Z", "Precautionary Boil Water Advisory Issued for the West Bank New Orleans"),
            rel(3, "2026-08-09T13:43:00Z", "Testing in Progress: Precautionary Boil Water Advisory for West Bank New Orleans"),
            rel(4, "2026-08-10T18:22:00Z", "Precautionary Boil Water Advisory Canceled for Venetian Isles"),
            rel(5, "2026-08-10T22:20:00Z", "Precautionary Boil Water Advisory Lifted for the Majority of West Bank New Orleans; Limited portion remains in effect for the Memorial Park Neighborhood"),
            rel(6, "2026-08-12T20:27:00Z", "Precautionary Boil Water Advisory Canceled for Memorial Park Neighborhood"),
        ]
        advisories = sr.build_advisories(releases)
        self.assertEqual(len(advisories), 2)
        venetian, west = advisories
        self.assertEqual(venetian["lifted_at"], "2026-08-10T18:22:00Z")
        self.assertEqual(venetian["release_ids"], [1, 4])
        self.assertEqual(west["partial_lift_at"], "2026-08-10T22:20:00Z")
        self.assertEqual(west["lifted_at"], "2026-08-12T20:27:00Z")
        # Hours run to the first lift; the small area that stayed under advisory is flagged, not counted.
        self.assertEqual(west["hours"], 63.6)
        self.assertIn("remainder_after_partial_lift_not_counted", west["flags"])

    def test_east_bank_and_new_orleans_east_stay_separate(self):
        advisories = sr.build_advisories([
            rel(1, "2025-01-23T01:36:00Z", "Precautionary Boil Water Advisory Issued for Parts of New Orleans East and Venetian Isles"),
            rel(2, "2025-01-26T18:59:00Z", "Precautionary Boil Water Advisory Issued for the East Bank of New Orleans"),
            rel(3, "2025-01-27T22:36:00Z", "Precautionary Boil Water Advisory Canceled for Majority of East Bank of New Orleans; Boil Water Advisory Remains in place for Parts of New Orleans East"),
            rel(4, "2025-01-28T20:40:00Z", "Precautionary Boil Water Advisories Lifted for Multiple Areas in New Orleans East and Venetian Isles"),
        ])
        self.assertEqual(len(advisories), 2)
        east_bank = advisories[1]
        self.assertEqual(east_bank["hours"], 27.6)
        self.assertEqual(advisories[0]["lifted_at"], "2025-01-28T20:40:00Z")
        counts = [{"key": "eb", "begin": "2025-01-24T06:00:00Z", "title": "Testing- Precautionary BWA - East Bank of NO",
                   "people": 333330, "housing_units": 170672, "method": "blocks_inside"}]
        sr.attach_areas(advisories, counts)
        self.assertEqual(east_bank["area_keys"], ["eb"])  # two days apart, matched by name

    def test_lift_of_another_area_does_not_stop_the_clock(self):
        advisories = sr.build_advisories([
            rel(1, "2024-08-07T01:15:00Z", "Precautionary Boil Water Advisory Issued for entire East Bank of New Orleans and Algiers Point"),
            rel(2, "2024-08-08T17:59:00Z", "SWBNO Extends Precautionary Boil Water Advisory for East Bank; Precautionary Boil Water Advisory Canceled for West Bank"),
            rel(3, "2024-08-09T00:19:00Z", "Precautionary Boil Water Advisory Canceled for New Orleans"),
        ])
        self.assertEqual(len(advisories), 1)
        self.assertEqual(advisories[0]["hours"], 47.1)
        self.assertNotIn("partial_lift_at", advisories[0])

    def test_expanded_advisory_opens_one(self):
        self.assertEqual(sr.classify("Expanded Precautionary Boil Water Advisory for parts of New Orleans East"), "issued")

    def test_limited_area_does_not_borrow_a_citywide_count(self):
        advisories = sr.build_advisories([
            rel(1, "2025-06-28T05:50:00Z", "Precautionary Boil Water Advisory for Limited Parts of East Bank"),
            rel(2, "2025-06-29T05:50:00Z", "Precautionary Boil Water Advisory Canceled for Limited Parts of East Bank"),
        ])
        counts = [{"key": "eb", "begin": "2025-01-24T06:00:00Z", "title": "BWA - East Bank of NO",
                   "people": 333330, "housing_units": 170672, "method": "blocks_inside"}]
        sr.attach_areas(advisories, counts)
        self.assertIsNone(advisories[0]["people"])

    def test_union_is_used_for_several_areas(self):
        advisories = sr.build_advisories([
            rel(1, "2026-03-09T13:00:00Z", "Precautionary Boil Water Advisory Issued for the East Bank"),
            rel(2, "2026-03-10T13:00:00Z", "Precautionary Boil Water Advisory Canceled for the East Bank"),
        ])
        counts = [{"key": k, "begin": "2026-03-09T06:00:00Z", "title": "East Bank", "people": 100,
                   "housing_units": 50, "method": "blocks_inside"} for k in ("a", "b")]
        sr.attach_areas(advisories, counts, union=lambda keys: (150, 70))
        self.assertEqual((advisories[0]["people"], advisories[0]["person_hours"]), (150, 3600))

    def test_broad_area_without_map_borrows_a_count(self):
        advisories = sr.build_advisories([
            rel(1, "2024-08-07T01:15:00Z", "Precautionary Boil Water Advisory Issued for entire East Bank of New Orleans and Algiers Point"),
            rel(2, "2024-08-08T18:00:00Z", "Precautionary Boil Water Advisory Canceled for East Bank of New Orleans and Algiers Point"),
        ])
        counts = [{"key": "eb", "begin": "2025-01-24T06:00:00Z", "title": "BWA - East Bank of NO",
                   "people": 333330, "housing_units": 170672, "method": "blocks_inside"}]
        sr.attach_areas(advisories, counts)
        self.assertEqual(advisories[0]["people"], 333330)
        self.assertEqual(advisories[0]["flags"], ["area_from_named_area_lookup", "other_named_places_not_counted"])

    def test_named_area_uses_whole_drawing_not_partial_or_combined(self):
        counts = [
            {"key": "whole", "begin": "2019-10-03T05:00:00Z", "title": "Precautionary B.W.A. in Lower 9th Ward",
             "people": 8475, "housing_units": 4051, "method": "blocks_inside"},
            {"key": "combined", "begin": "2019-02-04T06:00:00Z", "title": "B.W.A. for Almonaster to Canal, L9W",
             "people": 23923, "housing_units": 12469, "method": "blocks_inside"},
            {"key": "partial", "begin": "2020-01-01T06:00:00Z", "title": "Limited part of Lower 9th Ward",
             "people": 90000, "housing_units": 1, "method": "blocks_inside"},
            {"key": "vi", "begin": "2019-08-16T05:00:00Z", "title": "Venetian Isles boil water advisory",
             "people": 757, "housing_units": 396, "method": "blocks_inside"},
        ]
        self.assertEqual(sr.named_areas(counts)["lower9"]["key"], "whole")
        advisories = sr.build_advisories([
            rel(1, "2016-06-02T15:00:00Z", "Precautionary Boil Water Advisory For Lower Ninth Ward Area of New Orleans"),
            rel(2, "2016-06-03T15:00:00Z", "Boil Water Advisory Lifted for Lower Ninth Ward"),
            rel(3, "2013-12-18T15:00:00Z", "Boil Water Advisory For A Limited Area of Venetian Isles"),
            rel(4, "2013-12-19T15:00:00Z", "Boil Water Advisory Lifted for Venetian Isles"),
        ])
        sr.attach_areas(advisories, counts)
        limited, lower9 = advisories
        self.assertEqual((lower9["people"], lower9["person_hours"]), (8475, 8475 * 24))
        self.assertEqual(lower9["flags"], ["area_from_named_area_lookup"])
        self.assertIsNone(limited["people"])  # "a limited area of" is not the whole place

    def test_real_titles_that_were_misread(self):
        for title, kind in [
            ("Precautionary Boil-Water Advisory For The Entire East Bank of New Orleans", "issued"),
            ("Limited precautionary boil-water advisory for Village De L\u2019est, Willowbrook and Alcee Fortier areas", "issued"),
            ("SWB Precautionary Boil Water Advisory", "issued"),
            ("Scheduled Precautionary Boil Water Advisory In Effect for Venetian Isles", "issued"),
            ("Precautionary Boil Water Advisory Still in Place for West Bank of Orleans Parish", "update"),
            ("Precautionary Boil Water Advisory Remains in Effect for a Portion of New Orleans East", "update"),
            ("Mayor Cantrell, SWBNO Chronicle Events Leading to NOLA East Bank Boil Water Advisory Issued on Nov.17", "update"),
            ("SWBNO presents City Council with chronicle of events leading to the Nov. 17 boil water advisory", "update"),
            ("Update on Boil Water Advisory for East Bank of Orleans Parish", "update"),
            ("New Update: All Water Restored, Testing Remains in Progress for Precautionary Boil Water Advisory Issued for parts of New Orleans East", "testing"),
            ("Precautionary Boil Water Advisory Lifted for Audubon Street from Spruce to Claiborne, Precautionary Boil Water Advisory Still in Effect for other Areas", "partial_lift"),
            ("SWBNO lifts precautionary BWA for parts of the East; limited area remains under BWA", "partial_lift"),
            ("Precautionary Boil Water Advisory Canceled for Remaining Uptown Properties", "lifted"),
            ("Precautionary Boil Water Advisory Lifted for All Customers", "lifted"),
        ]:
            self.assertEqual(sr.classify(title), kind, title)

    def test_january_2018_freeze(self):
        left_out = []
        advisories = sr.build_advisories([
            rel(2052, "2018-01-17T23:50:00Z", "Precautionary Boil-Water Advisory For New Orleans East"),
            rel(2054, "2018-01-18T16:51:00Z", "Precautionary Boil-Water Advisory For The Entire East Bank of New Orleans"),
            rel(2055, "2018-01-20T02:02:00Z", "Precautionary Boil Water Advisory Lifted for East Bank of New Orleans West of the Industrial Canal And Lower Ninth Ward"),
            rel(2056, "2018-01-20T20:43:00Z", "New Orleans: Limit Water Use, Precautionary Boil Water Advisory Lifted For New Orleans East"),
            rel(2061, "2018-01-23T20:35:00Z", "Precautionary Boil-Water Advisory For Westbank of Orleans Parish"),
            rel(2068, "2018-01-25T00:08:00Z", "Precautionary Boil Water Advisory Still in Place for West Bank of Orleans Parish"),
            rel(2069, "2018-01-25T12:41:00Z", "Precautionary Boil Water Advisory Lifted for West Bank of New Orleans"),
        ], left_out)
        self.assertEqual([(a["issued_at"][:10], a["hours"]) for a in advisories],
                         [("2018-01-17", 68.9), ("2018-01-18", 33.2), ("2018-01-23", 40.1)])
        self.assertEqual(left_out, [])

    def test_partial_lift_named_as_the_east_stops_the_clock(self):
        advisories = sr.build_advisories([
            rel(1, "2025-11-14T17:09:00Z", "Precautionary Boil Water Advisory Issued for Limited Portion of New Orleans East"),
            rel(2, "2025-11-15T17:41:00Z", "SWBNO lifts precautionary BWA for parts of the East; limited area remains under BWA"),
            rel(3, "2025-11-16T17:25:00Z", "Precautionary Boil Water Advisory Canceled for New Orleans East"),
        ])
        self.assertEqual(advisories[0]["hours"], 24.5)
        self.assertIn("remainder_after_partial_lift_not_counted", advisories[0]["flags"])

    def test_lift_with_no_advisory_is_recorded_and_repeat_is_not(self):
        left_out = []
        advisories = sr.build_advisories([
            rel(1, "2013-07-24T20:34:00Z", "Boil Water Advisory Lifted for Uptown Section of City"),
            rel(2, "2022-08-01T19:34:00Z", "Precautionary Boil Water Advisory Issued for parts of New Orleans Westbank"),
            rel(3, "2022-08-03T15:29:00Z", "Update: Precautionary Boil Water Advisory Canceled for parts of New Orleans Westbank"),
            rel(4, "2022-08-03T15:29:00Z", "Update: Precautionary Boil Water Advisory Canceled for parts of New Orleans Westbank"),
        ], left_out)
        self.assertEqual([(u["id"], u["reason"]) for u in left_out], [(1, "no_open_advisory")])
        self.assertEqual(advisories[0]["release_ids"], [2, 3, 4])

    def test_bulk_posted_archive_is_left_out(self):
        left_out = []
        advisories = sr.build_advisories([
            rel(18, "2009-05-18T19:59:00Z", "Boil Water Advisory For Venetian Isles Is Lifted"),
            rel(22, "2009-05-18T20:13:00Z", "Boil Water Advisory For Venetian Isles"),
        ], left_out)
        self.assertEqual(advisories, [])
        self.assertEqual({u["reason"] for u in left_out}, {"archive_posted_in_bulk"})

    def test_lift_naming_another_place_is_flagged(self):
        advisories = sr.build_advisories([
            rel(1, "2026-05-19T14:50:00Z", "Precautionary Boil Water Advisory Issued for Portion of New Orleans East"),
            rel(2, "2026-05-20T16:17:00Z", "Precautionary Boil Water Advisory Canceled for the East Bank of New Orleans"),
        ])
        self.assertIn("lift_names_a_different_place", advisories[0]["flags"])
        self.assertEqual(advisories[0]["hours"], 25.4)

    def test_list_layout_change_is_an_error(self):
        dashed = LIST_HTML.replace(" - Precautionary", " \u2013 Precautionary")
        self.assertEqual(len(sr.parse_list(dashed)), 2)
        with self.assertRaises(sr.FeedError):
            sr.parse_list(LIST_HTML.replace("2026,", "2026 at"))

    def test_retitled_release_is_fetched_again(self):
        known = {"5127": {"title": "old title"}, "5130": {"title": "Precautionary Boil Water Advisory Canceled for New Orleans East"}}
        found = sr.collect(known, fetch=lambda page, search: LIST_HTML, pause=0)
        self.assertEqual([r["id"] for r in found], [5127])

    def test_small_areas_sharing_blocks_are_counted_once(self):
        import json, tempfile
        from pathlib import Path
        from collectors import common
        with tempfile.TemporaryDirectory() as tmp:
            saved, common.DATA = common.DATA, Path(tmp)
            self.addCleanup(setattr, common, "DATA", saved)
            (Path(tmp) / "census").mkdir()
            blocks = [{"geoid": g, "lat": 30.0, "lon": -90.0, "people": 100, "units": 40, "occupied": None} for g in "abc"]
            (Path(tmp) / "census" / "blocks-22071.json").write_text(json.dumps({"has_occupied": False, "blocks": blocks}))
            counts = [
                {"key": "x", "method": "blocks_touching_upper_bound", "people": 200, "housing_units": 80, "block_geoids": ["a", "b"]},
                {"key": "y", "method": "blocks_touching_upper_bound", "people": 200, "housing_units": 80, "block_geoids": ["b", "c"]},
                {"key": "old", "method": "blocks_touching_upper_bound", "people": 7, "housing_units": 3},
            ]
            union = sr.block_union(Path(tmp), counts)
            self.assertEqual(union(["x", "y"]), (300, 120, False))
            self.assertEqual(union(["x", "old"]), (207, 83, True))  # no block list saved: summed and flagged

    def test_issue_title_without_a_place_takes_it_from_the_lift(self):
        advisories = sr.build_advisories([
            rel(314, "2012-10-08T19:52:00Z", "SWB Precautionary Boil Water Advisory"),
            rel(315, "2012-10-09T19:28:00Z", "Boil Water Advisory Cancelled for Eastbank of Orleans Parish"),
        ])
        counts = [{"key": "eb", "begin": "2025-01-24T06:00:00Z", "title": "BWA - East Bank of NO",
                   "people": 333330, "housing_units": 170672, "method": "blocks_inside"}]
        sr.attach_areas(advisories, counts)
        self.assertEqual(advisories[0]["people"], 333330)
        self.assertIn("place_taken_from_lift_release", advisories[0]["flags"])
        totals = sr.yearly_totals(advisories)["2012"]
        self.assertEqual((totals["from_own_map"], totals["from_named_area_lookup"]), (0, advisories[0]["person_hours"]))

    def test_concurrent_advisories_are_flagged_and_final_remainder_lift_is_not(self):
        advisories = sr.build_advisories([
            rel(1, "2025-01-23T01:36:00Z", "Precautionary Boil Water Advisory Issued for Parts of New Orleans East and Venetian Isles"),
            rel(2, "2025-01-26T18:59:00Z", "Precautionary Boil Water Advisory Issued for the East Bank of New Orleans"),
            rel(3, "2025-01-27T22:36:00Z", "Precautionary Boil Water Advisory Canceled for Majority of East Bank of New Orleans; Boil Water Advisory Remains in place for Uptown"),
            rel(4, "2025-01-28T20:40:00Z", "Precautionary Boil Water Advisories Lifted for Multiple Areas in New Orleans East and Venetian Isles"),
            rel(5, "2025-01-29T20:40:00Z", "Precautionary Boil Water Advisory Lifted for Limited Portion of Uptown"),
        ])
        counts = [{"key": "ne", "begin": "2025-01-23T06:00:00Z", "title": "NO East", "people": 4000, "housing_units": 1, "method": "blocks_inside"},
                  {"key": "eb", "begin": "2025-01-26T06:00:00Z", "title": "East Bank", "people": 333330, "housing_units": 1, "method": "blocks_inside"}]
        sr.attach_areas(advisories, counts)
        for advisory in advisories:
            self.assertIn("concurrent_with_another_advisory_may_double_count", advisory["flags"])
            self.assertNotIn("lift_names_a_different_place", advisory["flags"])
        self.assertEqual(sr.yearly_totals(advisories)["2025"]["advisories_without_person_hours"], 0)

    def test_expansions_and_repeat_lifts(self):
        advisories = sr.build_advisories([
            rel(1, "2024-08-13T01:42:00Z", "Expanded Precautionary Boil Water Advisory for parts of New Orleans East"),
            rel(2, "2024-08-13T16:26:00Z", "EXPANDED - Testing in Progress: Precautionary Boil Water Advisory for parts of New Orleans East"),
            rel(3, "2024-08-13T17:00:00Z", "Precautionary Boil Water Advisory Issued for Uptown"),
            rel(4, "2024-08-14T15:52:00Z", "Boil Water Advisory Cancelled"),
            rel(5, "2024-08-14T15:52:00Z", "Boil Water Advisory Cancelled"),
        ])
        east, uptown = advisories
        self.assertEqual(sorted(east["flags"]), ["area_expanded_after_issue", "issue_release_missing", "no_lift_release_found"])
        self.assertEqual(uptown["release_ids"], [3, 4, 5])  # the repeat does not close the other advisory
        self.assertIsNone(east["lifted_at"])

    def test_lift_for_part_of_a_named_area_is_partial(self):
        self.assertEqual(sr.classify("Precautionary Boil Water Advisory Lifted for East Bank of New Orleans West of the Industrial Canal And Lower Ninth Ward"), "partial_lift")

    def test_areas_and_person_hours(self):
        advisories = sr.build_advisories([
            rel(1, "2026-10-22T13:02:00Z", "Precautionary Boil Water Advisory Issued for a portion of New Orleans East"),
            rel(2, "2026-10-23T18:03:00Z", "Precautionary Boil Water Advisory Canceled for New Orleans East"),
        ])
        counts = [
            {"key": "a", "begin": "2026-10-22T05:00:00Z", "title": "LIFTED: Precautionary BWA for NO East",
             "people": 31535, "housing_units": 13281, "method": "blocks_inside"},
            {"key": "old", "begin": "2019-02-04T06:00:00Z", "title": "x", "people": 5, "housing_units": 2, "method": "blocks_inside"},
        ]
        unmatched = sr.attach_areas(advisories, counts)
        self.assertEqual(unmatched, ["old"])
        self.assertEqual(advisories[0]["hours"], 29.0)
        self.assertEqual(advisories[0]["person_hours"], 31535 * 29)
        self.assertEqual(advisories[0]["flags"], [])

    def test_open_advisory_has_no_person_hours(self):
        advisories = sr.build_advisories([rel(1, "2026-10-22T13:02:00Z", "Precautionary Boil Water Advisory Issued for Algiers")])
        sr.attach_areas(advisories, [])
        self.assertIsNone(advisories[0]["person_hours"])
        self.assertIn("no_lift_release_found", advisories[0]["flags"])


if __name__ == "__main__":
    unittest.main()
