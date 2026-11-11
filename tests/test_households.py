"""Tests for counting households inside advisory areas, on made-up blocks."""

import unittest

from collectors import households

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
WITH_HOLE = {"type": "Polygon", "coordinates": [SQUARE["coordinates"][0], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
TINY = {"type": "Polygon", "coordinates": [[[20, 20], [20.1, 20], [20.1, 20.1], [20, 20.1], [20, 20]]]}


def block(geoid, lon, lat, people=100):
    return {"geoid": geoid, "lon": lon, "lat": lat, "people": people, "units": 50, "occupied": 40}


BLOCKS = [block("a", 1, 1), block("b", 5, 5), block("c", 11, 5), block("d", 20.5, 20.5, 30)]


def feature(key, geometry, begin=1760000000000):
    return {"properties": {"OBJECTID": key, "Advisory_Title": f"t{key}", "Public_Begin_DT": begin}, "geometry": geometry}


class HouseholdTests(unittest.TestCase):
    def test_blocks_inside(self):
        counts = households.count_inside(SQUARE, BLOCKS)
        self.assertEqual((counts["people"], counts["occupied_households"], counts["blocks"]), (200, 80, 2))

    def test_hole_is_excluded(self):
        self.assertEqual(households.count_inside(WITH_HOLE, BLOCKS)["people"], 100)

    def test_multipolygon(self):
        multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"], [[[10.5, 4], [12, 4], [12, 6], [10.5, 6], [10.5, 4]]]]}
        self.assertEqual(households.count_inside(multi, BLOCKS)["people"], 300)

    def test_small_area_uses_touching_blocks_as_upper_bound(self):
        rows = households.build([feature(1, TINY)], BLOCKS, touching=lambda g: {"d"})
        self.assertEqual(rows[0]["method"], "blocks_touching_upper_bound")
        self.assertEqual(rows[0]["people"], 30)

    def test_unchanged_geometry_reuses_previous_counts(self):
        def fail(_):
            raise AssertionError("should not query again")
        first = households.build([feature(1, TINY)], BLOCKS, touching=lambda g: {"d"})
        second = households.build([feature(1, TINY)], BLOCKS, previous=first, touching=fail)
        self.assertEqual(second[0]["people"], 30)

    def test_rows_sorted_by_begin(self):
        rows = households.build([feature(2, SQUARE, 1770000000000), feature(1, SQUARE, 1760000000000)], BLOCKS)
        self.assertEqual([r["objectid"] for r in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
