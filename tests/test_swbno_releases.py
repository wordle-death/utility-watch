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
        self.assertEqual(west["hours"], 109.7)

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
