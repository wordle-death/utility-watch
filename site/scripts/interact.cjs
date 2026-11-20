// Exercise the page's interactive parts: node scripts/interact.cjs <html>
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const out = [];
  for (const width of [1100, 400]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.goto("file://" + process.argv[2]);
    await page.waitForTimeout(800);
    const check = (name, ok, detail = "") => out.push(`${ok ? "PASS" : "FAIL"} ${width}px ${name} ${detail}`);
    // Year filter
    const before = await page.locator("tbody tr").first().innerText();
    const rows2026 = await page.locator("section").nth(0).locator("tbody tr").count();
    await page.selectOption("#year-filter", "2018");
    const rows2018 = await page.locator("section").nth(0).locator("tbody tr").count();
    const first2018 = await page.locator("section").nth(0).locator("tbody tr").first().innerText();
    check("year filter", rows2018 > 0 && /2018/.test(first2018) && first2018 !== before, `2026 rows ${rows2026}, 2018 rows ${rows2018}`);
    await page.selectOption("#year-filter", "all");
    check("all years", (await page.locator("section").nth(0).locator("tbody tr").count()) === 94);
    // Bar tooltip
    const bars = page.locator("section").nth(0).locator("svg[role=img] rect");
    await bars.nth(8).hover();
    const tip = await page.locator(".tip").first().innerText().catch(() => "");
    check("bar tooltip", /2018/.test(tip) && /Advisories/.test(tip), JSON.stringify(tip.replace(/\n/g, " | ")));
    const box = await page.locator(".tip").first().boundingBox();
    check("tooltip inside page", box && box.x >= 0 && box.x + box.width <= width);
    // Storm toggle
    const svg = page.locator("section").nth(1).locator("svg[role=img]").first();
    const label = async () => (await svg.locator("text").allInnerTexts()).join(" ");
    const without = await label();
    await page.getByRole("button", { name: "With major storms" }).click();
    const withStorms = await label();
    check("storm toggle", without !== withStorms, "axis labels change");
    await svg.hover({ position: { x: (await svg.boundingBox()).width * 0.6, y: 100 } });
    const tip2 = await page.locator("section").nth(1).locator(".tip").innerText().catch(() => "");
    check("line tooltip", /20\d\d/.test(tip2) && /min/.test(tip2), JSON.stringify(tip2.replace(/\n/g, " | ")));
    // Numbers table
    await page.locator("summary").click();
    check("show the numbers", (await page.locator("details table tbody tr").count()) === 13);
    // Source link
    const href = await page.locator("section").nth(0).locator("tbody a").first().getAttribute("href");
    check("notice link", /swbno\.org\/PressReleases\/Details\/\d+/.test(href), href);
    await page.close();
  }
  console.log(out.join("\n"));
  await browser.close();
})();
