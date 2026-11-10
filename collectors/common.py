"""Shared helpers: HTTP, time parsing, and JSON file storage.

Standard library only, so the collectors run on a bare GitHub Actions runner.
"""

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
USER_AGENT = "utility-watch/0.1 (+https://github.com/wordle-death/utility-watch)"


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    """UTC ISO 8601 string with a Z suffix, or None."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    """Parse a string written by iso(); returns an aware UTC datetime or None."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def from_epoch_ms(value):
    if value in (None, "", 0):
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(microsecond=0)


def from_local(value, tz_name, fmt=None):
    """Parse a local-time string with no offset, as many utility feeds publish.

    fmt=None means ISO 8601. If the string already has an offset, it is kept.
    """
    if not value:
        return None
    value = str(value).strip()
    dt = datetime.strptime(value, fmt) if fmt else datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.astimezone(timezone.utc).replace(microsecond=0)


def fetch_json(url, params=None, headers=None, timeout=30, retries=2):
    """GET a URL and decode JSON, retrying transient failures."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json, */*;q=0.5"}
    request_headers.update(headers or {})
    error = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except Exception as exc:  # network errors, HTTP errors, bad JSON
            error = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise error


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def dumps(obj):
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path, obj):
    """Write JSON only if the content changed. Returns True when the file changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dumps(obj)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def append_jsonl(path, rows):
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def short_hash(*parts):
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def first_key(record, *keys):
    """Return the first present, non-empty value among candidate keys."""
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
