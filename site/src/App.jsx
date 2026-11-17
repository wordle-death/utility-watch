import React, { useEffect, useMemo, useState } from "react";
import National from "./National.jsx";
import city from "./data/new-orleans.json";
import nationalData from "./data/national.json";

const nationalCount = nationalData.utilities.length;
import { YearBars, MinutesLines } from "./charts.jsx";
import { FLAGS, day, dayTime, millions, short, whole } from "./format.js";

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
  return cleaned ? cleaned[0].toUpperCase() + cleaned.slice(1) : "Place not named in the notice";
}

export function Section({ eyebrow, title, children }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function Tile({ label, figure, children }) {
  return (
    <div className="panel flex flex-col gap-1">
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

function NewOrleans() {
  const years = useMemo(() => waterYears(city.water.by_year, city.built_at), []);
  const current = years[years.length - 1];
  const latest = city.power.years[city.power.years.length - 1];
  // Both rows use the last full year the power data covers, so water and power are on the same footing.
  const waterYear = years.find((y) => y.year === latest.year) || current;
  const powerHours = (latest.saidi_with * latest.customers) / 60;
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
            <Tile label="Hours under a boil-water advisory, per resident" figure={whole(waterYear.person_hours / city.residents)}>
              estimated average: some neighborhoods had none, others several days.{counted(waterYear)}{" "}
              {current.year} so far: {whole(current.person_hours / city.residents)}
            </Tile>
            <Tile label="Minutes without power, per customer" figure={whole(latest.saidi_with)}>
              storms included; U.S. average {whole(latest.saidi_with_national_avg)}. Without major storms:{" "}
              {whole(latest.saidi_without)}, U.S. average {whole(latest.saidi_without_national_avg)}
            </Tile>
            <Tile label="Cost per household" figure="Not yet">method under review</Tile>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="eyebrow">For the whole city, {latest.year}</span>
          <div className="grid gap-3 sm:grid-cols-3">
            <Tile label="Hours residents spent under a boil-water advisory" figure={`${millions(waterYear.person_hours)}`}>
              estimated: people in each advisory area × the hours it lasted.{counted(waterYear)}
              {waterYear.upper ? ` ${millions(waterYear.upper)} comes from advisories that include a very small area, counted generously.` : ""}{" "}
              {current.year} so far: {millions(current.person_hours)}
            </Tile>
            <Tile label="Hours customers spent without power" figure={whole(Math.round(powerHours / 1000) * 1000)}>
              estimated from Entergy's federal filing: minutes per customer × {whole(latest.customers)} customers,
              storms included
            </Tile>
            <Tile label="Cost to the city" figure="Not yet">method under review</Tile>
          </div>
        </div>
      </header>

      <Water water={city.water} years={years} />
      <hr className="rule" />
      <Power power={city.power} built={city.built_at} />
      <hr className="rule" />

      <Section eyebrow="Cost" title="What this costs households">
        <p className="muted">Not estimated yet. The method for putting a dollar range on a boil-water advisory and on an
          hour without power is still being worked out, and no figure will appear here until it has been reviewed.</p>
        <p className="muted">School and daycare closures during boil-water advisories are part of that cost: a closed
          school means lost wages and lost work for families well beyond the price of bottled water. Closures are not
          collected yet.</p>
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
          <span className="small muted">Every boil-water advisory since 2010, power outage time against the nation,
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
      <div className="wrap" style={{ paddingBlock: "14px 0" }}>
        <div className="note">Private preview. Not published. Figures are estimates still under review.</div>
      </div>
      <Page />
    </>
  );
}
