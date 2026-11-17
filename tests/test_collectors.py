"""Offline tests: parsers on feed samples, and outage open/update/close logic.

Run with: python -m unittest discover -s tests
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest import mock

from collectors import common, power, run, sources, water

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
        self.assertEqual(event["id"], 229)

    def test_schema_change_is_an_error(self):
        with self.assertRaises(power.FeedError):
            sources.parse_mlgw({"type": "FeatureCollection"})
        with self.assertRaises(power.FeedError):
            sources.parse_idaho_current({"object": None})

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
        # Plus 30 minutes at 100 customers before the first run saw it.
        self.assertEqual(row["customer_hours"], 300.0)
        self.assertEqual(row["max_gap_minutes"], 60)
        self.assertEqual(row["end_basis"], "midpoint_estimate")
        self.assertEqual(row["end"], common.iso(T0 + timedelta(hours=1, minutes=30)))
        self.assertEqual(row["duration_hours"], 2.0)

    def test_planned_work_counts_only_while_in_progress(self):
        start, hour = T0 - timedelta(hours=3), timedelta(hours=1)
        def planned(pending):
            return dict(outage(7, 100, start), planned=True, pending=pending)
        power.update("x", [planned(True)], T0)             # listed ahead of time
        power.update("x", [planned(True)], T0 + hour)      # still only scheduled
        power.update("x", [planned(False)], T0 + 2 * hour)  # crew has started
        power.update("x", [planned(False)], T0 + 3 * hour)
        power.update("x", [], T0 + 4 * hour)
        row = self.log("x")[0]
        # Half of the gap when it started, one observed hour, half of the final gap; nothing while scheduled.
        self.assertEqual((row["customer_hours_observed"], row["customer_hours"]), (200.0, 200.0))
        self.assertEqual(row["customer_hours_before_first_seen"], 0.0)
        self.assertEqual(row["in_progress_first_seen"], common.iso(T0 + 2 * hour))
        self.assertEqual(row["duration_hours"], 2.0)
        self.assertTrue(row["planned"])

    def test_planned_work_never_seen_in_progress_counts_nothing(self):
        start = T0 - timedelta(hours=3)
        listing = dict(outage(8, 97, start), planned=True, pending=True)
        power.update("x", [listing], T0)
        power.update("x", [listing], T0 + timedelta(hours=10))
        power.update("x", [], T0 + timedelta(hours=11))
        row = self.log("x")[0]
        self.assertEqual((row["customer_hours"], row["duration_hours"], row["in_progress_first_seen"]), (0.0, 0.0, None))

    def test_planned_work_paused_again_counts_only_time_in_progress(self):
        start, hour = T0 - timedelta(hours=3), timedelta(hours=1)
        def planned(pending):
            return dict(outage(9, 100, start), planned=True, pending=pending)
        for h, pending in [(0, True), (1, False), (2, False), (3, True), (4, True)]:
            power.update("x", [planned(pending)], T0 + h * hour)
        power.update("x", [], T0 + 5 * hour)
        row = self.log("x")[0]
        # Half an hour, one hour, half an hour in progress: the duration matches the hours.
        self.assertEqual((row["customer_hours"], row["duration_hours"]), (200.0, 2.0))

    def test_restored_only_planned_outage_keeps_its_length(self):
        # Idaho Power reports some outages only once restored; planned ones must not count as zero.
        reported = dict(outage(3, 100, T0 - timedelta(hours=3)), planned=True, end=T0 - timedelta(hours=1))
        power.update("x", [], T0, restored=[reported])
        row = self.log("x")[0]
        self.assertEqual((row["duration_hours"], row["customer_hours"]), (2.0, 200.0))
        self.assertEqual(row["in_progress_first_seen"], row["start"])  # it did start; not a never-started listing

    def test_older_record_for_scheduled_work_is_reset(self):
        start = T0 - timedelta(hours=3)
        power.update("x", [outage(4, 100, start)], T0)  # saved by the older collector
        path = common.DATA / "power" / "x" / "active.json"
        state = common.read_json(path, {})
        for key in ("pending", "planned", "in_progress_first_seen", "opened_pending", "in_progress_hours"):
            state["events"]["4"].pop(key, None)
        common.write_json(path, state)
        listing = dict(outage(4, 100, start), planned=True, pending=True)
        power.update("x", [listing], T0 + timedelta(hours=2))
        power.update("x", [listing], T0 + timedelta(hours=3))
        power.update("x", [], T0 + timedelta(hours=4))
        row = self.log("x")[0]
        self.assertEqual((row["customer_hours"], row["duration_hours"], row["planned"]), (0.0, 0.0, True))
        self.assertTrue(row["migrated_from_older_record"])

    def _older(self, event_id, kind, status):
        """Save an outage the way the older collector did: no planned-work fields."""
        path = common.DATA / "power" / "x" / "active.json"
        state = common.read_json(path, {})
        record = state["events"][str(event_id)]
        for key in ("pending", "planned", "in_progress_first_seen", "opened_pending", "in_progress_hours"):
            record.pop(key, None)
        record.update(kind=kind, status=status)
        common.write_json(path, state)

    def test_older_scheduled_record_that_starts_drops_its_scheduled_hours(self):
        start = T0 - timedelta(hours=30)
        power.update("x", [outage(5, 100, start)], T0)
        power.update("x", [outage(5, 100, start)], T0 + timedelta(hours=10))  # older code piled up hours
        self._older(5, "PLANNED_OUTAGE", "SCHEDULED")
        started = dict(outage(5, 100, start), planned=True, pending=False, kind="PLANNED_OUTAGE", status="IN PROGRESS")
        power.update("x", [started], T0 + timedelta(hours=11))
        power.update("x", [], T0 + timedelta(hours=12))
        row = self.log("x")[0]
        # Half the hour it started in, half the final hour: one hour in progress.
        self.assertEqual((row["customer_hours"], row["duration_hours"]), (100.0, 1.0))
        self.assertTrue(row["migrated_from_older_record"])

    def test_older_scheduled_record_gone_on_first_run_counts_nothing(self):
        start = T0 - timedelta(hours=30)
        power.update("x", [outage(6, 100, start)], T0)
        self._older(6, "PLANNED_OUTAGE", "SCHEDULED")
        power.update("x", [], T0 + timedelta(hours=1))
        row = self.log("x")[0]
        self.assertEqual((row["customer_hours"], row["duration_hours"], row["planned"]), (0.0, 0.0, True))

    def test_feeds_without_planned_status_are_unchanged(self):
        start = T0 - timedelta(minutes=30)
        power.update("x", [outage(1, 100, start)], T0)
        self._older(1, None, "Waiting for an available crew")  # MLGW-style record
        power.update("x", [outage(1, 100, start)], T0 + timedelta(hours=1))
        power.update("x", [], T0 + timedelta(hours=2))
        row = self.log("x")[0]
        self.assertEqual((row["customer_hours"], row["duration_hours"]), (200.0, 2.0))
        self.assertNotIn("migrated_from_older_record", row)
        self.assertNotIn("in_progress_hours", row)

    def test_work_seen_in_progress_then_pending_counts_as_before(self):
        start, hour = T0 - timedelta(hours=5), timedelta(hours=1)
        power.update("x", [dict(outage(2, 100, start), planned=True, pending=False)], T0)
        power.update("x", [dict(outage(2, 100, start), planned=True, pending=True)], T0 + hour)
        power.update("x", [], T0 + 2 * hour)
        row = self.log("x")[0]
        self.assertEqual((row["customer_hours"], row["duration_hours"]), (650.0, 6.5))

    def test_older_planned_record_in_progress_is_flagged(self):
        start = T0 - timedelta(hours=5)
        power.update("x", [outage(3, 100, start)], T0)
        self._older(3, "PLANNED_OUTAGE", "IN PROGRESS")
        started = dict(outage(3, 100, start), planned=True, pending=False)
        power.update("x", [started], T0 + timedelta(hours=1))
        power.update("x", [], T0 + timedelta(hours=2))
        self.assertTrue(self.log("x")[0]["hours_may_include_scheduled_time"])

    def test_entergy_scheduled_work_is_pending(self):
        base = {"id": 5, "startTime": 1793800800000, "numPeople": 14, "latitude": 30.0, "longitude": -90.0}
        scheduled, started, unplanned = sources.parse_entergy([
            dict(base, type="PLANNED_OUTAGE", status="SCHEDULED"),
            dict(base, id=6, type="PLANNED_OUTAGE", status="IN PROGRESS"),
            dict(base, id=7, status="Outage Reported"),
        ])
        self.assertEqual((scheduled["planned"], scheduled["pending"]), (True, True))
        self.assertEqual((started["planned"], started["pending"]), (True, False))
        self.assertEqual((unplanned["planned"], unplanned["pending"]), (False, False))

    def test_outage_open_before_this_change_keeps_counting(self):
        # A record saved by the older collector has no "pending" field.
        start = T0 - timedelta(minutes=30)
        power.update("x", [outage(1, 100, start)], T0)
        state = common.read_json(common.DATA / "power" / "x" / "active.json", {})
        for key in ("pending", "planned", "in_progress_first_seen", "opened_pending", "in_progress_hours"):
            state["events"]["1"].pop(key, None)
        common.write_json(common.DATA / "power" / "x" / "active.json", state)
        power.update("x", [outage(1, 100, start)], T0 + timedelta(hours=1))
        power.update("x", [], T0 + timedelta(hours=2))
        self.assertEqual(self.log("x")[0]["customer_hours"], 200.0)

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
        self.assertEqual(rows[0]["customer_hours"], 20.0)
        self.assertEqual(rows[0]["customer_hours_basis"], "reported_duration")

    def test_old_restored_outage_is_not_logged(self):
        end = T0 - timedelta(days=9)
        restored = [dict(outage(5, 20, end - timedelta(hours=1)), end=end)]
        for minutes in (0, 15, 30):
            power.update("x", [], T0 + timedelta(minutes=minutes), restored)
        self.assertEqual(self.log("x", "2026-11") + self.log("x", "2026-10"), [])

    def test_sudden_empty_snapshot_is_held_once(self):
        start = T0 - timedelta(hours=1)
        power.update("x", [outage(i, 10, start) for i in range(5)], T0)
        held = power.update("x", [], T0 + timedelta(minutes=15))
        self.assertTrue(held.get("held_empty_snapshot"))
        self.assertEqual(held["active"], 5)
        # Back on the next run: nothing was closed or reopened.
        back = power.update("x", [outage(i, 10, start) for i in range(5)], T0 + timedelta(minutes=30))
        self.assertEqual((back["opened"], back["closed"]), (0, 0))
        # Empty twice in a row: now they close.
        power.update("x", [], T0 + timedelta(minutes=45))
        closed = power.update("x", [], T0 + timedelta(minutes=60))
        self.assertEqual(closed["closed"], 5)

    def test_missing_id_is_an_error(self):
        with self.assertRaises(power.FeedError):
            power.update("x", [outage(None, 10)], T0)

    def test_duplicate_ids_are_kept_apart(self):
        summary = power.update("x", [outage("a", 3), outage("a", 100)], T0)
        self.assertEqual((summary["active"], summary["customers_out"]), (2, 103))

    def test_log_goes_to_month_outage_ended(self):
        nov1 = datetime(2026, 11, 1, 0, 10, tzinfo=timezone.utc)
        power.update("x", [outage(1, 10, nov1 - timedelta(hours=1))], nov1 - timedelta(minutes=30))
        power.update("x", [], nov1 - timedelta(minutes=20))
        self.assertEqual(len(self.log("x", "2026-10")), 1)

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

    def test_removed_area_is_kept_with_geometry(self):
        water.update_swbno({"features": [self.feature(1, "active"), self.feature(2, "active")]}, T0)
        water.update_swbno({"features": [self.feature(2, "active")]}, T0)
        saved = json.loads((common.DATA / "water" / "swbno" / "advisories.geojson").read_text())
        kept = {f["properties"]["OBJECTID"]: f for f in saved["features"]}
        self.assertIn("removed_at", kept[1])
        self.assertIn("geometry", kept[1])

    def test_paging_collects_every_page(self):
        pages = [{"features": [self.feature(i, "a") for i in range(500)], "exceededTransferLimit": True},
                 {"features": [self.feature(i, "a") for i in range(500, 520)]}]
        with mock.patch.object(sources, "fetch_json", side_effect=pages):
            self.assertEqual(len(sources.fetch_swbno()["features"]), 520)

    def test_empty_response_does_not_erase_copy(self):
        water.update_swbno({"features": [self.feature(1, "active")]}, T0)
        with self.assertRaises(ValueError):
            water.update_swbno({"features": []}, T0)
        saved = json.loads((common.DATA / "water" / "swbno" / "advisories.geojson").read_text())
        self.assertEqual(len(saved["features"]), 1)


class StatusTests(TempData):
    def test_one_alert_after_six_hours_of_failure(self):
        run._record_status("power", T0, [{"source": "x"}], {})
        alerts = [run._record_status("power", T0 + timedelta(hours=h), [], {"x": "boom"}) for h in (1, 5, 7, 8)]
        self.assertEqual(alerts, [[], [], ["x"], []])

    def test_success_heartbeat_is_hourly(self):
        run._record_status("power", T0, [{"source": "x"}], {})
        path = common.DATA / "status-power.json"
        before = path.read_text()
        run._record_status("power", T0 + timedelta(minutes=15), [{"source": "x"}], {})
        self.assertEqual(path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
