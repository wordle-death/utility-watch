"""Offline tests: parsers on feed samples, and outage open/update/close logic.

Run with: python -m unittest discover -s tests
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collectors import common, power, sources, water

T0 = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)

# Samples shaped like the live feeds, as read on 2026-11-02.
ENTERGY_SAMPLE = [
    {"id": 229, "type": "UNPLANNED_OUTAGE", "startTime": 1793800800000, "etrTime": 1793829600000,
     "numPeople": 73, "status": "ASSIGNED", "cause": "", "latitude": 29.98799, "longitude": -90.09614},
]
IDAHO_RESTORED_SAMPLE = {"wasSuccessful": True, "list": [
    {"osiOutageId": 2600000911, "totalAffectedPremises": 40, "outageStartDate": "2026-11-02T14:39:12.04",
     "outageEndDate": "2026-11-02T15:14:08.09", "probableCauseCodeDisplayName": "Object In Line",
     "energizationStatusDisplayName": "Restored", "isPlannedOutage": False,
     "outageZipNumbers": ["83201"], "outageCityNames": ["POCATELLO"]},
]}
MLGW_SAMPLE = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"OUTAGE_NO": 1540786, "TIME_STAMP": "11/02/2026 06:54:30 PM",
     "CUR_CUST_AFF": 4, "OUT_CAUSE": " ", "STATUS": "Waiting for an available crew"},
     "geometry": {"type": "Point", "coordinates": [-89.94438, 35.12945]}},
]}
SRP_SAMPLE = [
    {"latitude": 33.3507, "longitude": -111.6287, "numberCustomersAffected": 4,
     "outageProblem": "Maintenance", "isMaintenanceOutage": True, "crossRoadText": "S ELLSWORTH RD "},
]


def outage(event_id, customers, start=None):
    return {"id": event_id, "customers": customers, "start": start, "cause": None, "status": None}


class TempData(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = common.DATA
        common.DATA = Path(self._tmp.name)

    def tearDown(self):
        common.DATA = self._saved
        self._tmp.cleanup()

    def log(self, key, month="2026-11"):
        path = common.DATA / "power" / key / "events" / f"{month}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class ParserTests(unittest.TestCase):
    def test_entergy(self):
        event = sources.parse_entergy(ENTERGY_SAMPLE)[0]
        self.assertEqual(event["customers"], 73)
        self.assertEqual(event["start"], datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc))
        self.assertIsNone(event["cause"])
        self.assertEqual(event["id"], "229-1793800800000")

    def test_idaho_restored_local_time(self):
        event = sources.parse_idaho_restored(IDAHO_RESTORED_SAMPLE)[0]
        # 14:39 Mountain Standard Time is 21:39 UTC.
        self.assertEqual(event["start"], datetime(2026, 11, 2, 21, 39, 12, tzinfo=timezone.utc))
        self.assertEqual(event["end"].hour, 22)
        self.assertEqual(event["zips"], ["83201"])

    def test_idaho_current(self):
        payload = {"object": {"outages": [{
            "omsOutageId": 2600001444, "omsCustomerCount": 48, "omsOutageStartDate": "2026-11-10T14:36:13.447",
            "omsStatusDescription": "On-site", "probableCause": "Object In Line", "isPlannedOutage": False,
            "omsEstimatedOutageRestorationDate": "2026-11-10T17:30:00", "latitude": 43.56, "longitude": -117.0,
            "outageCity": [{"omsOutageId": 0, "outageCityName": "HOMEDALE"}],
            "outageZip": [{"omsOutageId": 0, "outageZipName": "83628"}]}]}}
        event = sources.parse_idaho_current(payload)[0]
        self.assertEqual(event["id"], 2600001444)
        self.assertEqual(event["customers"], 48)
        self.assertEqual(event["start"], datetime(2026, 11, 10, 21, 36, 13, tzinfo=timezone.utc))
        self.assertEqual((event["zips"], event["places"]), (["83628"], ["HOMEDALE"]))

    def test_idaho_current_empty(self):
        payload = {"object": {"outages": [], "totalCustomersAffected": 0}}
        self.assertEqual(sources.parse_idaho_current(payload), [])

    def test_mlgw(self):
        event = sources.parse_mlgw(MLGW_SAMPLE)[0]
        self.assertEqual(event["id"], 1540786)
        self.assertEqual(event["start"], datetime(2026, 11, 3, 0, 54, 30, tzinfo=timezone.utc))
        self.assertIsNone(event["cause"])
        self.assertEqual((event["lat"], event["lon"]), (35.12945, -89.94438))

    def test_srp_id_is_stable_without_id_field(self):
        first = sources.parse_srp(SRP_SAMPLE)[0]
        second = sources.parse_srp(SRP_SAMPLE)[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["kind"], "PLANNED")
        self.assertEqual(first["places"], ["S ELLSWORTH RD"])


class PowerTests(TempData):
    def test_open_update_close(self):
        start = T0 - timedelta(minutes=30)
        power.update("x", [outage(1, 100, start)], T0)
        power.update("x", [outage(1, 300, start)], T0 + timedelta(hours=1))
        summary = power.update("x", [], T0 + timedelta(hours=2))
        self.assertEqual(summary["closed"], 1)
        row = self.log("x")[0]
        self.assertEqual(row["peak_customers"], 300)
        # 100 customers for 1 hour, then 300 for half of the final hour-long gap.
        self.assertEqual(row["customer_hours_observed"], 250.0)
        self.assertEqual(row["end_basis"], "midpoint_estimate")
        self.assertEqual(row["end"], common.iso(T0 + timedelta(hours=1, minutes=30)))
        self.assertEqual(row["duration_hours"], 2.0)

    def test_future_planned_outage_is_ignored(self):
        summary = power.update("x", [outage(1, 50, T0 + timedelta(days=2))], T0)
        self.assertEqual(summary["active"], 0)

    def test_reported_end_is_used(self):
        start = T0 - timedelta(hours=1)
        power.update("x", [outage(7, 40, start)], T0)
        restored = [dict(outage(7, 40, start), end=T0 + timedelta(minutes=10))]
        power.update("x", [], T0 + timedelta(minutes=15), restored)
        row = self.log("x")[0]
        self.assertEqual(row["end_basis"], "reported")
        self.assertAlmostEqual(row["customer_hours_observed"], 6.7, places=1)

    def test_restored_only_outage_logged_once(self):
        start, end = T0 - timedelta(hours=2), T0 - timedelta(hours=1)
        restored = [dict(outage(9, 20, start), end=end)]
        power.update("x", [], T0, restored)
        power.update("x", [], T0 + timedelta(minutes=15), restored)
        rows = self.log("x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_hours_observed"], 20.0)

    def test_no_change_leaves_files_untouched(self):
        power.update("x", [], T0)
        path = common.DATA / "power" / "x" / "active.json"
        before = path.read_text()
        power.update("x", [], T0 + timedelta(minutes=15))
        self.assertEqual(path.read_text(), before)


class WaterTests(TempData):
    def feature(self, objectid, status):
        return {"type": "Feature", "properties": {"OBJECTID": objectid, "Adv_Status": status},
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}

    def test_changes_are_logged(self):
        water.update_swbno({"features": [self.feature(1, "active")]}, T0)
        water.update_swbno({"features": [self.feature(1, "archived"), self.feature(2, "active")]}, T0)
        lines = (common.DATA / "water" / "swbno" / "changes.jsonl").read_text().splitlines()
        kinds = [json.loads(line)["change"] for line in lines]
        self.assertEqual(kinds, ["added", "updated", "added"])

    def test_empty_response_does_not_erase_copy(self):
        water.update_swbno({"features": [self.feature(1, "active")]}, T0)
        with self.assertRaises(ValueError):
            water.update_swbno({"features": []}, T0)
        saved = json.loads((common.DATA / "water" / "swbno" / "advisories.geojson").read_text())
        self.assertEqual(len(saved["features"]), 1)


if __name__ == "__main__":
    unittest.main()
