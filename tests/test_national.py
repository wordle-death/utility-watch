"""Tests for the national reliability comparison, on a small made-up table."""

import unittest

try:
    import pandas as pd
    from national import reliability
except ImportError:  # pandas is only needed for the national job
    pd = None


def table():
    rows = []
    # Ten investor-owned IEEE utilities in 2025 with SAIDI 100..1000, 100k customers each.
    for i in range(1, 11):
        rows.append((i, f"Utility {i}", "LA", "Investor Owned", "2025-01-01", 100_000, "ieee_standard",
                     i * 100.0, i * 50.0, 1.0, 0.8))
    # Same utility reported twice: the IEEE row must win.
    rows.append((3, "Utility 3", "LA", "Investor Owned", "2025-01-01", 100_000, "other_standard", 9999.0, 9999.0, 9, 9))
    # A tiny system and a non-IEEE reporter are left out of rankings.
    rows.append((50, "Tiny", "LA", "Cooperative", "2025-01-01", 200, "ieee_standard", 5.0, 5.0, 0.1, 0.1))
    rows.append((51, "Own Method", "TX", "Municipal", "2025-01-01", 500_000, "other_standard", 1.0, 1.0, 0.1, 0.1))
    columns = ["utility_id_eia", "utility_name_eia", "state", "entity_type", "report_date", "customers", "standard",
               "saidi_w_major_event_days_minutes", "saidi_wo_major_event_days_minutes",
               "saifi_w_major_event_days_customers", "saifi_wo_major_event_days_customers"]
    return pd.DataFrame(rows, columns=columns)


@unittest.skipIf(pd is None, "pandas not installed")
class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.df = reliability.tidy(table())

    def test_ieee_row_preferred(self):
        row = self.df[self.df["utility_id_eia"] == 3].iloc[0]
        self.assertEqual(row["saidi_with"], 300.0)

    def test_ranking_pool_excludes_tiny_and_non_ieee(self):
        pool = reliability.rank(self.df, 2025)
        self.assertEqual(len(pool), 10)

    def test_profile_percentiles(self):
        entry = reliability.profile(self.df, 8, "LA")[0]
        # Seven of ten utilities have fewer outage minutes than utility 8.
        self.assertEqual(entry["saidi_with_pct_of_utilities_better"], 70.0)
        self.assertEqual(entry["saidi_with_national_avg"], 550.0)
        self.assertEqual(entry["saidi_with_peer_count"], 10)

    def test_national_average_is_weighted_by_customers(self):
        df = reliability.tidy(pd.concat([table(), pd.DataFrame([
            (60, "Big", "TX", "Investor Owned", "2025-01-01", 9_000_000, "ieee_standard", 0.0, 0.0, 0, 0)],
            columns=table().columns)]))
        # Ten utilities of 100k averaging 550, plus one of 9 million at 0.
        self.assertEqual(reliability.weighted_mean(reliability.rank(df, 2025), "saidi_with"), 55.0)
        # The big one is outside the half-to-double peer range of utility 8.
        self.assertEqual(reliability.profile(df, 8, "LA")[0]["saidi_with_peer_count"], 10)

    def test_impossible_values_are_dropped(self):
        extra = pd.DataFrame([
            (12532, "ID typed as minutes", "TN", "Municipal", "2025-01-01", 5000, "ieee_standard", 12532.0, 90.0, 1, 1),
            (70, "Over a year", "TX", "Municipal", "2025-01-01", 5000, "ieee_standard", 900_000.0, 80.0, 1, 1)],
            columns=table().columns)
        df = reliability.tidy(pd.concat([table(), extra]))
        self.assertEqual(len(reliability.rank(df, 2025, "saidi_with")), 10)
        self.assertEqual(len(reliability.rank(df, 2025, "saidi_without")), 12)

    def test_build_fails_when_too_few_utilities(self):
        with self.assertRaises(ValueError):
            reliability.build(self.df)

    def test_build_shape(self):
        reliability.MIN_POOL, saved = 5, reliability.MIN_POOL
        self.addCleanup(setattr, reliability, "MIN_POOL", saved)
        result = reliability.build(self.df)
        self.assertEqual(result["latest_year"], 2025)
        self.assertEqual(len(result["utilities_latest_year"]), 12)
        self.assertEqual(result["national_by_year"][0]["saidi_with_median"], 550.0)


if __name__ == "__main__":
    unittest.main()
