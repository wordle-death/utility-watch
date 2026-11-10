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
- `data/water/swbno/advisories.geojson`: the current copy of S&WB's advisory layer.
- `data/water/swbno/changes.jsonl`: every advisory added, changed or removed.
- `data/status.json`: when each source last succeeded or failed.

### How outage ends are measured

Most feeds drop an outage when power returns, without saying when. An outage that disappears is closed at the midpoint between the last run that saw it and the first that did not; both times are kept in `end_window`. Customer-hours are added up between runs using the customer count from the earlier run. Idaho Power reports its own end times, and those are used instead.

## Running locally

Python 3.11 or newer, no packages needed.

```
python -m unittest discover -s tests -t .
python -m collectors.run power --dry-run   # fetch and parse, write nothing
python -m collectors.run power             # fetch and update data/
python -m collectors.run water
```

## Scheduled runs

`.github/workflows/collect.yml` runs power every 15 minutes and water hourly, then commits any changes to `main`. `tests.yml` runs the tests on every pull request and checks the live feeds on every branch push.
