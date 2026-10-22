// Screenshot the live Benchmarks page for the README (docs/images/benchmarks.png).
// Drives the system Chrome through playwright-core (no browser download):
//
//   node scripts/capture-benchmarks.mjs --site https://devpilot-pied.vercel.app \
//       --run lite-s20-seed7 --out ../../docs/images/benchmarks.png
//
// The SWE-bench pipeline runs this after publishing final results
// (apps/api/scripts/eval_pipeline.py). CHROME_PATH overrides the browser.
import { chromium } from "playwright-core";

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  if (fallback === undefined) {
    console.error(`missing --${name}`);
    process.exit(2);
  }
  return fallback;
}

const site = arg("site").replace(/\/$/, "");
const run = arg("run");
const out = arg("out");

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH ?? "/usr/bin/google-chrome",
  headless: true,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 },
    colorScheme: "light",
  });
  page.setDefaultTimeout(120_000); // the free API host may be waking up

  await page.goto(`${site}/login`);
  await page.getByRole("button", { name: /View the demo/ }).click();
  await page.waitForURL(/\/tasks/);

  await page.goto(`${site}/evals`);
  await page.getByRole("heading", { name: "Benchmarks" }).waitFor();
  const select = page.locator("select");
  await select.or(page.getByText(`${run} —`)).first().waitFor();
  if (await select.count()) {
    const label = await select
      .locator("option", { hasText: `${run} ·` })
      .first()
      .textContent();
    await select.selectOption({ label: label.trim() });
  }
  await page.getByText(new RegExp(`^${run} — `)).waitFor();
  await page.waitForLoadState("networkidle");

  await page.screenshot({ path: out, fullPage: true });
  console.log(`Saved ${out}`);
} finally {
  await browser.close();
}
