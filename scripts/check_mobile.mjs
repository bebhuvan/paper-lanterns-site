// Open the built site in headless Chromium at phone and tablet widths and fail on layout faults:
//   - the page scrolls sideways (charts may scroll inside their own .chart-box);
//   - a button, menu toggle or block-level link is shorter than 44px;
//   - letter text is smaller than 18px;
//   - a note figure sits more than 6px away from the word it marks;
//   - the logo or a header link wraps onto two lines.
// No dependencies: scripts/chromium.mjs drives Chromium over its DevTools protocol.
// Requests to anything but the local server are blocked, so the check needs no network.
//
// Usage: node scripts/check_mobile.mjs <built-site-dir>    (CHROME=/path/to/chromium to choose the browser)

import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cdp, findChrome, launch, serve } from "./chromium.mjs";

const WIDTHS = [360, 390, 768, 935, 1280];
const PAGES = [
  "/",
  "/collections/",
  "/collections/dostoevsky-family-friends-1914/",
  "/collections/dostoevsky-family-friends-1914/20/",
  "/collections/sand-flaubert-letters-1922/1/",
  "/collections/tipu-sultan-select-letters-1811/",
  "/collections/fifty-famous-letters-1930/",
  "/collections/vivekananda-letters-1944/1/",
  "/letter/adams-abigail-john-1776/",
  "/essay/thoreau-walking-1862/",
  "/about/",
  "/reading/",
  "/search/",
  "/explore/",
  "/explore/1840s/",
  "/people/",
  "/people/fyodor-dostoevsky/",
  "/journal/",
];

const root = process.argv[2];
if (!root || !existsSync(join(root, "index.html"))) {
  console.error("usage: node scripts/check_mobile.mjs <built-site-dir>");
  process.exit(2);
}

// Runs inside the page.
const PROBE = `(() => {
  const cw = document.documentElement.clientWidth;
  const out = { scrollWidth: document.documentElement.scrollWidth, clientWidth: cw, wide: [], small: [], text: null };
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".chart-box, .tabs-track, pre, .skip") || !visible(el)) continue; // intentional sideways scrollers
    const r = el.getBoundingClientRect();
    if (r.right > cw + 1 || r.left < -1) out.wide.push(el.tagName.toLowerCase() + "." + el.className + " [" + Math.round(r.left) + "," + Math.round(r.right) + "]");
  }
  for (const el of document.querySelectorAll("button, summary, a")) {
    if (!visible(el) || el.closest(".skip")) continue;
    const inline = getComputedStyle(el).display === "inline";
    if (inline && el.tagName === "A") continue; // links inside running text are exempt (WCAG 2.5.8)
    const r = el.getBoundingClientRect();
    if (r.height < 44) out.small.push(el.tagName.toLowerCase() + " '" + (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30) + "' " + Math.round(r.height) + "px");
  }
  // Header words must never wrap onto a second line (logo, links), at any width.
  out.wrapped = [...document.querySelectorAll(".site-header .logo .word, .site-nav a, .letter-bar .logo .word")]
    .filter((el) => {
      if (!visible(el)) return false;
      const range = document.createRange();
      range.selectNodeContents(el);
      return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size > 1;
    })
    .map((el) => el.textContent.trim());
  // A note figure must sit against the word before it, not float away from it.
  out.farNotes = [];
  for (const sup of document.querySelectorAll(".text sup.fnref")) {
    const prev = sup.previousSibling, a = sup.querySelector("a");
    if (!prev || prev.nodeType !== 3 || !prev.textContent.length || /\s$/.test(prev.textContent) || !a || !a.firstChild) continue;
    const r1 = document.createRange(); r1.setStart(prev, prev.textContent.length - 1); r1.setEnd(prev, prev.textContent.length);
    const r2 = document.createRange(); r2.selectNodeContents(a);
    const end = [...r1.getClientRects()].pop(), start = r2.getClientRects()[0];
    if (end && start && Math.abs(start.top - end.top) < 30 && start.left - end.right > 6) out.farNotes.push(a.textContent + " " + Math.round(start.left - end.right) + "px");
  }
  const t = document.querySelector(".text");
  if (t) out.text = parseFloat(getComputedStyle(t).fontSize);
  return JSON.stringify(out);
})()`;

const server = await serve(root);
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = mkdtempSync(join(tmpdir(), "pl-chrome-"));
let browser;
const problems = [];
try {
  browser = await launch(findChrome(), profile);
  const c = cdp(browser.ws);
  await c.ready;
  const { targetId } = await c.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await c.send("Target.attachToTarget", { targetId, flatten: true });
  await c.send("Page.enable", {}, sessionId);
  await c.send("Network.enable", {}, sessionId);
  await c.send("Network.setBlockedURLs", { urls: ["*://archive.org/*", "*://*.archive.org/*", "https://*"] }, sessionId);
  for (const width of WIDTHS) {
    await c.send("Emulation.setDeviceMetricsOverride", { width, height: 800, deviceScaleFactor: 2, mobile: width < 768 }, sessionId);
    for (const page of PAGES) {
      const loaded = c.once("Page.loadEventFired", sessionId);
      await c.send("Page.navigate", { url: origin + page }, sessionId);
      await loaded;
      const { result } = await c.send("Runtime.evaluate", { expression: PROBE, returnByValue: true }, sessionId);
      const r = JSON.parse(result.value);
      const where = `${width}px ${page}`;
      if (r.scrollWidth > r.clientWidth) problems.push(`${where}: page scrolls sideways (${r.scrollWidth} > ${r.clientWidth}): ${r.wide.slice(0, 4).join("; ")}`);
      else if (r.wide.length) problems.push(`${where}: elements past the screen edge: ${r.wide.slice(0, 4).join("; ")}`);
      if (r.wrapped.length) problems.push(`${where}: header text wraps onto two lines: ${r.wrapped.join(", ")}`);
      if (r.small.length) problems.push(`${where}: touch targets under 44px: ${r.small.slice(0, 6).join("; ")}`);
      if (r.farNotes.length) problems.push(`${where}: note figures float away from their words: ${r.farNotes.slice(0, 4).join("; ")}`);
      if (r.text !== null && width < 768 && r.text < 18) problems.push(`${where}: letter text is ${r.text}px (minimum 18px)`);
    }
  }
  c.close();
} finally {
  if (browser) browser.proc.kill();
  server.close();
  rmSync(profile, { recursive: true, force: true });
}

if (problems.length) {
  problems.forEach((p) => console.error(p));
  console.error(`check_mobile: ${problems.length} problem(s)`);
  process.exit(1);
}
console.log(`check_mobile: ${PAGES.length} pages at ${WIDTHS.join(", ")}px: no sideways scroll, no wrapped header, touch targets 44px+, letter text 18px+, note figures against their words`);
