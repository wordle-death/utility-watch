"""Build the national power-reliability comparison from federal data.

Source: EIA Form 861 reliability data, as cleaned and published by the
Public Utility Data Liberation project (PUDL, Catalyst Cooperative).

    python -m national.reliability            # download, write data/national/reliability.json
    python -m national.reliability --inspect  # download and print the table's shape, write nothing

Measures (minutes and counts per customer per year):
- SAIDI: total minutes the average customer was without power.
- SAIFI: number of outages the average customer had.
Each is reported with and without "major event days" (large storms).

Utilities report under the IEEE standard or their own method. The two are
not strictly comparable, so each row records which one it used, and
rankings use IEEE rows only.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

URL = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/nightly/core_eia861__yearly_reliability.parquet"
OUT = Path(__file__).resolve().parent.parent / "data" / "national" / "reliability.json"
MIN_CUSTOMERS = 1000  # ignore very small systems when ranking
MIN_POOL = 500  # fewer comparable utilities than this in the latest year means the source table changed
MINUTES_IN_YEAR = 366 * 24 * 60

COLUMNS = {
    "saidi_w_major_event_days_minutes": "saidi_with",
    "saidi_wo_major_event_days_minutes": "saidi_without",
    "saifi_w_major_event_days_customers": "saifi_with",
    "saifi_wo_major_event_days_customers": "saifi_without",
}


def tidy(raw):
    """One row per utility, state and year, preferring the IEEE standard."""
    df = raw.copy()
    df["year"] = pd.to_datetime(df["report_date"]).dt.year
    df = df.rename(columns=COLUMNS)
    df["standard"] = df["standard"].astype("string").str.lower().fillna("unknown")
    df["ieee"] = df["standard"].str.contains("ieee")
    # Blank out values that cannot be outage minutes: more than a year, or the
    # utility's own ID number typed into the field (City of Milan, TN: 12532).
    for measure in ("saidi_with", "saidi_without"):
        bad = (df[measure] > MINUTES_IN_YEAR) | ((df[measure] == df["utility_id_eia"]) & (df["utility_id_eia"] >= 1000))
        df.loc[bad, measure] = float("nan")
    df = df.dropna(subset=["saidi_with", "saidi_without"], how="all")
    df = df.sort_values("ieee", ascending=False).drop_duplicates(["utility_id_eia", "state", "year"])
    if "data_maturity" not in df:
        df["data_maturity"] = None
    keep = ["utility_id_eia", "utility_name_eia", "state", "entity_type", "year", "customers",
            "standard", "ieee", "data_maturity", *COLUMNS.values()]
    return df[keep].sort_values(["year", "utility_id_eia", "state"]).reset_index(drop=True)


def rank(df, year, measure="saidi_with"):
    """Utilities comparable for ranking in one year: IEEE method, not tiny, measure present."""
    pool = df[(df["year"] == year) & df["ieee"] & (df["customers"] >= MIN_CUSTOMERS)].dropna(subset=[measure])
    return pool[pool[measure] >= 0]


def percentile_worse_than(pool, value, measure):
    """Share of utilities in the pool with fewer outage minutes (a better score)."""
    if pool.empty or pd.isna(value):
        return None
    return round(float((pool[measure] < value).mean()) * 100, 1)


def weighted_mean(pool, measure):
    pool = pool.dropna(subset=[measure, "customers"])
    total = pool["customers"].sum()
    return round(float((pool[measure] * pool["customers"]).sum() / total), 1) if total else None


def profile(df, utility_id, state=None):
    """A utility's yearly record against the nation and its peers.

    Peers: same ownership type, between half and double its customer count.
    """
    rows = df[df["utility_id_eia"] == utility_id]
    if state:
        rows = rows[rows["state"] == state]
    out = []
    for row in rows.sort_values("year").itertuples():
        entry = {"year": int(row.year), "customers": _num(row.customers), "standard": row.standard}
        for measure in ("saidi_with", "saidi_without"):
            value = getattr(row, measure)
            pool = rank(df, row.year, measure)
            peers = pool[(pool["entity_type"] == row.entity_type)
                         & pool["customers"].between(row.customers * 0.5, row.customers * 2)]
            entry[measure] = _num(value)
            entry[f"{measure}_national_avg"] = weighted_mean(pool, measure)
            entry[f"{measure}_national_median"] = _num(pool[measure].median())
            entry[f"{measure}_pct_of_utilities_better"] = percentile_worse_than(pool, value, measure)
            entry[f"{measure}_peer_median"] = _num(peers[measure].median())
            entry[f"{measure}_peer_count"] = int(len(peers))
            entry[f"{measure}_pct_of_peers_better"] = percentile_worse_than(peers, value, measure)
        entry["saifi_with"] = _num(row.saifi_with)
        entry["saifi_without"] = _num(row.saifi_without)
        out.append(entry)
    return out


def _num(value):
    return None if pd.isna(value) else round(float(value), 2)


def build(df):
    latest = int(df["year"].max())
    if len(rank(df, latest)) < MIN_POOL:
        raise ValueError(f"only {len(rank(df, latest))} comparable utilities in {latest}; the source table has changed")
    maturity = sorted(str(v) for v in df[df["year"] == latest]["data_maturity"].dropna().unique())
    utilities = []
    for row in df[df["year"] == latest].itertuples():
        utilities.append({
            "id": int(row.utility_id_eia), "name": row.utility_name_eia, "state": row.state,
            "entity_type": row.entity_type, "customers": _num(row.customers), "standard": row.standard,
            "saidi_with": _num(row.saidi_with), "saidi_without": _num(row.saidi_without),
            "saifi_with": _num(row.saifi_with), "saifi_without": _num(row.saifi_without),
        })
    national = []
    for year in sorted(df["year"].unique()):
        pool_with, pool_without = rank(df, year, "saidi_with"), rank(df, year, "saidi_without")
        national.append({
            "year": int(year), "utilities_ranked": int(len(pool_with)),
            "saidi_with_avg": weighted_mean(pool_with, "saidi_with"),
            "saidi_without_avg": weighted_mean(pool_without, "saidi_without"),
            "saidi_with_median": _num(pool_with["saidi_with"].median()),
            "saidi_without_median": _num(pool_without["saidi_without"].median()),
        })
    return {
        "source": "EIA Form 861 reliability data via PUDL (Catalyst Cooperative)",
        "source_url": URL,
        "latest_year": latest,
        # "final" or "provisional", as PUDL labels the latest year; provisional figures can still change.
        "latest_year_data_maturity": maturity,
        "unit": "One row per utility per state. A utility that serves several states is ranked once in each.",
        "ranking_rule": f"IEEE-standard reporters with at least {MIN_CUSTOMERS} customers",
        "national_by_year": national,
        "utilities_latest_year": utilities,
    }


def find(df, name_part):
    names = df["utility_name_eia"].astype("string")
    return df[names.str.contains(name_part, case=False, na=False)]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--find", default="Entergy New Orleans")
    args = parser.parse_args(argv)

    raw = pd.read_parquet(URL)
    if args.inspect:
        print("rows", len(raw))
        print(raw.dtypes.to_string())
        for column in ("standard", "entity_type", "data_maturity"):
            if column in raw:
                print(raw[column].value_counts(dropna=False).head(12).to_string())
        print("years", sorted(pd.to_datetime(raw["report_date"]).dt.year.unique()))
    df = tidy(raw)
    # A utility's name can change over the years; keep its latest name per ID and state.
    matches = (find(df, args.find).sort_values("year")
               .drop_duplicates(["utility_id_eia", "state"], keep="last")[["utility_id_eia", "utility_name_eia", "state"]])
    print(matches.to_string())
    for match in matches.itertuples():
        print(json.dumps(profile(df, match.utility_id_eia, match.state), indent=1))
    if args.inspect:
        return 0
    result = build(df)
    result["profiles"] = {
        f"{m.utility_id_eia}-{m.state}": {"name": m.utility_name_eia, "years": profile(df, m.utility_id_eia, m.state)}
        for m in matches.itertuples()
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", OUT, "utilities", len(result["utilities_latest_year"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
