// Open the built site in headless Chromium at phone and tablet widths and fail on layout faults:
//   - the page scrolls sideways (charts may scroll inside their own .chart-box);
//   - a button, menu toggle or block-level link is shorter than 44px;
//   - letter text is smaller than 18px;
//   - the logo or a header link wraps onto two lines.
// No dependencies: Node's built-in http and WebSocket talk to Chromium's DevTools protocol.
// Requests to anything but the local server are blocked, so the check needs no network.
//
// Usage: node scripts/check_mobile.mjs <built-site-dir>    (CHROME=/path/to/chromium to choose the browser)

import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { extname, join, normalize, sep } from "node:path";

const WIDTHS = [360, 390, 768, 935, 1280];
const PAGES = [
  "/",
  "/collections/",
  "/collections/dostoevsky-family-friends-1914/",
  "/collections/dostoevsky-family-friends-1914/20/",
  "/collections/tipu-sultan-select-letters-1811/",
  "/collections/fifty-famous-letters-1930/",
  "/collections/vivekananda-letters-1944/1/",
  "/letter/adams-abigail-john-1776/",
  "/essay/thoreau-walking-1862/",
  "/about/",
  "/search/",
  "/explore/",
  "/explore/1840s/",
  "/people/",
  "/people/fyodor-dostoevsky/",
];
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2" };

const root = process.argv[2];
if (!root || !existsSync(join(root, "index.html"))) {
  console.error("usage: node scripts/check_mobile.mjs <built-site-dir>");
  process.exit(2);
}

function findChrome() {
  const candidates = [process.env.CHROME, "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"];
  const hit = candidates.find((c) => c && existsSync(c));
  if (!hit) {
    console.error("check_mobile: no Chromium or Chrome found; set CHROME=/path/to/browser");
    process.exit(2);
  }
  return hit;
}

function serve(dir) {
  const base = normalize(dir) + sep;
  const server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = normalize(join(dir, path));
    if (!file.startsWith(base) && file + sep !== base) { res.writeHead(403).end(); return; }
    if (existsSync(file) && statSync(file).isDirectory()) { file = join(file, "index.html"); }
    if (!existsSync(file)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function launch(chrome, profile) {
  const proc = spawn(chrome, [
    "--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--disable-extensions",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  return new Promise((resolve, reject) => {
    let buf = "";
    const timer = setTimeout(() => reject(new Error("Chromium did not start within 20s")), 20000);
    proc.stderr.on("data", (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(timer); resolve({ proc, ws: m[1] }); }
    });
    proc.on("exit", (code) => reject(new Error(`Chromium exited early (${code}): ${buf.slice(-400)}`)));
  });
}

function cdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      listeners.forEach((l) => l(msg));
    }
  });
  const ready = new Promise((resolve, reject) => { ws.addEventListener("open", resolve); ws.addEventListener("error", reject); });
  return {
    ready,
    send(method, params = {}, sessionId) {
      const msgId = ++id;
      ws.send(JSON.stringify({ id: msgId, method, params, sessionId }));
      return new Promise((resolve, reject) => pending.set(msgId, { resolve, reject }));
    },
    once(method, sessionId) {
      return new Promise((resolve) => {
        const l = (msg) => {
          if (msg.method === method && msg.sessionId === sessionId) { listeners.splice(listeners.indexOf(l), 1); resolve(msg.params); }
        };
        listeners.push(l);
      });
    },
    close() { ws.close(); },
  };
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
console.log(`check_mobile: ${PAGES.length} pages at ${WIDTHS.join(", ")}px: no sideways scroll, no wrapped header, touch targets 44px+, letter text 18px+`);
