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
const slim = (e) => ({
  id: e.id, start: e.start, end: e.end || null, end_basis: e.end_basis || null,
  customers: e.peak_customers ?? e.customers, customer_hours: e.customer_hours ?? null,
  duration_hours: e.duration_hours ?? null, cause: e.cause, kind: e.kind, status: e.status,
  max_gap_minutes: e.max_gap_minutes, lat: e.lat, lon: e.lon,
});
const firstSeen = [...closed, ...active].map((e) => e.first_seen).filter(Boolean).sort()[0] || null;

const out = {
  built_at: new Date().toISOString(),
  city: "New Orleans",
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
      last_success: powerStatus?.sources?.[source]?.last_success ?? powerStatus?.[source]?.last_success ?? null,
      closed: closed.map(slim),
      active: active.map(slim),
    },
  },
};
mkdirSync(join(root, "site", "src", "data"), { recursive: true });
writeFileSync(join(root, "site", "src", "data", "new-orleans.json"), JSON.stringify(out));
console.log("snapshot:", advisories.length, "advisories,", closed.length, "closed outages,", active.length, "open");
