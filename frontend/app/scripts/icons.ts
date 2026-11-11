/// <reference types="node" />
/**
 * Renders the PNG and ICO icon set in public/ from public/favicon.svg.
 * Run from frontend/app: node scripts/icons.ts
 * The ICO step needs python3 with Pillow. Without it the existing .ico stays.
 */
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { lightToken } from "./tokens.ts";

const PAPER = lightToken("paper");
const pub = (name: string) => fileURLToPath(new URL(`../public/${name}`, import.meta.url));

// The root svg gets 100% width and height so it fills its box.
const svg = readFileSync(pub("favicon.svg"), "utf8").replace(
  /^<svg /,
  '<svg width="100%" height="100%" ',
);

/**
 * Each entry is the file name, the canvas size in px, the share of the canvas
 * the mark fills, and whether the background is opaque paper.
 */
const TARGETS: [string, number, number, boolean][] = [
  ["favicon-16x16.png", 16, 1, false],
  ["favicon-32x32.png", 32, 1, false],
  ["apple-touch-icon.png", 180, 0.6, true],
  // Both android-chrome icons are maskable, so the mark stays inside the inner
  // 80 percent safe zone.
  ["android-chrome-192x192.png", 192, 0.6, true],
  ["android-chrome-512x512.png", 512, 0.56, true],
];

function page(size: number, frac: number, opaque: boolean): string {
  const mark = Math.round(size * frac);
  return `<!doctype html><html><body style="margin:0;width:${size}px;height:${size}px;background:${
    opaque ? PAPER : "transparent"
  };display:flex;align-items:center;justify-content:center"><div style="width:${mark}px;height:${mark}px">${svg}</div></body></html>`;
}

async function main() {
  const browser = await chromium.launch();
  // The light colour scheme keeps the dark-mode media rule in favicon.svg from
  // applying.
  const ctx = await browser.newContext({ deviceScaleFactor: 1, colorScheme: "light" });
  for (const [name, size, frac, opaque] of TARGETS) {
    const p = await ctx.newPage();
    await p.setViewportSize({ width: size, height: size });
    await p.setContent(page(size, frac, opaque));
    const buf = await p.screenshot({ type: "png", omitBackground: !opaque });
    writeFileSync(pub(name), buf);
    await p.close();
    console.log(`Wrote ${name}`);
  }
  await browser.close();

  const py =
    "from PIL import Image; import sys;" +
    "im=Image.open(sys.argv[1]).convert('RGBA');" +
    "im.save(sys.argv[3],format='ICO',sizes=[(16,16),(32,32)],append_images=[Image.open(sys.argv[2]).convert('RGBA')])";
  try {
    execFileSync("python3", [
      "-c",
      py,
      pub("favicon-32x32.png"),
      pub("favicon-16x16.png"),
      pub("favicon.ico"),
    ]);
    console.log("Wrote favicon.ico");
  } catch {
    console.log("Pillow unavailable; favicon.ico left unchanged");
  }
}

void main();
