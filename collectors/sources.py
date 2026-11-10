"""Feeds for each utility, and parsers that turn them into one outage format.

Normalized outage fields: id, start, end (restored only), customers, cause,
status, kind, lat, lon, zips, places, etr. Times are aware UTC datetimes.

Parsers are separate from fetching so they can be tested on saved samples.
Field names were read from each live feed in November 2026; where a feed's
field names were not confirmed, parsers try several likely names.
"""

from .power import FeedError
from .common import (
    fetch_json,
    first_key,
    from_epoch_ms,
    from_local,
    short_hash,
    to_int,
)

# First raw record per feed from the latest fetch, for dry-run inspection.
RAW_SAMPLES = {}

# --- Entergy New Orleans (DataCapable platform) ---------------------------

ENTERGY_NOLA_URL = "https://entergy.datacapable.com/datacapable/v2/p/entergy/r/nola/map/events"


def _require(condition, message):
    if not condition:
        raise FeedError(message)


def parse_entergy(payload):
    _require(isinstance(payload, list), "Entergy feed did not return a list")
    events = []
    for item in payload:
        events.append(
            {
                # Entergy's ID stays the same if the outage's start is revised.
                "id": item.get("id"),
                "start": from_epoch_ms(item.get("startTime")),
                "etr": from_epoch_ms(item.get("etrTime")),
                "customers": to_int(item.get("numPeople")),
                "cause": item.get("cause") or None,
                "status": item.get("status"),
                "kind": item.get("type"),
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
            }
        )
    return events


def collect_entergy_nola():
    return parse_entergy(fetch_json(ENTERGY_NOLA_URL)), None


# --- Idaho Power (Boise) --------------------------------------------------

IDAHO_CURRENT_URL = "https://apiedge.idahopower.com/api/Outage/GetCurrentOutageInformation"
IDAHO_RESTORED_URL = "https://apiedge.idahopower.com/api/Outage/GetRestoredOutageInformation"
IDAHO_TZ = "America/Boise"
IDAHO_HEADERS = {"Origin": "https://tools.idahopower.com", "Referer": "https://tools.idahopower.com/Outage"}


def _idaho_item(item):
    return {
        "id": first_key(item, "osiOutageId", "outageId", "id"),
        "start": from_local(first_key(item, "outageStartDate", "startDate"), IDAHO_TZ),
        "end": from_local(first_key(item, "outageEndDate", "endDate"), IDAHO_TZ),
        "customers": to_int(first_key(item, "totalAffectedPremises", "affectedPremises", "customersAffected")),
        "cause": first_key(item, "probableCauseCodeDisplayName", "cause"),
        "status": first_key(item, "energizationStatusDisplayName", "outageStatusDisplayName"),
        "kind": "PLANNED" if item.get("isPlannedOutage") else "UNPLANNED",
        "lat": first_key(item, "latitude", "lat"),
        "lon": first_key(item, "longitude", "lon", "lng"),
        "zips": item.get("outageZipNumbers") or [],
        "places": item.get("outageCityNames") or [],
    }


def parse_idaho_current(payload):
    """Live outages use "oms" field names; their IDs match the restored list's."""
    _require(isinstance((payload or {}).get("object"), dict) and isinstance(payload["object"].get("outages"), list),
             "Idaho Power current feed is missing object.outages")
    events = []
    for item in payload["object"]["outages"]:
        events.append(
            {
                "id": first_key(item, "omsOutageId", "osiOutageId", "outageId"),
                "start": from_local(first_key(item, "omsOutageStartDate", "outageStartDate"), IDAHO_TZ),
                "etr": from_local(item.get("omsEstimatedOutageRestorationDate"), IDAHO_TZ),
                "customers": to_int(first_key(item, "omsCustomerCount", "totalAffectedPremises")),
                "cause": item.get("probableCause"),
                "status": item.get("omsStatusDescription"),
                "kind": "PLANNED" if item.get("isPlannedOutage") else "UNPLANNED",
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
                "zips": [z.get("outageZipName") for z in item.get("outageZip") or [] if z.get("outageZipName")],
                "places": [c.get("outageCityName") for c in item.get("outageCity") or [] if c.get("outageCityName")],
            }
        )
    return events


def parse_idaho_restored(payload):
    _require(isinstance((payload or {}).get("list"), list), "Idaho Power restored feed is missing list")
    return [_idaho_item(item) for item in payload["list"]]


def collect_idaho_power():
    raw = fetch_json(IDAHO_CURRENT_URL, headers=IDAHO_HEADERS)
    outages = ((raw or {}).get("object") or {}).get("outages") or []
    RAW_SAMPLES["idaho-power"] = outages[0] if outages else None
    current = parse_idaho_current(raw)
    restored = parse_idaho_restored(fetch_json(IDAHO_RESTORED_URL, headers=IDAHO_HEADERS))
    return current, restored


# --- MLGW (Memphis) -------------------------------------------------------

MLGW_URL = "https://outagemap.mlgw.org/geojson.php"
MLGW_TZ = "America/Chicago"


def parse_mlgw(payload):
    _require(isinstance((payload or {}).get("features"), list), "MLGW feed is missing features")
    events = []
    for feature in payload["features"]:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        events.append(
            {
                "id": props.get("OUTAGE_NO"),
                "start": from_local(props.get("TIME_STAMP"), MLGW_TZ, "%m/%d/%Y %I:%M:%S %p"),
                "etr": None,
                "customers": to_int(props.get("CUR_CUST_AFF")),
                "cause": (props.get("OUT_CAUSE") or "").strip() or None,
                "status": props.get("STATUS"),
                "kind": None,
                "lon": coords[0],
                "lat": coords[1],
            }
        )
    return events


def collect_mlgw():
    return parse_mlgw(fetch_json(MLGW_URL, headers={"Referer": "https://outagemap.mlgw.org/"})), None


# --- SRP (Phoenix area) ---------------------------------------------------

SRP_URL = "https://myaccount.srpnet.com/myaccountapi/api/outages/getall"
SRP_TZ = "America/Phoenix"


def parse_srp(payload):
    _require(isinstance(payload, list), "SRP feed did not return a list")
    events = []
    for item in payload:
        lat, lon = item.get("latitude"), item.get("longitude")
        start_raw = first_key(item, "outageBeginTime", "outageStartTime", "beginTime", "startTime", "outageBegan")
        explicit_id = first_key(item, "outageId", "outageID", "id", "eventId", "incidentId")
        events.append(
            {
                # If SRP ever omits its ID, fall back to location plus start time.
                "id": explicit_id
                or short_hash(round(float(lat or 0), 4), round(float(lon or 0), 4), start_raw),
                "start": from_local(start_raw, SRP_TZ) if start_raw else None,
                "etr": None,
                "customers": to_int(item.get("numberCustomersAffected")),
                "cause": item.get("outageProblem"),
                "status": None,
                "kind": "PLANNED" if item.get("isMaintenanceOutage") else "UNPLANNED",
                "lat": lat,
                "lon": lon,
                "places": [item["crossRoadText"].strip()] if item.get("crossRoadText") else [],
            }
        )
    return events


def collect_srp():
    headers = {"Referer": "https://myaccount.srpnet.com/power/myaccount/outages"}
    return parse_srp(fetch_json(SRP_URL, headers=headers)), None


POWER_SOURCES = {
    "entergy-nola": collect_entergy_nola,
    "idaho-power": collect_idaho_power,
    "mlgw": collect_mlgw,
    "srp": collect_srp,
}


# --- S&WB New Orleans boil-water advisory areas (ArcGIS) ------------------

SWBNO_LAYER = (
    "https://services1.arcgis.com/cYAR0YQ3Tr6M4FbT/arcgis/rest/services/"
    "SWB_Advisory_Area_VIEW/FeatureServer/0/query"
)


def fetch_swbno(page_size=500, max_pages=20):
    """Fetch every advisory area, page by page, so a capped response is never mistaken for the full layer."""
    features = []
    for page in range(max_pages):
        payload = fetch_json(
            SWBNO_LAYER,
            params={"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson",
                    "orderByFields": "OBJECTID", "resultOffset": page * page_size,
                    "resultRecordCount": page_size},
        )
        _require(isinstance((payload or {}).get("features"), list), "S&WB layer response has no features list")
        features.extend(payload["features"])
        more = payload.get("exceededTransferLimit") or (payload.get("properties") or {}).get("exceededTransferLimit")
        if not more and len(payload["features"]) < page_size:
            return {"type": "FeatureCollection", "features": features}
    raise FeedError("S&WB layer still had more pages after the page limit")
