// Draw the share cards (DECISIONS.md D31). Hugo writes card.html beside the home page, each book and each letter;
// this opens each one in headless Chromium at 1200×630, fits its long lines, saves card.png beside it and deletes
// the card.html, so no card page is ever published. Requests to anything but the local server are blocked.
//
// A card whose text cannot be fitted stops the run: nothing is published as a guess.
// Drawn cards are cached by the hash of their page, the fonts and this script, so a rebuild only draws what changed.
//
// Usage: node scripts/og_cards.mjs <built-site-dir>
//   OG_CACHE=<dir> to move the cache (default .cache/og in the repository); CHROME=/path/to/chromium.

import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { cdp, findChrome, launch, serve } from "./chromium.mjs";
import { availableParallelism } from "node:os";
import { Worker } from "node:worker_threads";

const TABS = 6;
const W = 1200;
const H = 630;
const here = dirname(fileURLToPath(import.meta.url));
const root = process.argv[2] && resolve(process.argv[2]);
if (!root || !existsSync(join(root, "index.html"))) {
  console.error("usage: node scripts/og_cards.mjs <built-site-dir>");
  process.exit(2);
}
const cacheDir = resolve(process.env.OG_CACHE || join(here, "..", ".cache", "og"));

function walk(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name === "card.html") out.push(p);
  }
  return out;
}

// Everything a card's pixels depend on beyond its own page: the fonts and these scripts (CSS and images have
// content-hashed names inside the page). Their hash goes into every card's cache key.
function sharedHash() {
  const h = createHash("sha256");
  h.update(readFileSync(fileURLToPath(import.meta.url))).update(readFileSync(join(here, "png_palette.mjs")));
  const fonts = join(root, "fonts");
  for (const f of readdirSync(fonts).sort()) h.update(f).update(readFileSync(join(fonts, f)));
  return h.digest("hex");
}

// Runs inside each card: wait for fonts and images, then step long text down until it fits, or report why not.
const FIT = `(async () => {
  await document.fonts.ready;
  const problems = [];
  for (const img of document.images) if (!img.complete || !img.naturalWidth) problems.push("image did not load: " + img.getAttribute("src"));
  if (!document.fonts.check("italic 30px 'Newsreader Text'") || !document.fonts.check("30px 'Newsreader Text'")) problems.push("Newsreader did not load");
  const q = (s) => document.querySelector(s);
  const box = (el) => el.getBoundingClientRect();
  const lines = (el) => Math.round(box(el).height / parseFloat(getComputedStyle(el).lineHeight));
  const steps = ["", "s1", "s2", "s3"];
  const fit = (el, ok, n = steps.length) => {
    for (const s of steps.slice(0, n)) {
      el.classList.remove("s1", "s2", "s3");
      if (s) el.classList.add(s);
      if (ok()) return true;
    }
    return false;
  };
  const kind = (document.body.className.match(/og-(\\w+)/) || [])[1];
  if (kind === "book") {
    const t = q(".text .title"), col = q(".text");
    if (!fit(t, () => lines(t) <= 4 && col.scrollHeight <= col.clientHeight + 1)) problems.push("the title does not fit in four lines");
  } else if (kind === "letter") {
    const words = q(".q"), who = q(".who"), foot = q(".foot"), head = q(".head");
    if (!fit(words, () => box(words).bottom <= box(who).top - 24)) problems.push("the first words run into the names");
    if (!fit(who, () => box(who).bottom <= box(foot).top - 12, 2)) problems.push("the names and date run into the footer");
    if (head.scrollWidth > head.clientWidth + 1) problems.push("the heading is cut off");
  } else if (kind === "home") {
    if (box(q(".line")).bottom > box(q(".foot")).top - 20) problems.push("the description runs into the footer");
  } else {
    problems.push("unknown card kind");
  }
  const d = document.documentElement;
  if (d.scrollWidth > ${W} || d.scrollHeight > ${H}) problems.push("the card is larger than ${W}×${H}");
  return problems;
})()`;

const cards = walk(root).sort();
mkdirSync(cacheDir, { recursive: true });
// Cards that could not be fitted are still drawn here, so a person can see what went wrong.
const failedDir = join(cacheDir, "failed");
rmSync(failedDir, { recursive: true, force: true });
mkdirSync(failedDir);
const shared = sharedHash();
const jobs = cards.map((file) => {
  const html = readFileSync(file, "utf8");
  // Hugo names the file (layouts/partials/og/file.html) because the page's og:image tag must name it too.
  const name = (html.match(/<meta name="?og-card-file"? content="?(card\.(?:png|jpg))"?>/) || [])[1];
  if (!name) throw new Error(`${file}: no og-card-file meta tag`);
  const ext = name.slice(5);
  const key = createHash("sha256").update(shared).update(html).digest("hex");
  return { file, url: "/" + relative(root, file).split(sep).join("/"), out: join(dirname(file), name), ext, cached: join(cacheDir, `${key}.${ext}`) };
});
const todo = jobs.filter((j) => !existsSync(j.cached));

// A pool of threads running png_palette.mjs; shrink(png) resolves to the palette PNG, or the original if it has
// too many colours for a palette.
const pool = Array.from({ length: Math.max(1, Math.min(4, availableParallelism() - 2)) }, () => {
  const w = new Worker(new URL("./png_palette.mjs", import.meta.url), { workerData: "png-palette" });
  w.waiting = new Map();
  w.on("message", ({ id, out, error }) => {
    const { resolve, reject } = w.waiting.get(id);
    w.waiting.delete(id);
    error ? reject(new Error(error)) : resolve(out ? Buffer.from(out) : null);
  });
  return w;
});
let shrinkId = 0;
function shrink(png) {
  const w = pool[shrinkId % pool.length];
  const id = ++shrinkId;
  return new Promise((resolve, reject) => {
    w.waiting.set(id, { resolve, reject });
    w.postMessage({ id, png });
  }).then((out) => out || png);
}
const writes = [];
const started = Date.now();
const problems = [];

if (todo.length) {
  const server = await serve(root);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const profile = mkdtempSync(join(tmpdir(), "pl-cards-"));
  let browser;
  try {
    browser = await launch(findChrome(), profile);
    const c = cdp(browser.ws);
    await c.ready;
    let next = 0;
    const tab = async () => {
      const { targetId } = await c.send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await c.send("Target.attachToTarget", { targetId, flatten: true });
      await c.send("Page.enable", {}, sessionId);
      await c.send("Network.enable", {}, sessionId);
      await c.send("Network.setBlockedURLs", { urls: ["https://*", "*://archive.org/*", "*://*.archive.org/*"] }, sessionId);
      await c.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false }, sessionId);
      while (next < todo.length) {
        const job = todo[next++];
        const loaded = c.once("Page.loadEventFired", sessionId);
        await c.send("Page.navigate", { url: origin + job.url }, sessionId);
        await loaded;
        const { result, exceptionDetails } = await c.send("Runtime.evaluate", { expression: FIT, awaitPromise: true, returnByValue: true }, sessionId);
        if (exceptionDetails) { problems.push(`${job.url}: ${exceptionDetails.text}`); continue; }
        const format = job.ext === "jpg" ? "jpeg" : "png";
        const shot = await c.send("Page.captureScreenshot", { format, quality: format === "jpeg" ? 88 : undefined, clip: { x: 0, y: 0, width: W, height: H, scale: 1 } }, sessionId);
        if (result.value.length) {
          const seen = join(failedDir, job.url.slice(1).replaceAll("/", "_").replace(/_?card\.html$/, "") + "." + job.ext);
          writeFileSync(seen, Buffer.from(shot.data, "base64"));
          problems.push(`${job.url}: ${result.value.join("; ")} (see ${seen})`);
          continue;
        }
        const image = Buffer.from(shot.data, "base64");
        if (format === "png") writes.push(shrink(image).then((out) => writeFileSync(job.cached, out)));
        else writeFileSync(job.cached, image);
      }
    };
    await Promise.all(Array.from({ length: Math.min(TABS, todo.length) }, tab));
    await Promise.all(writes);
    c.close();
  } finally {
    if (browser) {
      const exited = new Promise((r) => browser.proc.once("exit", r));
      browser.proc.kill();
      await exited;
    }
    server.close();
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

await Promise.all(pool.map((w) => w.terminate()));

if (problems.length) {
  problems.slice(0, 40).forEach((p) => console.error(p));
  console.error(`og_cards: ${problems.length} card(s) could not be drawn`);
  process.exit(1);
}

let bytes = 0;
for (const j of jobs) {
  copyFileSync(j.cached, j.out);
  bytes += readFileSync(j.out).length;
  rmSync(j.file);
}
// Forget cards no page uses any more, so the cache stays the size of the site.
const used = new Set(jobs.map((j) => j.cached));
for (const f of readdirSync(cacheDir)) if (/\.(png|jpg)$/.test(f) && !used.has(join(cacheDir, f))) rmSync(join(cacheDir, f));
const secs = ((Date.now() - started) / 1000).toFixed(1);
console.log(`og_cards: ${jobs.length} cards (${todo.length} drawn, ${jobs.length - todo.length} cached) in ${secs}s, ${(bytes / 1e6).toFixed(1)} MB`);
