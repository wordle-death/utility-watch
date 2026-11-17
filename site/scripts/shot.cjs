// Screenshot the built preview: node scripts/shot.cjs <html> <outdir> [route]
const { chromium } = require("playwright");
(async () => {
  const route = process.argv[4] || "";
  const browser = await chromium.launch();
  for (const [name, width, scheme] of [["desk", 1100, "light"], ["phone", 400, "dark"]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto("file://" + process.argv[2] + (route ? "#" + route : ""));
    await page.waitForTimeout(1200);
    console.log(name, route || "home", "overflow", await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), errors.slice(0, 3));
    await page.screenshot({ path: `${process.argv[3]}/${route || "home"}-${name}.png`, fullPage: true });
  }
  await browser.close();
})();
