export const millions = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} million` : Math.round(n).toLocaleString("en-US"));
export const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : `${Math.round(n)}`);
export const whole = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-US"));
const zone = "America/Chicago";
export const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-US", { timeZone: zone, month: "short", day: "numeric", year: "numeric" }) : "–");
export const dayTime = (iso) => (iso ? new Date(iso).toLocaleString("en-US", { timeZone: zone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "–");

// Plain-language versions of the flags the timeline puts on uncertain advisories.
export const FLAGS = {
  area_from_named_area_lookup: "Area borrowed from S&WB's drawing of the whole named area",
  other_named_places_not_counted: "Also names places that are not counted",
  no_map_area: "No map, so people not counted",
  no_lift_release_found: "No lift notice found",
  remainder_after_partial_lift_not_counted: "Counted to the first lift; the part lifted later is left out",
  small_areas_summed_may_overlap: "Small areas added together; may overlap",
  concurrent_with_another_advisory_may_double_count: "Overlaps another advisory in time; some people may be counted twice",
  area_expanded_after_issue: "Area grew after it was issued; counted at full size from the start",
  place_taken_from_lift_release: "Place taken from the lift notice",
  lift_names_a_different_place: "Lift notice names a different place",
  partial_lift_of_unmatched_place_not_applied: "A partial lift for another place was ignored",
  issue_release_missing: "First notice missing; clock probably starts late",
  unusually_long_check_by_hand: "Unusually long",
  area_matched_by_date_only: "Map matched by date only",
  release_matched_by_time_only: "Notice matched by time only",
  multiple_areas_summed_may_overlap: "Areas added together; may overlap",
};
