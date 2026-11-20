import { test } from "node:test";
import assert from "node:assert/strict";
import { CPI, WATER, iceResidential, money, powerPerCustomer, waterForYear } from "../src/costs.js";

const now = (x, year) => (x * CPI.current) / CPI[year];

test("ICE matches its published points and clamps outside them", () => {
  assert.ok(Math.abs(iceResidential(120) - now(10.49, 2023)) < 1e-9);
  assert.ok(Math.abs(iceResidential(1440) - now(54.52, 2023)) < 1e-9);
  assert.equal(iceResidential(1), iceResidential(5));
  assert.equal(iceResidential(5000), iceResidential(1440));
});

test("power cost is outages times the cost of an average outage", () => {
  assert.ok(Math.abs(powerPerCustomer(240, 2) - 2 * iceResidential(120)) < 1e-9);
  assert.equal(powerPerCustomer(0, 0), 0);
  assert.equal(powerPerCustomer(null, 1), null);
});

test("water cost counts households per advisory and reports gaps", () => {
  const r = waterForYear([
    { households: 100, hours: 10, upper_bound: false, flags: [] },
    { households: 50, hours: null, upper_bound: true, flags: ["concurrent_with_another_advisory_may_double_count"] },
    { households: null, hours: 5, flags: [] },
  ]);
  assert.equal(r.householdAdvisories, 150);
  assert.equal(r.missing, 1);
  assert.equal(r.upperBound, 50);
  assert.equal(r.concurrent, 50);
  assert.ok(Math.abs(r.high - 150 * WATER.high.perHousehold) < 1e-9);
  assert.equal(waterForYear([{ households: null, flags: [] }]), null);
});

test("money rounds before choosing a unit", () => {
  assert.deepEqual([5.13, 49999, 999600, 9960000, 26980000].map(money), ["$5", "$49,999", "$1.0M", "$10M", "$27M"]);
  assert.equal(money(null), "–");
});
