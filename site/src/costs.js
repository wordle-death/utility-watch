// Preliminary cost estimates. Every input is listed here with its source, so the method can be read in one place.
// All results are in current dollars, adjusted with the consumer price index (CPI-U, U.S. city average).

export const CPI = {
  2012: 229.594, // annual average
  2014: 236.736, // annual average
  2023: 304.702, // annual average
  current: 337.511, // October 2026, latest release (BLS, Nov 10, 2026)
};
export const CURRENT_DOLLARS = "October 2026 dollars";
const inflate = (amount, year) => (amount * CPI.current) / CPI[year];

// Boil-water advisories: cost per household for one advisory. No official standard exists for an advisory
// (FEMA's standard value covers a complete loss of water), so the range spans two published studies.
export const WATER = {
  low: {
    perHousehold: inflate(3.6, 2014),
    source: "Toledo, Ohio, 2014 three-day water advisory: extra bottled-water spending per household",
    cite: "Don't Drink the Water! The Impact of Harmful Algal Blooms on Household Averting Expenditure (Environmental and Resource Economics, 2023)",
    url: "https://link.springer.com/article/10.1007/s10640-023-00786-2",
  },
  high: {
    perHousehold: inflate(93.96, 2012),
    source: "Interviews about routine water disruptions: money and time each household spent per incident",
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
  if (!saidi || !saifi) return null;
  return saifi * iceResidential(saidi / saifi);
}

/** Water cost for a year's advisories: households in each advisory × the per-household range. */
export function waterForYear(advisories) {
  const counted = advisories.filter((a) => a.households != null && a.hours != null);
  const householdAdvisories = counted.reduce((sum, a) => sum + a.households, 0);
  return {
    low: householdAdvisories * WATER.low.perHousehold,
    high: householdAdvisories * WATER.high.perHousehold,
    householdAdvisories,
    missing: advisories.length - counted.length,
  };
}
