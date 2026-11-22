// Tests for scripts/png_palette.mjs (run by ./verify with node --test). No network, no browser.
import assert from "node:assert/strict";
import { test } from "node:test";
import { crc32, deflateSync, inflateSync } from "node:zlib";
import { decode, toPalettePng } from "../scripts/png_palette.mjs";

function chunk(type, data) {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, "latin1");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, crc]);
}

// An RGB PNG whose rows use the "sub" filter, as a browser may write them.
function rgbPng(width, height, colour) {
  const rows = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) {
    rows[y * (width * 3 + 1)] = 1;
    let prev = [0, 0, 0];
    for (let x = 0; x < width; x++) {
      const c = colour(x, y), at = y * (width * 3 + 1) + 1 + x * 3;
      for (let k = 0; k < 3; k++) rows[at + k] = (c[k] - prev[k]) & 255;
      prev = c;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

test("decode undoes row filters", () => {
  const png = rgbPng(4, 2, (x, y) => [x * 60, y * 100, 7]);
  const { width, height, pixels } = decode(png);
  assert.equal(width, 4);
  assert.equal(height, 2);
  assert.equal(pixels[5], (60 << 16) | (100 << 8) | 7);
});

test("a flat picture becomes a smaller palette PNG with the same colours", () => {
  const ink = [18, 18, 20], lamp = [200, 54, 27], paper = [255, 255, 255];
  const png = rgbPng(300, 200, (x, y) => (y < 20 ? lamp : (x + y) % 7 === 0 ? ink : paper));
  const out = toPalettePng(png);
  assert.ok(out && out.length < png.length);
  assert.equal(out[25], 3, "colour type 3 (palette)");
  const plte = out.indexOf("PLTE", 0, "latin1");
  const n = out.readUInt32BE(plte - 4) / 3;
  const colours = Array.from({ length: n }, (_, i) => [...out.subarray(plte + 4 + i * 3, plte + 7 + i * 3)].join(","));
  assert.deepEqual(new Set(colours), new Set([ink, lamp, paper].map((c) => c.join(","))));
  const idat = out.indexOf("IDAT", 0, "latin1");
  const rows = inflateSync(out.subarray(idat + 4, idat + 4 + out.readUInt32BE(idat - 4)));
  assert.equal(colours[rows[1]], lamp.join(","), "first pixel is lamp red");
});

test("a photograph is left alone", () => {
  let seed = 1;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) & 255);
  assert.equal(toPalettePng(rgbPng(120, 100, () => [rnd(), rnd(), rnd()])), null);
});
