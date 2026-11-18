// Gather the collected data one city page needs into a single small file.
// Nothing is calculated here except simple sums of the live outage log;
// every other figure is copied as published in data/.
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const data = (...parts) => join(root, "data", ...parts);
const read = (path) => JSON.parse(readFileSync(path, "utf8"));

const timeline = read(data("water", "swbno", "advisory_timeline.json"));
const national = read(data("national", "reliability.json"));
const powerStatus = read(data("status-power.json"));
const waterStatus = read(data("status-water.json"));

const advisories = timeline.advisories.map((a) => ({
  issued_at: a.issued_at,
  ended_at: a.partial_lift_at || a.lifted_at,
  title: a.title,
  hours: a.hours,
  people: a.people,
  person_hours: a.person_hours,
  own_map: a.area_keys.length > 0,
  upper_bound: a.upper_bound,
  flags: a.flags,
  release_ids: a.release_ids,
}));

const source = "entergy-nola";
const eventsDir = data("power", source, "events");
const closed = existsSync(eventsDir)
  ? readdirSync(eventsDir).filter((f) => f.endsWith(".jsonl")).sort().flatMap((f) =>
      readFileSync(join(eventsDir, f), "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line)))
  : [];
const active = Object.values(read(data("power", source, "active.json")).events || {});
// Planned work logged before the collector learned to wait for "in progress" has inflated hours:
// those records lack in_progress_first_seen, and their hours are left out.
const isPlanned = (e) => e.planned === true || e.kind === "PLANNED_OUTAGE";
// Planned records logged by the older collector (no "pending" field) carry hours counted while only scheduled.
const hoursTrusted = (e) => !isPlanned(e) || ("pending" in e && !e.hours_may_include_scheduled_time);
// Planned work that vanished without ever being seen under way was never an outage.
const neverStarted = (e) => (e.opened_pending === true && !(e.in_progress_hours > 0))
  || (isPlanned(e) && !("pending" in e) && String(e.status || "").toUpperCase() === "SCHEDULED");
const slim = (e) => ({
  never_started: neverStarted(e),
  planned: isPlanned(e), pending: e.pending === true || (isPlanned(e) && String(e.status || "").toUpperCase() === "SCHEDULED"),
  hours_trusted: hoursTrusted(e),
  id: e.id, start: e.start, end: e.end || null, end_basis: e.end_basis || null,
  customers: e.customers ?? null, peak_customers: e.peak_customers ?? e.customers ?? null, customer_hours: hoursTrusted(e) ? e.customer_hours ?? null : null,
  duration_hours: e.duration_hours ?? null, cause: e.cause, kind: e.kind, status: e.status,
  max_gap_minutes: e.max_gap_minutes, lat: e.lat, lon: e.lon,
});
const firstSeen = [...closed, ...active].map((e) => e.first_seen).filter(Boolean).sort()[0] || null;

// Residents of the parish, for per-resident averages: the same 2020 Census blocks the advisory counts use.
const residents = read(data("census", "blocks-22071.json")).blocks.reduce((sum, b) => sum + b.people, 0);

// When each feed last succeeded, so the page can warn a visitor when collection has stopped.
const freshness = {
  power: active.map((e) => e.last_seen).filter(Boolean).sort().pop() ?? powerStatus?.[source]?.last_success ?? null,
  water: waterStatus?.swbno?.last_success ?? null,
};

const out = {
  freshness,
  built_at: new Date().toISOString(),
  city: "New Orleans",
  residents,
  water: {
    utility: "Sewerage & Water Board of New Orleans",
    method: timeline.method,
    by_year: timeline.by_year,
    advisories,
    releases_unattached: (timeline.releases_unattached || []).filter((r) => r.reason !== "archive_posted_in_bulk"),
    release_url: "https://www.swbno.org/PressReleases/Details/",
  },
  power: {
    utility: "Entergy New Orleans",
    latest_year: national.latest_year,
    latest_year_data_maturity: national.latest_year_data_maturity,
    ranking_rule: national.ranking_rule,
    source: national.source,
    years: national.profiles["13478-LA"].years,
    live: {
      collecting_since: firstSeen,
      // The newest snapshot actually saved; the status file is refreshed only hourly.
      last_success: active.map((e) => e.last_seen).filter(Boolean).sort().pop()
        ?? powerStatus?.[source]?.last_success ?? null,
      closed: closed.map(slim),
      active: active.map(slim),
    },
  },
};
// National lookup: every utility's latest year, with its standing among comparable utilities.
// The comparison pool follows national/reliability.py: IEEE-method reporters with at least 1,000 customers.
// Same test as national/reliability.py, which treats any standard naming IEEE as comparable.
const isIeee = (u) => String(u.standard || "").includes("ieee");
const comparable = (u, measure) => isIeee(u) && u.customers >= 1000 && u[measure] != null && u[measure] >= 0;
const shareBetter = (u, measure) => {
  if (!comparable(u, measure)) return null;
  const pool = national.utilities_latest_year.filter((v) => comparable(v, measure));
  return Math.round((pool.filter((v) => v[measure] < u[measure]).length / pool.length) * 1000) / 10;
};
const nationalOut = {
  built_at: out.built_at,
  latest_year: national.latest_year,
  latest_year_data_maturity: national.latest_year_data_maturity,
  source: national.source,
  by_year: national.national_by_year,
  utilities: national.utilities_latest_year.map((u) => ({
    id: u.id, name: u.name, state: u.state, type: u.entity_type, customers: u.customers,
    with: u.saidi_with, without: u.saidi_without, ieee: isIeee(u),
    better_with: shareBetter(u, "saidi_with"), better_without: shareBetter(u, "saidi_without"),
  })),
};

mkdirSync(join(root, "site", "src", "data"), { recursive: true });
writeFileSync(join(root, "site", "src", "data", "national.json"), JSON.stringify(nationalOut));
writeFileSync(join(root, "site", "src", "data", "new-orleans.json"), JSON.stringify(out));
console.log("snapshot:", advisories.length, "advisories,", closed.length, "closed outages,", active.length, "open");
