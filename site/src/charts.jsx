import React, { useEffect, useRef, useState } from "react";
import { short, whole } from "./format.js";

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(880);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(280, el.clientWidth));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function niceTicks(max, count = 4) {
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough);
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function Tip({ x, width, children }) {
  const left = Math.min(Math.max(x - 95, 0), width - 200);
  return <div className="tip" style={{ left, top: 6 }}>{children}</div>;
}

/** Person-hours under advisory per year, split by how the area was measured. */
export function YearBars({ years }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const height = 300, m = { top: 14, right: 8, bottom: 40, left: 44 };
  const innerW = width - m.left - m.right, innerH = height - m.top - m.bottom;
  const ticks = niceTicks(Math.max(...years.map((y) => y.person_hours), 1));
  const top = ticks[ticks.length - 1];
  const y = (v) => m.top + innerH - (v / top) * innerH;
  const band = innerW / years.length, bar = Math.min(30, band * 0.62);
  const sparse = band < 34;
  return (
    <div ref={ref} style={{ position: "relative" }} onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label="Person-hours under boil-water advisory by year">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t ? "var(--line)" : "var(--axis)"} />
            <text x={m.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-3)">{t ? short(t) : "0"}</text>
          </g>
        ))}
        {years.map((d, i) => {
          const cx = m.left + band * i + band / 2, x = cx - bar / 2;
          const own = d.from_own_map, borrowed = d.from_named_area_lookup;
          const hOwn = (own / top) * innerH, hBor = (borrowed / top) * innerH;
          const gap = own && borrowed ? 2 : 0;
          return (
            <g key={d.year} opacity={hover == null || hover === i ? 1 : 0.55}>
              {own > 0 && <path d={barPath(x, y(0) - hOwn, bar, hOwn, borrowed ? 0 : 4)} fill="var(--series-1)" />}
              {borrowed > 0 && <path d={barPath(x, y(0) - hOwn - gap - hBor, bar, hBor, 4)} fill="var(--series-2)" />}
              {(!sparse || i % 2 === 0) && (
                <text x={cx} y={height - 22} textAnchor="middle" fontSize="11" fill="var(--ink-2)">
                  {sparse ? `’${String(d.year).slice(2)}` : d.year}
                </text>
              )}
              {d.incomplete && <text x={cx} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--ink-3)">†</text>}
              <rect x={m.left + band * i} y={m.top} width={band} height={innerH + 30} fill="transparent"
                onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <Tip x={m.left + band * hover + band / 2} width={width}>
          <b>{years[hover].year}{years[hover].partial ? " (so far)" : ""}</b>
          <div className="row"><span>Advisories</span><span className="data">{years[hover].advisories}</span></div>
          <div className="row"><span>Person-hours</span><span className="data">{short(years[hover].person_hours)}</span></div>
          <div className="row"><span>From own map</span><span className="data">{short(years[hover].from_own_map)}</span></div>
          <div className="row"><span>From named area</span><span className="data">{short(years[hover].from_named_area_lookup)}</span></div>
          {years[hover].incomplete > 0 && <div className="muted">† {years[hover].incomplete} not counted</div>}
        </Tip>
      )}
    </div>
  );
}

function barPath(x, yTop, w, h, r) {
  r = Math.min(r, h, w / 2);
  return `M${x},${yTop + h}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${yTop + h}Z`;
}

/** Outage minutes per customer per year for one utility against the nation and its peers. */
export function MinutesLines({ rows, series }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const labels = width >= 620;
  const height = 300, m = { top: 14, right: labels ? 132 : 14, bottom: 30, left: 48 };
  const innerW = width - m.left - m.right, innerH = height - m.top - m.bottom;
  const values = rows.flatMap((r) => series.map((s) => r[s.key])).filter((v) => v != null);
  const ticks = niceTicks(Math.max(...values, 1));
  const top = ticks[ticks.length - 1];
  const x = (i) => m.left + (innerW * i) / (rows.length - 1);
  const y = (v) => m.top + innerH - (v / top) * innerH;
  const path = (key) => {
    let d = "", pen = false;
    rows.forEach((r, i) => {
      if (r[key] == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i)},${y(r[key])}`;
      pen = true;
    });
    return d;
  };
  const last = rows.length - 1;
  // Spread the end labels so they never sit on top of each other.
  const ends = series.map((s) => ({ ...s, at: y(rows[last][s.key] ?? 0) })).sort((a, b) => a.at - b.at);
  for (let i = 1; i < ends.length; i++) ends[i].at = Math.max(ends[i].at, ends[i - 1].at + 15);
  const move = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const i = Math.round(((event.clientX - box.left - m.left) / innerW) * last);
    setHover(Math.min(last, Math.max(0, i)));
  };
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg width={width} height={height} role="img" aria-label="Outage minutes per customer by year"
        onMouseMove={move} onMouseLeave={() => setHover(null)} onClick={move}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t ? "var(--line)" : "var(--axis)"} />
            <text x={m.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-3)">{whole(t)}</text>
          </g>
        ))}
        {rows.map((r, i) => (i % 2 === 0 || rows.length < 9) && (
          <text key={r.year} x={x(i)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{r.year}</text>
        ))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + innerH} stroke="var(--axis)" />}
        {series.map((s) => (
          <g key={s.key}>
            <path d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {rows[last][s.key] != null && <circle cx={x(last)} cy={y(rows[last][s.key])} r="4" fill={s.color} stroke="var(--surface)" strokeWidth="2" />}
            {hover != null && rows[hover][s.key] != null && (
              <circle cx={x(hover)} cy={y(rows[hover][s.key])} r="4" fill={s.color} stroke="var(--surface)" strokeWidth="2" />
            )}
          </g>
        ))}
        {labels && ends.map((s) => (
          <text key={s.key} x={x(last) + 10} y={s.at + 4} fontSize="12" fill="var(--ink-2)">
            {s.short} <tspan fill="var(--ink)" fontWeight="600">{whole(rows[last][s.key])}</tspan>
          </text>
        ))}
      </svg>
      {hover != null && (
        <Tip x={x(hover)} width={width}>
          <b>{rows[hover].year}</b>
          {series.map((s) => (
            <div className="row" key={s.key}>
              <span><i style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: s.color, marginRight: 6 }} />{s.short}</span>
              <span className="data">{rows[hover][s.key] == null ? "not reported" : `${whole(rows[hover][s.key])} min`}</span>
            </div>
          ))}
        </Tip>
      )}
    </div>
  );
}
