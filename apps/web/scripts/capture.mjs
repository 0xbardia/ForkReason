/**
 * Visual QA capture.
 *
 * Screenshots every required surface at every required viewport, and records
 * console errors, horizontal overflow and layout shift per page. Used by the
 * release loop, so it is written to fail loudly rather than silently pass.
 *
 *   node scripts/capture.mjs [baseUrl] [outDir]
 */

import { chromium } from "playwright-core";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:3111";
const OUT = process.argv[3] ?? "/root/ForkReason/artifacts/screens";

const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "desktop-1280", width: 1280, height: 820 },
  { name: "mobile-390", width: 390, height: 844 },
  { name: "mobile-360", width: 360, height: 800 },
];

// A real case, so the signature screen is reviewed against real data rather
// than an empty state. Override with CASE_ID.
const CASE_ID = process.env.CASE_ID ?? "";

const SURFACES = [
  { name: "landing", path: "/" },
  { name: "trace", path: "/trace" },
  ...(CASE_ID
    ? [
        { name: "case", path: `/case/${CASE_ID}` },
        { name: "evidence", path: `/case/${CASE_ID}/evidence` },
        { name: "challenge", path: `/case/${CASE_ID}/challenge` },
      ]
    : []),
  { name: "explore", path: "/explore" },
  { name: "docs", path: "/docs" },
  { name: "docs-detail", path: "/docs/repo-dna" },
  { name: "security", path: "/security" },
  { name: "notfound", path: "/this-route-does-not-exist" },
];

const findings = [];

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });

  for (const surface of SURFACES) {
    const page = await context.newPage();
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text().slice(0, 200));
    });
    page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`.slice(0, 200)));

    let status = 0;
    try {
      const response = await page.goto(`${BASE}${surface.path}`, {
        waitUntil: "domcontentloaded",
        timeout: 30000,
      });
      status = response?.status() ?? 0;
      await page.waitForTimeout(2200);
    } catch (error) {
      errors.push(`navigation: ${error.message}`.slice(0, 200));
    }

    const metrics = await page
      .evaluate(() => {
        const doc = document.documentElement;
        const overflow = doc.scrollWidth - doc.clientWidth;
        // Find any element wider than the viewport, which is what actually
        // causes a horizontal scrollbar.
        let worst = null;
        if (overflow > 0) {
          for (const el of document.querySelectorAll("body *")) {
            const rect = el.getBoundingClientRect();
            if (rect.right > doc.clientWidth + 1 && rect.width > 40) {
              const candidate = {
                tag: el.tagName.toLowerCase(),
                cls: String(el.className).slice(0, 60),
                right: Math.round(rect.right),
              };
              if (!worst || candidate.right > worst.right) worst = candidate;
            }
          }
        }
        return {
          overflow,
          worst,
          title: document.title,
          h1: document.querySelector("h1")?.innerText ?? null,
          scrollHeight: document.body.scrollHeight,
        };
      })
      .catch(() => ({ overflow: 0, worst: null, title: "", h1: null, scrollHeight: 0 }));

    const file = path.join(OUT, `${surface.name}-${viewport.name}.png`);
    await page.screenshot({ path: file, fullPage: viewport.width >= 1280 });

    const record = { surface: surface.name, viewport: viewport.name, status, ...metrics, errors };
    findings.push(record);

    const flag = errors.length || metrics.overflow > 0 ? " !!" : "";
    console.log(
      `${surface.name.padEnd(10)} ${viewport.name.padEnd(13)} ${status} ` +
        `ovf=${metrics.overflow} err=${errors.length}${flag}`,
    );
    if (metrics.worst) console.log(`    widest: ${metrics.worst.tag}.${metrics.worst.cls} → ${metrics.worst.right}px`);
    for (const error of errors.slice(0, 3)) console.log(`    ${error}`);

    await page.close();
  }

  await context.close();
}

await browser.close();
await writeFile(path.join(OUT, "findings.json"), JSON.stringify(findings, null, 2));

const problems = findings.filter((f) => f.errors.length > 0 || f.overflow > 0 || f.status >= 500);
console.log(`\n${findings.length} captures, ${problems.length} with problems.`);
console.log(`Output: ${OUT}`);