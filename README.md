# utility-watch

How often American cities lose power and safe water, how many households it reaches, for how long, and what it costs.

This repo is at its first stage: **collectors** that save live outage and boil-water data on a schedule. Utilities' live maps show only what is out right now and keep no public history, so history starts when collection starts.

## What is collected

| Source | City | What | How often |
| --- | --- | --- | --- |
| Entergy New Orleans (DataCapable map) | New Orleans | Power outages: customers, start, estimated restore, cause, location | Every 15 minutes |
| Idaho Power | Boise | Power outages, including reported end times and ZIP codes | Every 15 minutes |
| MLGW | Memphis | Power outages: customers, start, cause, location | Every 15 minutes |
| SRP | Phoenix area | Power outages: customers, cause, location | Every 15 minutes |
| Sewerage & Water Board (ArcGIS layer) | New Orleans | Every boil-water advisory area since 2019, as map polygons | Hourly |

Not yet collected: APS (Phoenix) and Portland General Electric (Portland). Their feeds have not been identified.

## Where the data goes

- `data/power/<source>/active.json`: outages open as of the last run.
- `data/power/<source>/events/YYYY-MM.jsonl`: one line per closed outage, with start, end, peak customers and customer-hours.
- `data/water/swbno/advisories.geojson`: every advisory area S&WB has published. Areas S&WB later removes stay here, marked `removed_at`.
- `data/water/swbno/changes.jsonl`: every advisory added, changed, removed or restored.
- `data/status-power.json`, `data/status-water.json`: when each source last succeeded or failed.

### How outage ends are measured

Most feeds drop an outage when power returns, without saying when. An outage that disappears is closed at the midpoint between the last run that saw it and the first that did not; both times are kept in `end_window`. Customer-hours are added up between runs using the customer count from the earlier run, and hours before the first sighting are kept in a separate field. Idaho Power reports its own end times, and those are used instead. `max_gap_minutes` records the longest stretch between sightings, so outages measured through delayed runs can be flagged.

### Safeguards

- A feed whose response is missing its expected fields, or lists an outage without an ID, is treated as a failed run, not as "no outages."
- If a feed suddenly shows no outages while three or more were open, nothing is closed until the next run confirms it.
- A source that fails keeps running on schedule. It sends one failure email after 6 hours without a successful run, not one per run.

## National power comparison

`national/reliability.py` downloads the federal EIA Form 861 reliability table (via PUDL) and writes `data/national/reliability.json`: every utility's latest outage minutes per customer (SAIDI) and outage count per customer (SAIFI), national averages by year since 2013, and a year-by-year profile of selected utilities against the nation and their peers. Rankings use only utilities that report under the IEEE standard and have at least 1,000 customers. Peers are utilities of the same ownership type with between half and double the customer count. The customer-weighted national averages match EIA's published figures. `national.yml` refreshes it monthly.

## Running locally

Python 3.11 or newer, no packages needed.

```
python -m unittest discover -s tests -t .
python -m collectors.run power --dry-run   # fetch and parse, write nothing
python -m collectors.run power             # fetch and update data/
python -m collectors.run water
```

## Scheduled runs

`collect-power.yml` runs every 15 minutes and `collect-water.yml` hourly; each commits any changes to `main`. `tests.yml` runs the tests on every pull request and checks the live feeds on every branch push.
