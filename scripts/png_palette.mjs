// Shrink a screenshot of a share card to a palette PNG (DECISIONS.md D31). A text card is ink on white paper, so
// nearly every pixel is one of a few colours or a blend at a letter's edge; storing up to 256 of them as a palette
// makes the file about a third of Chromium's full-colour PNG. No dependencies: Node's zlib does the compression.
//
// toPalettePng(png) returns the smaller PNG, or null when the picture has too many colours to look right
// (a photograph); the caller then keeps the original.

import { isMainThread, parentPort, workerData } from "node:worker_threads";
import { crc32, deflateSync, inflateSync } from "node:zlib";

const SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const PALETTE = 256;
// Past this many distinct colours the picture is not flat artwork, and a palette would band it visibly.
const MAX_DISTINCT = 6000;

function chunks(png) {
  if (!png.subarray(0, 8).equals(SIGNATURE)) throw new Error("not a PNG");
  const out = [];
  for (let at = 8; at < png.length; ) {
    const len = png.readUInt32BE(at);
    out.push({ type: png.toString("latin1", at + 4, at + 8), data: png.subarray(at + 8, at + 8 + len) });
    at += 12 + len;
  }
  return out;
}

function paeth(a, b, c) {
  const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

// Decode an 8-bit RGB or RGBA, non-interlaced PNG (what Chromium writes) to packed 0xRRGGBB values.
export function decode(png) {
  const all = chunks(png);
  const ihdr = all.find((c) => c.type === "IHDR").data;
  const width = ihdr.readUInt32BE(0), height = ihdr.readUInt32BE(4);
  const depth = ihdr[8], type = ihdr[9], interlace = ihdr[12];
  if (depth !== 8 || (type !== 2 && type !== 6) || interlace !== 0) throw new Error(`unsupported PNG (depth ${depth}, type ${type})`);
  const bpp = type === 6 ? 4 : 3;
  const raw = inflateSync(Buffer.concat(all.filter((c) => c.type === "IDAT").map((c) => c.data)));
  const stride = width * bpp;
  const prev = new Uint8Array(stride), cur = new Uint8Array(stride);
  const pixels = new Uint32Array(width * height);
  for (let y = 0; y < height; y++) {
    const f = raw[y * (stride + 1)];
    const row = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? cur[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
      const pred = f === 0 ? 0 : f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : f === 4 ? paeth(a, b, c) : -1;
      if (pred < 0) throw new Error(`bad PNG filter ${f}`);
      cur[i] = (row[i] + pred) & 255;
    }
    for (let x = 0; x < width; x++) pixels[y * width + x] = (cur[x * bpp] << 16) | (cur[x * bpp + 1] << 8) | cur[x * bpp + 2];
    prev.set(cur);
  }
  return { width, height, pixels };
}

function chunk(type, data) {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, "latin1");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, crc]);
}

const dist2 = (p, q) => {
  const dr = (p >> 16) - (q >> 16), dg = ((p >> 8) & 255) - ((q >> 8) & 255), db = (p & 255) - (q & 255);
  return dr * dr * 3 + dg * dg * 4 + db * db * 2;
};

export function toPalettePng(png) {
  const { width, height, pixels } = decode(png);
  const counts = new Map();
  // Most of a card is runs of one colour (paper), so count runs rather than pixels.
  for (let i = 0; i < pixels.length; ) {
    const p = pixels[i];
    let j = i + 1;
    while (j < pixels.length && pixels[j] === p) j++;
    counts.set(p, (counts.get(p) || 0) + j - i);
    i = j;
  }
  if (counts.size > MAX_DISTINCT) return null;
  // The commonest colours become the palette: paper, the inks, the lamp red and their most frequent blends.
  // Every other colour, a rare edge blend, takes its nearest palette entry.
  const palette = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, PALETTE).map(([c]) => c);
  const index = new Map(palette.map((c, i) => [c, i]));
  for (const c of counts.keys()) {
    if (index.has(c)) continue;
    let best = 0, bestD = Infinity;
    for (let i = 0; i < palette.length; i++) {
      const d = dist2(c, palette[i]);
      if (d < bestD) { bestD = d; best = i; }
    }
    index.set(c, best);
  }
  const rows = Buffer.alloc((width + 1) * height);
  let last = -1, lastIndex = 0;
  for (let y = 0; y < height; y++) {
    rows[y * (width + 1)] = 0;
    for (let x = 0; x < width; x++) {
      const p = pixels[y * width + x];
      if (p !== last) { last = p; lastIndex = index.get(p); }
      rows[y * (width + 1) + 1 + x] = lastIndex;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 3; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const plte = Buffer.alloc(palette.length * 3);
  palette.forEach((c, i) => { plte[i * 3] = c >> 16; plte[i * 3 + 1] = (c >> 8) & 255; plte[i * 3 + 2] = c & 255; });
  const out = Buffer.concat([SIGNATURE, chunk("IHDR", ihdr), chunk("PLTE", plte), chunk("IDAT", deflateSync(rows, { level: 9 })), chunk("IEND", Buffer.alloc(0))]);
  return out.length < png.length ? out : null;
}

// Started as a worker thread by og_cards.mjs, so cards are shrunk on every core while Chromium draws the next ones.
if (!isMainThread && workerData === "png-palette") {
  parentPort.on("message", ({ id, png }) => {
    try {
      const out = toPalettePng(Buffer.from(png));
      parentPort.postMessage({ id, out });
    } catch (err) {
      parentPort.postMessage({ id, error: String(err) });
    }
  });
}
