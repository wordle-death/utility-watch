import React, { useMemo, useState } from "react";
import city from "./data/new-orleans.json";
import { YearBars, MinutesLines } from "./charts.jsx";
import { FLAGS, day, dayTime, millions, short, whole } from "./format.js";

const FIRST_YEAR = 2010; // the one 2009 advisory on record has no map and no count

function waterYears(byYear, builtAt) {
  const thisYear = new Date(builtAt).getUTCFullYear();
  const years = [];
  for (let year = FIRST_YEAR; year <= thisYear; year++) {
    const e = byYear[year] || {};
    years.push({
      year, advisories: e.advisories || 0, person_hours: e.person_hours || 0,
      from_own_map: e.from_own_map || 0, from_named_area_lookup: e.from_named_area_lookup || 0,
      incomplete: e.advisories_without_person_hours || 0, partial: year === thisYear,
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

function Section({ eyebrow, title, children }) {
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

function Tile({ label, figure, children }) {
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
  const total = years.reduce((sum, y) => sum + y.person_hours, 0);
  const borrowed = years.reduce((sum, y) => sum + y.from_named_area_lookup, 0);
  return (
    <Section eyebrow="Water" title="Boil-water advisories">
      <p className="muted">
        Each bar is the number of people under a boil-water advisory multiplied by the hours it lasted, added up for
        the year. One million person-hours is about 42,000 people without safe tap water for a full day.
      </p>
      <div className="panel flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3>Person-hours under advisory, by year issued</h3>
          <div className="legend">
            <span><i style={{ background: "var(--series-1)" }} />Area from the advisory's own map</span>
            <span><i style={{ background: "var(--series-2)" }} />Area borrowed from a named-area drawing</span>
          </div>
        </div>
        <YearBars years={years} />
        <p className="small muted">
          † At least one advisory that year could not be counted, so the bar is too low. {years[years.length - 1].year} is
          the year so far. Estimated: hours come from the Sewerage &amp; Water Board's notices, people from the 2020 Census
          for every year.
        </p>
      </div>
      <div className="note">
        {Math.round((borrowed / total) * 100)}% of the total, and everything before 2019, uses a borrowed area: the
        board published no map for those advisories, so the count uses its drawing of the whole East Bank, West Bank,
        Lower 9th Ward or Venetian Isles. The East Bank drawing likely overstates some of them.
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
              <th className="num">Person-hours</th><th>Caveats</th><th>Source</th></tr>
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

function Power({ power }) {
  const [mode, setMode] = useState("without");
  const latest = power.years[power.years.length - 1];
  const live = power.live;
  const closedHours = live.closed.reduce((sum, e) => sum + (e.customer_hours || 0), 0);
  const open = [...live.active].sort((a, b) => (b.customers || 0) - (a.customers || 0));
  return (
    <Section eyebrow="Power" title="Outage time compared with the rest of the country">
      <p className="muted">
        Utilities report to the federal government how many minutes the average customer went without power each year.
        In {latest.year}, {power.utility} customers lost {whole(latest.saidi_without)} minutes outside of major storms,
        against a national average of {whole(latest.saidi_without_national_avg)}. {whole(latest.saidi_without_pct_of_utilities_better)}%
        of comparable utilities did better.
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

      <h3 className="pt-2">Outages since collection began</h3>
      <p className="muted">
        Entergy's outage map keeps no history, so this project saves it every 15 minutes. Collection began{" "}
        {day(live.collecting_since)}. For the first day it sometimes ran hours apart, so short outages in that window were missed.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Outages recorded and ended" figure={whole(live.closed.length)}>since {day(live.collecting_since)}</Tile>
        <Tile label="Customer-hours without power" figure={whole(closedHours)}>estimated from 15-minute snapshots</Tile>
        <Tile label="Open right now" figure={whole(open.length)}>as of {dayTime(live.last_success)} Central</Tile>
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

export default function App() {
  const years = useMemo(() => waterYears(city.water.by_year, city.built_at), []);
  const current = years[years.length - 1];
  const latest = city.power.years[city.power.years.length - 1];
  return (
    <main className="wrap flex flex-col gap-12">
      <header className="flex flex-col gap-4">
        <div className="note">Private preview. Not published. Figures are estimates still under review.</div>
        <div className="flex flex-col gap-2">
          <span className="eyebrow">Utility Watch · {city.city}</span>
          <h1>How often New Orleans loses power and safe water</h1>
          <p className="muted">Built from public records: the water board's own notices and maps, the power company's
            federal filings and live outage map, and the Census. Data as of {dayTime(city.built_at)} Central.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile label={`Boil-water advisories, ${current.year} so far`} figure={current.advisories}>
            issued by the Sewerage &amp; Water Board
          </Tile>
          <Tile label={`Person-hours under advisory, ${current.year} so far`} figure={millions(current.person_hours)}>
            estimate: people in the advisory area × hours
          </Tile>
          <Tile label={`Power outage minutes per customer, ${latest.year}`} figure={whole(latest.saidi_without)}>
            U.S. average {whole(latest.saidi_without_national_avg)}, major storms excluded
          </Tile>
        </div>
      </header>

      <Water water={city.water} years={years} />
      <hr className="rule" />
      <Power power={city.power} />
      <hr className="rule" />

      <Section eyebrow="Cost" title="What this costs households">
        <p className="muted">Not estimated yet. The method for putting a dollar range on a boil-water advisory and on an
          hour without power is still being worked out, and no figure will appear here until it has been reviewed.</p>
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
