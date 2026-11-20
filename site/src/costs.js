// Preliminary cost estimates. Every input is listed here with its source, so the method can be read in one place.
// All results are in current dollars, adjusted with the consumer price index (CPI-U, U.S. city average).

export const CPI = {
  2012: 229.594, // annual average
  2014: 236.736, // annual average
  2023: 304.702, // annual average
  current: 337.511, // October 2026, latest release (BLS, Nov 10, 2026)
};
export const CURRENT_DOLLARS = "October 2026 dollars";
export const CPI_SOURCE = "https://www.bls.gov/news.release/cpi.nr0.htm";
const inflate = (amount, year) => (amount * CPI.current) / CPI[year];

// Boil-water advisories: cost per household for one advisory. No official standard exists for an advisory
// (FEMA's standard value covers a complete loss of water), so the range spans two published studies,
// neither of which measured a boil-water advisory exactly.
export const WATER = {
  low: {
    perHousehold: inflate(3.6, 2014),
    source: "extra bottled water bought per household during Toledo, Ohio's three-day do-not-drink advisory in 2014",
    cite: "Don't Drink the Water! The Impact of Harmful Algal Blooms on Household Averting Expenditure (Environmental and Resource Economics, 2023)",
    url: "https://link.springer.com/article/10.1007/s10640-023-00786-2",
  },
  high: {
    perHousehold: inflate(93.96, 2012),
    source: "money and time each household spent per incident in routine local water disruptions, from interviews in 2012",
    cite: "Heflin et al., Understanding the economic impacts of disruptions in water service (Evaluation and Program Planning, 2014)",
    url: "https://www.sciencedirect.com/science/article/abs/pii/S0149718914000500",
  },
};

// Power outages: the Department of Energy's Interruption Cost Estimate (ICE) Calculator 2.0, residential
// customers, cost per outage by length (2023 dollars). Valid for outages up to 24 hours.
const ICE_RESIDENTIAL = [
  [5, 1.8], // momentary, taken as 5 minutes
  [120, 10.49],
  [480, 25.55],
  [1440, 54.52],
];
// For context only, not used in the totals: one business customer's cost of a two-hour outage (2023 dollars).
export const ICE_BUSINESS_2H = inflate(2839, 2023);
export const ICE_SOURCE = {
  cite: "Berkeley Lab, ICE Calculator 2.0 Phase I final report (2025)",
  url: "https://eta-publications.lbl.gov/sites/default/files/2025-06/ice_2.0_phase_i_final_report_29may2025.pdf",
};

/** Residential cost of one outage of the given length, in current dollars; straight line on a log-time scale. */
export function iceResidential(minutes) {
  const m = Math.min(Math.max(minutes, ICE_RESIDENTIAL[0][0]), ICE_RESIDENTIAL[ICE_RESIDENTIAL.length - 1][0]);
  for (let i = 1; i < ICE_RESIDENTIAL.length; i++) {
    const [a, ca] = ICE_RESIDENTIAL[i - 1], [b, cb] = ICE_RESIDENTIAL[i];
    if (m <= b) return inflate(ca + (Math.log(m / a) / Math.log(b / a)) * (cb - ca), 2023);
  }
  return null;
}

/** Yearly residential cost per customer: outages per customer (SAIFI) × cost of an average-length outage (CAIDI). */
export function powerPerCustomer(saidi, saifi) {
  if (saidi == null || saifi == null) return null;
  if (saifi === 0 && saidi === 0) return 0; // no outages reported
  if (saifi === 0 || saidi === 0) return null; // the two figures disagree: treat as unknown, not as zero
  return saifi * iceResidential(saidi / saifi);
}

/** Water cost for a year's advisories: households in each advisory × the per-household range. */
export function waterForYear(advisories) {
  // The cost is per advisory, so an advisory needs a household count but not its length.
  const counted = advisories.filter((a) => a.households != null);
  if (advisories.length && !counted.length) return null; // nothing countable: unknown, not zero
  const householdAdvisories = counted.reduce((sum, a) => sum + a.households, 0);
  return {
    low: householdAdvisories * WATER.low.perHousehold,
    high: householdAdvisories * WATER.high.perHousehold,
    householdAdvisories,
    advisories: advisories.length,
    missing: advisories.length - counted.length,
    // Households in advisories that include at least one very small area counted generously (most of each such
    // advisory is usually counted exactly), and the number of advisories that overlap another in time.
    inAdvisoriesWithUpperBound: counted.filter((a) => a.upper_bound).reduce((sum, a) => sum + a.households, 0),
    concurrentAdvisories: counted.filter((a) => a.flags.includes("concurrent_with_another_advisory_may_double_count")).length,
  };
}

/** "$6", "$1,200", "$950K", "$1.0M", "$27M": rounded first, then given a unit. */
export function money(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const r = (x, d) => Number(x.toFixed(d));
  if (n < 1e5) return `$${Math.round(n).toLocaleString("en-US")}`;
  if (r(n / 1e3, 0) < 1000) return `$${r(n / 1e3, 0)}K`;
  const m = n / 1e6;
  return m < 9.95 ? `$${r(m, 1).toFixed(1)}M` : `$${Math.round(m)}M`;
}
