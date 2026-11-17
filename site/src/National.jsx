import React, { useMemo, useState } from "react";
import data from "./data/national.json";
import { MinutesLines } from "./charts.jsx";
import { Section, Tile } from "./App.jsx";
import { whole } from "./format.js";

const SERIES = [
  { key: "saidi_with_avg", short: "With storms", color: "var(--series-1)" },
  { key: "saidi_without_avg", short: "Without", color: "var(--series-2)" },
];
const STATES = [...new Set(data.utilities.map((u) => u.state))].sort();
const SORTS = {
  customers: { label: "Largest first", fn: () => (a, b) => (b.customers || 0) - (a.customers || 0) },
  most: { label: "Most outage time", fn: (m) => (a, b) => (b[m] ?? -1) - (a[m] ?? -1) },
  fewest: { label: "Least outage time", fn: (m) => (a, b) => (a[m] ?? Infinity) - (b[m] ?? Infinity) },
  name: { label: "Name", fn: () => (a, b) => a.name.localeCompare(b.name) },
};
const PAGE = 40;

function ordinal(n) {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th";
  return `${n}${tail}`;
}

function standing(u, measure) {
  const better = u[`better_${measure}`];
  if (u[measure] == null) return { text: "Not reported" };
  if (better == null) return { text: u.ieee ? "Too small to rank" : "Own method; not ranked" };
  // Percentile where higher is better: the share of comparable utilities with as much or more outage time.
  const percentile = Math.min(99, Math.max(1, Math.round(100 - better)));
  return { better, text: ordinal(percentile) };
}

export default function National() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [measure, setMeasure] = useState("with");
  const [sort, setSort] = useState("customers");
  const [shown, setShown] = useState(PAGE);
  const latest = data.by_year[data.by_year.length - 1];

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.utilities
      .filter((u) => (state === "all" || u.state === state) && (!q || u.name.toLowerCase().includes(q)))
      .sort(SORTS[sort].fn(measure));
  }, [query, state, measure, sort]);
  const reset = (setter) => (event) => { setter(event.target.value); setShown(PAGE); };

  return (
    <main className="wrap flex flex-col gap-12">
      <header className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="eyebrow">Utility Watch · National</span>
          <h1>How much time does your power company leave you in the dark?</h1>
          <p className="muted">Every year, utilities tell the federal government how many minutes their average customer
            went without power. This page puts all {whole(data.utilities.length)} of those reports side by side for{" "}
            {data.latest_year}.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile label={`Minutes without power per customer, U.S. average, ${latest.year}`} figure={whole(latest.saidi_with_avg)}>
            every outage counted, storms included
          </Tile>
          <Tile label="The same, leaving out major storms" figure={whole(latest.saidi_without_avg)}>
            how the grid holds up on an ordinary day
          </Tile>
          <Tile label="The typical utility, storms included" figure={whole(latest.saidi_with_median)}>
            half of utilities had fewer minutes than this, half had more
          </Tile>
        </div>
      </header>

      <Section eyebrow="Trend" title="The national average since 2013">
        <div className="panel flex flex-col gap-3">
          <h3>Outage minutes per customer per year, U.S. average</h3>
          <div className="legend">
            <span><i style={{ background: "var(--series-1)" }} />With major storms</span>
            <span><i style={{ background: "var(--series-2)" }} />Without major storms</span>
          </div>
          <MinutesLines rows={data.by_year} series={SERIES} />
          <p className="small muted">Measured: reported by utilities on federal Form EIA-861 and averaged by number of
            customers. The gap between the lines is the time lost to major storms.</p>
        </div>
      </Section>

      <Section eyebrow="Lookup" title="Find your utility">
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr] items-end">
          <label className="small muted flex flex-col gap-1" htmlFor="utility-search">Utility name
            <input id="utility-search" type="search" placeholder="Entergy, Duke, City of…" value={query} onChange={reset(setQuery)} />
          </label>
          <label className="small muted flex flex-col gap-1" htmlFor="state-filter">State
            <select id="state-filter" value={state} onChange={reset(setState)}>
              <option value="all">All states</option>
              {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="small muted flex flex-col gap-1" htmlFor="sort-by">Sort
            <select id="sort-by" value={sort} onChange={reset(setSort)}>
              {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="seg" role="group" aria-label="Major storms">
            <button type="button" aria-pressed={measure === "with"} onClick={() => setMeasure("with")}>With major storms</button>
            <button type="button" aria-pressed={measure === "without"} onClick={() => setMeasure("without")}>Without major storms</button>
          </div>
          <span className="small muted" aria-live="polite">{whole(rows.length)} {rows.length === 1 ? "utility" : "utilities"}</span>
        </div>
        <div className="panel scroll-x" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Utility</th><th>State</th><th>Type</th><th className="num">Customers</th>
                <th className="num">Minutes, {data.latest_year}</th><th>Reliability percentile</th></tr>
            </thead>
            <tbody>
              {rows.slice(0, shown).map((u) => {
                const s = standing(u, measure);
                return (
                  <tr key={`${u.id}-${u.state}`} className={u.id === 13478 ? "pick" : undefined}>
                    <td style={{ minWidth: 200 }}>
                      {u.id === 13478 ? <a href="#new-orleans">{u.name}</a> : u.name}
                    </td>
                    <td>{u.state}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{u.type}</td>
                    <td className="num">{whole(u.customers)}</td>
                    <td className="num">{u[measure] == null ? "–" : whole(u[measure])}</td>
                    <td style={{ minWidth: 190 }}>
                      {s.better != null ? (
                        <div className="flex items-center gap-3">
                          <span className="data" style={{ minWidth: "3.2em" }}>{s.text}</span>
                          <div className="meter" style={{ flex: 1 }} aria-hidden="true"><i style={{ left: `${100 - s.better}%` }} /></div>
                        </div>
                      ) : <span className="small muted">{s.text}</span>}
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && <tr><td colSpan="6" className="muted">No utility matches. Try part of the name, or clear the state.</td></tr>}
            </tbody>
          </table>
        </div>
        {rows.length > shown && (
          <div><button type="button" className="btn" onClick={() => setShown(shown + PAGE)}>Show {Math.min(PAGE, rows.length - shown)} more</button></div>
        )}
        <p className="small muted">Higher is better. A utility in the 90th percentile had as little outage time as, or
          less than, about 90% of comparable utilities; one in the 10th had more than about 90% of them.</p>
      </Section>

      <Section eyebrow="Method" title="How to read this">
        <ul className="muted flex flex-col gap-2" style={{ margin: 0, paddingLeft: 18, maxWidth: "68ch" }}>
          <li><b>Source:</b> {data.source}. {data.latest_year} figures are {(data.latest_year_data_maturity || []).join(", ") || "unlabeled"}.
            These are the utilities' own reports; nobody audits them.</li>
          <li><b>Who is ranked:</b> utilities with at least 1,000 customers that measure outages the standard way (IEEE 1366).
            Others are listed with their figures but not ranked, because their numbers are not comparable.</li>
          <li><b>Major storms:</b> each utility decides which days count as a major event, within the standard's rules, so
            the without-storms figures are less comparable than they look.</li>
          <li><b>One row per state:</b> a utility that serves several states appears once for each.</li>
          <li><b>Customers</b> are accounts, not people. A household is usually one customer.</li>
        </ul>
        <p className="small muted">
          Sources: <a href="https://www.eia.gov/electricity/data/eia861/" target="_blank" rel="noreferrer">EIA Form 861</a> via{" "}
          <a href="https://catalyst.coop/pudl/" target="_blank" rel="noreferrer">PUDL</a>,{" "}
          <a href="https://github.com/wordle-death/utility-watch" target="_blank" rel="noreferrer">code and data</a>.
        </p>
      </Section>
    </main>
  );
}
