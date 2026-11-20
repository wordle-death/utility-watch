import React, { useEffect, useMemo, useState } from "react";
import National from "./National.jsx";
import city from "./data/new-orleans.json";
import nationalData from "./data/national.json";

const nationalCount = nationalData.utilities.length;
import { YearBars, MinutesLines } from "./charts.jsx";
import { FLAGS, day, dayTime, millions, short, whole } from "./format.js";
import { CPI_SOURCE, CURRENT_DOLLARS, ICE_BUSINESS_2H, ICE_SOURCE, WATER, advisoryCost, money, outageCost,
  powerPerCustomer, waterForYear } from "./costs.js";

const FIRST_YEAR = 2010; // the one 2009 advisory on record has no map and no count

function waterYears(byYear, builtAt) {
  const thisYear = Number(new Date(builtAt).toLocaleString("en-US", { timeZone: "America/Chicago", year: "numeric" }));
  const years = [];
  for (let year = FIRST_YEAR; year <= thisYear; year++) {
    const e = byYear[year] || {};
    years.push({
      year, advisories: e.advisories || 0, person_hours: e.person_hours || 0,
      from_own_map: e.from_own_map || 0, from_named_area_lookup: e.from_named_area_lookup || 0,
      incomplete: e.advisories_without_person_hours || 0, partial: year === thisYear,
      upper: e.from_advisories_with_an_upper_bound_area || 0,
    });
  }
  return years;
}

function place(title) {
  const cleaned = title
    .replace(/^(expanded\s*[-–]?\s*)?(swb\s+|limited\s+|scheduled\s+)?(precautionary\s+)?boil[- ]water\s+(advisor(y|ies)|order)\s*(in effect\s+)?(issued|called|reinstated)?\s*(only\s+)?(for\s+)?(the\s+|an?\s+)?/i, "")
    .trim();
  return cleaned ? cleaned[0].toUpperCase() + cleaned.slice(1) : "Not named in the first notice";
}

export function Section({ eyebrow, title, children }) {
  const service = { Water: "water", Power: "power", Cost: "cost" }[eyebrow];
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        {service ? <ServiceTag service={service} /> : <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

const SERVICES = {
  water: { name: "Water", icon: "M12 3c-3.5 4.6-6 8-6 11a6 6 0 0 0 12 0c0-3-2.5-6.4-6-11z" },
  power: { name: "Power", icon: "M13 2 5 13.5h5.5L10 22l8.5-12H13z" },
  cost: { name: "Cost", icon: "M12 3v18M16.5 7.5c-.8-1.3-2.4-2-4.5-2-2.6 0-4.3 1.2-4.3 3.1 0 4.4 9 2.4 9 6.9 0 2-1.9 3.2-4.7 3.2-2.3 0-4.1-.9-4.9-2.4" },
};

function ServiceTag({ service }) {
  const s = SERVICES[service];
  return (
    <span className={`service service-${service}`}>
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
        <path d={s.icon} fill={service === "cost" ? "none" : "currentColor"} stroke="currentColor"
          strokeWidth={service === "cost" ? 2 : 1} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {s.name}
    </span>
  );
}

export function Tile({ label, figure, children, service }) {
  return (
    <div className="panel flex flex-col gap-1">
      {service && <ServiceTag service={service} />}
      <span className="small muted">{label}</span>
      <span className="figure">{figure}</span>
      <span className="small muted">{children}</span>
    </div>
  );
}

function Water({ water, years }) {
  const yearOptions = [...new Set(water.advisories.map((a) => a.issued_at.slice(0, 4)))].sort().reverse();
  const [year, setYear] = useState(yearOptions[0]);
  const rows = useMemo(() => water.advisories
    .filter((a) => year === "all" || a.issued_at.startsWith(year))
    .sort((a, b) => (a.issued_at < b.issued_at ? 1 : -1)), [water, year]);
  return (
    <Section eyebrow="Water" title="Boil-water advisories">
      <p className="muted">
        Each bar adds up the hours every affected resident spent under a boil-water advisory that year: the number of
        people in each advisory area multiplied by the hours it lasted. One million hours is about 42,000 people
        without safe tap water for a full day.
      </p>
      <div className="panel flex flex-col gap-3">
        <h3>Hours residents spent without safe tap water, by year</h3>
        <YearBars years={years} />
        <p className="small muted">
          † At least one advisory that year could not be counted, so the bar is too low. {years[years.length - 1].year} is
          the year so far. Estimated: hours come from the Sewerage &amp; Water Board's notices, people from the 2020 Census
          for every year. Figures before 2019 are rougher: the board published no maps then, so they use its later
          drawings of whole areas such as the East Bank.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <h3>Every advisory on record</h3>
        <label className="small muted flex items-center gap-2" htmlFor="year-filter">
          Year
          <select id="year-filter" value={year} onChange={(e) => setYear(e.target.value)}>
            {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
            <option value="all">All years</option>
          </select>
        </label>
      </div>
      <div className="panel scroll-x" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Issued</th><th>Where</th><th className="num">Hours</th><th className="num">People</th>
              <th className="num">People × hours</th><th>Caveats</th><th>Source</th></tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.issued_at + a.title}>
                <td style={{ whiteSpace: "nowrap" }}>{day(a.issued_at)}</td>
                <td style={{ minWidth: 190 }}>{place(a.title)}</td>
                <td className="num">{a.hours == null ? "–" : a.hours.toFixed(0)}</td>
                <td className="num">{a.people == null ? "–" : `${a.upper_bound ? "≤ " : ""}${whole(a.people)}`}</td>
                <td className="num">{a.person_hours == null ? "–" : short(a.person_hours)}</td>
                <td style={{ minWidth: 220 }}>
                  {a.flags.length === 0 ? <span className="muted small">None</span>
                    : a.flags.map((f) => <span className="chip" key={f} style={{ whiteSpace: "normal" }}>{FLAGS[f] || f}</span>)}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <a href={water.release_url + a.release_ids[0]} target="_blank" rel="noreferrer">Notice</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        {water.releases_unattached.length} lift notices have no matching "issued" notice on the board's site
        ({water.releases_unattached.map((r) => day(r.published)).join(", ")}), so those advisories are missing here.
      </p>
    </Section>
  );
}

const LINES = {
  without: [
    { key: "saidi_without", short: "Entergy N.O.", color: "var(--series-1)" },
    { key: "saidi_without_national_avg", short: "U.S. average", color: "var(--series-2)" },
    { key: "saidi_without_peer_median", short: "Similar utilities", color: "var(--series-3)" },
  ],
  with: [
    { key: "saidi_with", short: "Entergy N.O.", color: "var(--series-1)" },
    { key: "saidi_with_national_avg", short: "U.S. average", color: "var(--series-2)" },
    { key: "saidi_with_peer_median", short: "Similar utilities", color: "var(--series-3)" },
  ],
};

function Power({ power, built }) {
  const [mode, setMode] = useState("without");
  const [withPlanned, setWithPlanned] = useState(true);
  const latest = power.years[power.years.length - 1];
  const live = power.live;
  // A rolling week, so the totals mean the same thing whenever the page is read.
  // Measured from the last successful snapshot, not from when the page was built.
  const now = new Date(live.last_success || built).getTime();
  const days = Math.min(7, Math.max(1, Math.floor((now - new Date(live.collecting_since).getTime()) / 864e5)));
  const counted = (e) => withPlanned || !e.planned;
  const recent = live.closed.filter((e) => counted(e) && !e.never_started && e.end
    && now - new Date(e.end).getTime() <= days * 864e5);
  const untrusted = recent.filter((e) => !e.hours_trusted).length;
  const recentHours = recent.reduce((sum, e) => sum + (e.customer_hours || 0), 0);
  // Work that is listed but has not started is not an outage yet.
  const open = live.active.filter((e) => counted(e) && !e.pending).sort((a, b) => (b.customers || 0) - (a.customers || 0));
  const upcoming = live.active.filter((e) => e.pending);
  const customers = (list) => list.reduce((sum, e) => sum + (e.customers || 0), 0);
  const span = days === 7 ? "past 7 days" : days === 1 ? "past day" : `past ${days} days`;
  return (
    <Section eyebrow="Power" title="Outage time compared with the rest of the country">
      <p className="muted">
        Utilities report to the federal government how many minutes the average customer went without power each year.
        In {latest.year}, {power.utility} customers lost {whole(latest.saidi_with)} minutes counting every outage,
        against a national average of {whole(latest.saidi_with_national_avg)}. Leaving out major storms, it was{" "}
        {whole(latest.saidi_without)} minutes against {whole(latest.saidi_without_national_avg)}, and{" "}
        {whole(latest.saidi_without_pct_of_utilities_better)}% of comparable utilities did better. Both views matter:
        storms are when outages hurt most, and the no-storm figure shows how the grid holds up on an ordinary day.
      </p>
      <div className="panel flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3>Outage minutes per customer per year</h3>
          <div className="seg" role="group" aria-label="Major storms">
            <button type="button" aria-pressed={mode === "without"} onClick={() => setMode("without")}>Without major storms</button>
            <button type="button" aria-pressed={mode === "with"} onClick={() => setMode("with")}>With major storms</button>
          </div>
        </div>
        <div className="legend">
          {LINES[mode].map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.short}</span>)}
        </div>
        <MinutesLines rows={power.years} series={LINES[mode]} />
        <p className="small muted">
          Measured: reported by each utility on federal Form EIA-861. "Similar utilities" is the median of{" "}
          {latest.saidi_without_peer_count} investor-owned utilities with half to double the customers.
          {mode === "with" ? " 2021 is Hurricane Ida. Entergy New Orleans did not report a with-storms figure for 2013 or 2014." : ""}
        </p>
        <details>
          <summary>Show the numbers</summary>
          <div className="scroll-x">
            <table>
              <thead><tr><th>Year</th>{LINES[mode].map((s) => <th className="num" key={s.key}>{s.short}</th>)}</tr></thead>
              <tbody>
                {power.years.map((r) => (
                  <tr key={r.year}><td>{r.year}</td>{LINES[mode].map((s) => <td className="num" key={s.key}>{whole(r[s.key])}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>

      <h3 className="pt-2">Outages right now and this week</h3>
      <p className="muted">
        Entergy's outage map shows only what is out at this moment and keeps no history, so this project saves it every
        15 minutes.{days < 7 ? ` It has been saving for ${days} ${days === 1 ? "day" : "days"}; the weekly totals fill in once there is a full week.` : ""}
      </p>
      <div className="seg" role="group" aria-label="Planned work" style={{ alignSelf: "flex-start" }}>
        <button type="button" aria-pressed={withPlanned} onClick={() => setWithPlanned(true)}>Include planned work</button>
        <button type="button" aria-pressed={!withPlanned} onClick={() => setWithPlanned(false)}>Unplanned only</button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Customers without power right now" figure={whole(customers(open))}>
          in {open.length} {open.length === 1 ? "outage" : "outages"}, as of {dayTime(live.last_success)} Central
          {upcoming.length > 0 ? `. ${upcoming.length} planned jobs are listed but have not started` : ""}
        </Tile>
        <Tile label={`Outages that ended, ${span}`} figure={whole(recent.length)}>
          {withPlanned ? "planned work included" : "planned work left out"}; listings that never started are not counted
        </Tile>
        <Tile label={`Customer-hours without power, outages that ended in the ${span}`} figure={whole(recentHours)}>
          estimated from 15-minute snapshots, each outage's full length
          {untrusted > 0 ? `. Leaves out ${untrusted} planned ${untrusted === 1 ? "job" : "jobs"} logged before planned work was timed properly` : ""}
        </Tile>
      </div>
      {open.length > 0 && (
        <div className="panel scroll-x" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Started</th><th className="num">Customers</th><th>Type</th><th>Status</th></tr></thead>
            <tbody>
              {open.map((e) => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{dayTime(e.start)}</td>
                  <td className="num">{whole(e.customers)}</td>
                  <td>{e.kind === "PLANNED_OUTAGE" ? "Planned" : "Unplanned"}</td>
                  <td>{e.status || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// Say when some of the year's advisories are missing from the water cost.
function waterNote(cost) {
  const d = cost.waterDetail;
  return d && d.missing ? ` ${d.advisories - d.missing} of ${d.advisories} advisories counted.` : "";
}

function range(r) {
  if (!r) return "Not yet";
  const lo = money(r.low), hi = money(r.high);
  return lo === hi ? lo : `${lo}–${hi}`;
}

/** Preliminary yearly costs to households: water from the advisory timeline, power from the federal filing. */
function costs(latest, year) {
  const homes = city.households;
  const reason = !homes ? "Household counts are not available yet, so no cost is shown."
    : latest.year !== year ? "Water and power figures for the same year are not both available yet."
    : null;
  if (reason) return { reason };
  const water = waterForYear(city.water.advisories.filter((a) => a.year === year));
  // Power: all outages, storms included. The figure without major storms is shown for context.
  const perCustomer = powerPerCustomer(latest.saidi_with, latest.saifi_with);
  const withoutStorms = powerPerCustomer(latest.saidi_without, latest.saifi_without);
  const w = water && { perHousehold: { low: water.low / homes, high: water.high / homes }, city: { low: water.low, high: water.high } };
  const p = perCustomer != null && {
    perHousehold: { low: perCustomer, high: perCustomer }, city: { low: perCustomer * homes, high: perCustomer * homes },
  };
  const add = (key) => (w && p ? { low: w[key].low + p[key].low, high: w[key].high + p[key].high } : null);
  return {
    year, homes, waterDetail: water, perCustomer, withoutStorms, water: w || {}, power: p || {},
    perHousehold: add("perHousehold"), city: add("city"),
    caidi: latest.saifi_with ? latest.saidi_with / latest.saifi_with : null,
  };
}

const TOP = 10;

/** The most costly single events: every boil-water advisory on record, and every power outage logged so far. */
function Incidents() {
  const [kind, setKind] = useState("water");
  const water = useMemo(() => city.water.advisories
    .map((a) => ({ ...a, cost: advisoryCost(a) }))
    .filter((a) => a.cost)
    // Cost does not yet grow with length, so ties are broken by households × hours.
    .sort((a, b) => b.cost.high - a.cost.high || (b.households * (b.hours || 0)) - (a.households * (a.hours || 0))), []);
  // Unplanned outages only: planned work is often listed several times for one job, with hours estimated from its
  // scheduled start. Outages over a day are left out because the ICE figures stop at 24 hours.
  const logged = city.power.live.closed;
  const power = useMemo(() => logged
    // Entergy files some scheduled work as ordinary outages, with the cause "Scheduled Interruption".
    .filter((e) => !e.planned && !/scheduled interruption/i.test(e.cause || "")
      && e.hours_trusted && !e.never_started && e.duration_hours <= 24)
    .map((e) => ({ ...e, value: outageCost(e) }))
    .filter((e) => e.value)
    .sort((a, b) => b.value.cost - a.value.cost), []);
  const rows = kind === "water" ? water : power;
  return (
    <div className="panel flex flex-col gap-3" style={{ padding: 0 }}>
      <div className="flex flex-wrap items-center justify-between gap-3" style={{ padding: "16px 18px 0" }}>
        <h3>The costliest single events</h3>
        <div className="seg" role="group" aria-label="Service">
          <button type="button" aria-pressed={kind === "water"} onClick={() => setKind("water")}>Boil-water advisories</button>
          <button type="button" aria-pressed={kind === "power"} onClick={() => setKind("power")}>Power outages</button>
        </div>
      </div>
      <p className="small muted" style={{ padding: "0 18px" }}>
        {kind === "water"
          ? `Top ${TOP} of ${rows.length} advisories with a household count, since ${rows.length ? day([...rows].sort((a, b) => (a.issued_at < b.issued_at ? -1 : 1))[0].issued_at) : "–"}. Households × ${money(WATER.low.perHousehold)}–${money(WATER.high.perHousehold)} each. The cost does not yet grow with an advisory's length, so the whole-East-Bank advisories tie; they are listed longest first.`
          : `Top ${TOP} of ${rows.length} unplanned outages up to a day long, out of ${logged.length} logged since ${day(city.power.live.collecting_since)} (planned and scheduled work, and outages longer than a day, are left out for now). Valued as if every customer out were a home, using the ICE cost of an outage that long; businesses cost more, so these are low.`}
      </p>
      <div className="scroll-x">
        <table>
          {kind === "water" ? (
            <>
              <thead><tr><th>Issued</th><th>Where</th><th className="num">Households</th><th className="num">Hours</th>
                <th className="num">Cost to households</th></tr></thead>
              <tbody>
                {rows.slice(0, TOP).map((a, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap" }}>{day(a.issued_at)}</td>
                    <td style={{ minWidth: 220 }}>
                      {place(a.title)}
                      <div>
                        {!a.own_map && <span className="chip" style={{ whiteSpace: "normal" }}>No map of its own; whole-area drawing used, may count too many</span>}
                        {a.flags.filter((f) => f !== "area_from_named_area_lookup").map((f) => (
                          <span className="chip" key={f} style={{ whiteSpace: "normal" }}>{FLAGS[f] || f}</span>
                        ))}
                      </div>
                    </td>
                    <td className="num">{a.upper_bound ? "≤ " : ""}{whole(a.households)}</td>
                    <td className="num">
                      {a.hours == null ? "–" : `${a.flags.includes("remainder_after_partial_lift_not_counted") ? "≥ " : ""}${whole(a.hours)}`}
                    </td>
                    <td className="num">{money(a.cost.low)}–{money(a.cost.high)}</td>
                  </tr>
                ))}
              </tbody>
            </>
          ) : (
            <>
              <thead><tr><th>Started</th><th className="num">Avg. customers out</th><th className="num">Hours</th>
                <th>Cause</th><th className="num">Cost to customers</th></tr></thead>
              <tbody>
                {rows.slice(0, TOP).map((e, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap" }}>{dayTime(e.start)}</td>
                    <td className="num">{whole(e.value.customers)}</td>
                    <td className="num">{e.duration_hours.toFixed(1)}</td>
                    <td>{!e.cause || /^pending$/i.test(e.cause) ? "Not yet given" : e.cause.split(" - ").slice(-1)[0].replace(/\s*\(describe in remarks\)/i, "")}</td>
                    <td className="num">{money(e.value.cost)}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan="5" className="muted">No ended outages logged yet.</td></tr>}
              </tbody>
            </>
          )}
        </table>
      </div>
    </div>
  );
}

function CostMethod({ cost }) {
  if (cost.reason) return <p className="muted">{cost.reason}</p>;
  const d = cost.waterDetail;
  return (
    <div className="flex flex-col gap-4" style={{ maxWidth: "68ch" }}>
      <p className="muted">
        For {cost.year}, in {CURRENT_DOLLARS} (adjusted with the federal{" "}
        <a href={CPI_SOURCE} target="_blank" rel="noreferrer">consumer price index</a>). "Per household" spreads the
        citywide cost across all {whole(cost.homes)} occupied households in Orleans Parish (2020 Census); households
        inside an advisory area paid more, and others nothing.
      </p>
      <div className="flex flex-col gap-2">
        <h3>Water: {range(cost.water.city)} citywide</h3>
        <p className="muted">
          No official standard exists for the cost of a boil-water advisory. The federal standard value (FEMA) covers a
          complete loss of water service, which is far worse. So the range runs between two published studies, neither
          of which measured a boil-water advisory exactly, each giving a cost per household for one event:
        </p>
        <ul className="muted flex flex-col gap-1" style={{ margin: 0, paddingLeft: 18 }}>
          <li><b>Low, {money(WATER.low.perHousehold)}:</b> {WATER.low.source}.{" "}
            <a href={WATER.low.url} target="_blank" rel="noreferrer">Source</a></li>
          <li><b>High, {money(WATER.high.perHousehold)}:</b> {WATER.high.source}.{" "}
            <a href={WATER.high.url} target="_blank" rel="noreferrer">Source</a></li>
        </ul>
        {!d ? <p className="muted">None of the year's advisories could be counted, so no water cost is shown.</p>
          : d.advisories === 0 ? <p className="muted">No boil-water advisories were issued this year.</p> : (
          <p className="muted">
            Multiplied by the households inside each advisory area: {whole(d.householdAdvisories)} across{" "}
            {d.advisories - d.missing} of the year's {d.advisories} advisories
            {d.missing ? ` (${d.missing} had no household count, so the total is too low)` : ""}.
            {d.inAdvisoriesWithUpperBound ? ` ${whole(d.inAdvisoriesWithUpperBound)} of those households are in advisories` +
              " that include a very small area counted generously, which pushes the total up slightly." : ""}
            {d.concurrentAdvisories ? " Advisories that overlapped in time are each counted in full, so some households" +
              " are counted twice." : ""}
            {" "}Every household is assumed to comply, and a longer advisory is not yet counted as costing more.
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <h3>Power: {range(cost.power.city)} citywide</h3>
        {cost.perCustomer == null ? <p className="muted">Entergy's outage figures for {cost.year} are not available,
          so no power cost is shown.</p> : <p className="muted">
          The Department of Energy's Interruption Cost Estimate (ICE) Calculator, a widely used federal tool, gives a
          residential customer's cost for one outage by its length. Entergy New Orleans reported to the federal
          government how many outages its average customer had in {cost.year} and how many minutes they lasted in
          total; from those, the average outage lasted {whole(cost.caidi)} minutes. The yearly cost is the number of
          outages times the ICE cost of an average-length outage: {money(cost.perCustomer)} per customer, storms
          included ({money(cost.withoutStorms)} leaving out major storms). Each household is counted as one residential
          customer; Entergy's {whole(city.power.years.find((y) => y.year === cost.year)?.customers)} customers also include
          businesses, which are not counted here.{" "}
          <a href={ICE_SOURCE.url} target="_blank" rel="noreferrer">Source</a>
        </p>}
      </div>
      <div className="flex flex-col gap-2">
        <h3>Not included yet</h3>
        <ul className="muted flex flex-col gap-1" style={{ margin: 0, paddingLeft: 18 }}>
          <li>Businesses. ICE puts one business customer's cost of a two-hour outage at about {money(ICE_BUSINESS_2H)}{" "}
            (<a href={ICE_SOURCE.url} target="_blank" rel="noreferrer">source</a>), so this is likely the largest missing
            piece.</li>
          <li>School and daycare closures during boil-water advisories, and the lost work and wages that follow.</li>
          <li>The spread of outage lengths. Pricing every outage at the average length can push the estimate either
            way, and ICE does not cover outages longer than a day.</li>
          <li>Illness, which is left out on purpose: these advisories are precautionary.</li>
        </ul>
      </div>
    </div>
  );
}

function NewOrleans() {
  const years = useMemo(() => waterYears(city.water.by_year, city.built_at), []);
  const current = years[years.length - 1];
  const latest = city.power.years[city.power.years.length - 1];
  // Both rows use the last full year the power data covers, so water and power are on the same footing.
  const waterYear = years.find((y) => y.year === latest.year) || current;
  const powerHours = (latest.saidi_with * latest.customers) / 60;
  const cost = useMemo(() => costs(latest, waterYear.year), [latest, waterYear]);
  // Say how many of the year's advisories are in the total when some could not be counted.
  const counted = (y) => (y.incomplete ? ` ${y.advisories - y.incomplete} of ${y.advisories} advisories counted.` : "");
  const borrowedShare = Math.round((years.reduce((sum, y) => sum + y.from_named_area_lookup, 0)
    / years.reduce((sum, y) => sum + y.person_hours, 0)) * 100);
  return (
    <main className="wrap flex flex-col gap-12">
      <header className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="eyebrow">Utility Watch · {city.city}</span>
          <h1>How often New Orleans loses power and safe water</h1>
          <p className="muted">Built from public records: the water board's own notices and maps, the power company's
            federal filings and live outage map, and the Census. Outage map as of {dayTime(city.power.live.last_success || city.built_at)} Central.</p>
        </div>
        <div className="flex flex-col gap-2">
          <span className="eyebrow">For the average resident, {latest.year}</span>
          <div className="grid gap-3 sm:grid-cols-3">
            <Tile service="water" label="Hours under a boil-water advisory, per resident" figure={whole(waterYear.person_hours / city.residents)}>
              estimated average: some neighborhoods had none, others several days.{counted(waterYear)}{" "}
              {current.year} so far: {whole(current.person_hours / city.residents)}
            </Tile>
            <Tile service="power" label="Minutes without power, per customer" figure={whole(latest.saidi_with)}>
              storms included; U.S. average {whole(latest.saidi_with_national_avg)}. Without major storms:{" "}
              {whole(latest.saidi_without)}, U.S. average {whole(latest.saidi_without_national_avg)}
            </Tile>
            <Tile service="cost" label="Cost per household, preliminary" figure={range(cost.perHousehold)}>
              {cost.reason ? cost.reason : <>water {range(cost.water.perHousehold)} plus power{" "}
              {range(cost.power.perHousehold)} (per customer); estimated, in 2026 dollars.{waterNote(cost)}{" "}
              <a href="#cost">How</a></>}
            </Tile>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="eyebrow">For the whole city, {latest.year}</span>
          <div className="grid gap-3 sm:grid-cols-3">
            <Tile service="water" label="Hours residents spent under a boil-water advisory" figure={`${millions(waterYear.person_hours)}`}>
              estimated: people in each advisory area × the hours it lasted.{counted(waterYear)}
              {waterYear.upper ? ` ${millions(waterYear.upper)} comes from advisories that include a very small area, counted generously.` : ""}{" "}
              {current.year} so far: {millions(current.person_hours)}
            </Tile>
            <Tile service="power" label="Hours customers spent without power" figure={whole(Math.round(powerHours / 1000) * 1000)}>
              estimated from Entergy's federal filing: minutes per customer × {whole(latest.customers)} customers,
              storms included
            </Tile>
            <Tile service="cost" label="Cost to households citywide, preliminary" figure={range(cost.city)}>
              {cost.reason ? cost.reason : <>water {range(cost.water.city)} plus power {range(cost.power.city)}, in 2026
              dollars; businesses, schools and daycares not yet included.{waterNote(cost)} <a href="#cost">How</a></>}
            </Tile>
          </div>
        </div>
      </header>

      <Water water={city.water} years={years} />
      <hr className="rule" />
      <Power power={city.power} built={city.built_at} />
      <hr className="rule" />

      <Section eyebrow="Cost" title="What this costs households">
        <div id="cost" className="note">Preliminary. These figures use published studies as stand-ins until the method has
          been reviewed, and they leave out costs to businesses, schools and daycares. Treat them as a first range, not a
          finding.</div>
        <Incidents />
        <CostMethod cost={cost} />
      </Section>
      <hr className="rule" />

      <Section eyebrow="Method" title="Where the numbers come from">
        <ul className="muted flex flex-col gap-2" style={{ margin: 0, paddingLeft: 18, maxWidth: "68ch" }}>
          <li><b>Advisory start and end</b> are the times on the Sewerage &amp; Water Board's "issued" and "lifted" notices.
            When part of an area was released early, the clock stops at the first lift.</li>
          <li><b>People</b> are 2020 Census residents of blocks inside the board's map of the advisory. Very small areas
            count every block they touch and are shown with "≤".</li>
          <li><b>Power comparison</b> uses {city.power.source}. Rankings include {city.power.ranking_rule.replace(/^IEEE-standard reporters/, "utilities that report under the IEEE standard")};
            {" "}{city.power.latest_year} data is {(city.power.latest_year_data_maturity || []).join(", ") || "unlabeled"}.</li>
          <li><b>Advisories without a map</b>, including every one before 2019, use the board's drawing of the whole
            named area (East Bank, West Bank, Lower 9th Ward or Venetian Isles). That is {borrowedShare}% of all
            the resident-hours shown, and the East Bank drawing likely overstates some of them.</li>
          <li><b>Live outages</b> are closed at the midpoint between the last snapshot that showed them and the first that
            did not.</li>
        </ul>
        <p className="small muted">
          Sources: <a href="https://www.swbno.org/PressReleases" target="_blank" rel="noreferrer">S&amp;WB press releases</a>,{" "}
          <a href="https://www.eia.gov/electricity/data/eia861/" target="_blank" rel="noreferrer">EIA Form 861</a> via{" "}
          <a href="https://catalyst.coop/pudl/" target="_blank" rel="noreferrer">PUDL</a>,{" "}
          <a href="https://www.census.gov/programs-surveys/decennial-census/decade/2020/2020-census-main.html" target="_blank" rel="noreferrer">2020 Census</a>,{" "}
          <a href="https://github.com/wordle-death/utility-watch" target="_blank" rel="noreferrer">code and data</a>.
        </p>
      </Section>
    </main>
  );
}


function Home() {
  return (
    <main className="wrap flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <span className="eyebrow">Utility Watch</span>
        <h1>How often the power and safe water go out, and for how long</h1>
        <p className="muted">Utilities publish outage maps that forget yesterday and notices that are hard to add up.
          This site keeps the record and puts numbers on it, using public data only.</p>
      </header>
      <div className="grid gap-3 sm:grid-cols-2">
        <a className="panel flex flex-col gap-1" href="#new-orleans" style={{ textDecoration: "none", color: "inherit" }}>
          <span className="eyebrow">City page</span>
          <h3>New Orleans</h3>
          <span className="small muted">Every boil-water advisory the water board has published, power outage time against the nation,
            and outages as they happen.</span>
          <span className="small" style={{ color: "var(--accent)" }}>Open the New Orleans page →</span>
        </a>
        <a className="panel flex flex-col gap-1" href="#national" style={{ textDecoration: "none", color: "inherit" }}>
          <span className="eyebrow">National</span>
          <h3>Look up your power company</h3>
          <span className="small muted">Outage minutes per customer for {whole(nationalCount)} U.S. utilities, and how each
            compares with the rest.</span>
          <span className="small" style={{ color: "var(--accent)" }}>Open the national comparison →</span>
        </a>
      </div>
      <p className="small muted">More cities, a water comparison and cost estimates are in the works.</p>
    </main>
  );
}

const ROUTES = { "": Home, "new-orleans": NewOrleans, national: National };
const PAGE_NAMES = { "": "Home", "new-orleans": "New Orleans", national: "National" };
// Collection runs every 15 minutes (power) and hourly (water), but the saved "last success" time is only
// refreshed about hourly and the page is rebuilt hourly, so a healthy page can show times two hours old.
const STALE_HOURS = 6;

function hoursSince(iso) {
  return iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : Infinity;
}

/** Warn when the copy of the data on this page has stopped updating. */
function Stale() {
  const late = [
    ["live power outage map", city.freshness.power],
    ["boil-water advisory map", city.freshness.water],
  ].filter(([, when]) => hoursSince(when) > STALE_HOURS);
  if (!late.length) return null;
  const oldest = Math.max(...late.map(([, when]) => hoursSince(when)));
  const age = oldest === Infinity ? "an unknown time" : oldest >= 48 ? `${Math.floor(oldest / 24)} days` : `${Math.floor(oldest)} hours`;
  return (
    <div className="wrap" style={{ paddingBlock: "14px 0" }}>
      <div className="note" role="status">
        Our copy of the {late.map(([name]) => name).join(" and ")} was last updated {age} ago, so "right now"
        figures may be out of date. Collection may have paused; it catches up when it resumes.
      </div>
    </div>
  );
}

const REPO = "https://github.com/wordle-death/utility-watch";

function Footer({ route }) {
  const report = `${REPO}/issues/new?template=correction.yml&page=${encodeURIComponent(PAGE_NAMES[route] ?? "Home")}`;
  return (
    <footer className="wrap" style={{ paddingBlock: "0 40px" }}>
      <hr className="rule" />
      <div className="flex flex-col gap-2 small muted" style={{ paddingTop: 18 }}>
        <p>
          Spot something wrong? <a href={report} target="_blank" rel="noreferrer">Report a correction</a>. Reports go to
          the project's public issue list on GitHub, which needs a free GitHub account.
        </p>
        <p>
          Figures marked "estimated" combine public records with our own method, described on each page; the rest are
          as the source reported them.
        </p>
        <p>
          Utility Watch is an independent project built from public records. It is not affiliated with any utility or
          government agency. <a href={REPO} target="_blank" rel="noreferrer">Code and data</a> are open.
        </p>
      </div>
    </footer>
  );
}

export default function App() {
  const read = () => window.location.hash.replace(/^#/, "");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const Page = ROUTES[route] || Home;
  const link = (name, label) => (
    <a href={`#${name}`} aria-current={route === name ? "page" : undefined}>{label}</a>
  );
  return (
    <>
      <nav className="topnav">
        <div className="topnav-inner">
          <a href="#" className="brand">Utility Watch</a>
          <div className="flex gap-4">{link("new-orleans", "New Orleans")}{link("national", "National")}</div>
        </div>
      </nav>
      {import.meta.env.VITE_PREVIEW === "1" && (
        <div className="wrap" style={{ paddingBlock: "14px 0" }}>
          <div className="note">Private preview. Not published. Figures are estimates still under review.</div>
        </div>
      )}
      {route === "new-orleans" && <Stale />}
      <Page route={route} />
      <Footer route={route} />
    </>
  );
}
