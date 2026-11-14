/// <reference types="node" />
/**
 * Renders public/og.png, the Open Graph card, from an HTML template.
 * Run from frontend/app: node scripts/og.ts
 */
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { lightToken } from "./tokens.ts";

const pub = (name: string) => fileURLToPath(new URL(`../public/${name}`, import.meta.url));
const font = (name: string) =>
  `data:font/woff2;base64,${readFileSync(pub(`fonts/${name}`)).toString("base64")}`;
const color = (name: string) => lightToken(name);

const ICON = readFileSync(pub("favicon.svg"), "utf8").replace(
  /^<svg /,
  '<svg width="100%" height="100%" ',
);

// A verbatim sentence from revision 1382808793 of the Wikipedia article
// "Jesus", the article the backend tests record. Wikipedia text is CC BY-SA
// 4.0, so the card credits Wikipedia and names the licence.
const QUOTE = {
  title: "Jesus",
  revision: 1382808793,
  license: "CC BY-SA 4.0",
  text: "He is the central figure of Christianity, the world's largest religion.",
};
const BUDGETS = [2000, 8000, 32000];
const SELECTED = 8000;
const k = (tokens: number) => `${tokens / 1000}k`;

const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @font-face { font-family: Newsreader; font-weight: 200 800; src: url("${font("newsreader-latin-wght-normal.woff2")}"); }
  @font-face { font-family: Archivo; font-weight: 100 900; font-stretch: 62% 125%; src: url("${font("archivo-latin-wdth-normal.woff2")}"); }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px; padding: 72px;
    display: grid; grid-template-columns: 1fr 560px; gap: 56px;
    background: ${color("paper")}; color: ${color("ink")}; font-family: Newsreader, serif;
    box-shadow: inset 0 0 0 1px ${color("rule")};
  }
  .sans { font-family: Archivo, sans-serif; font-stretch: 92%; }
  .left { display: flex; flex-direction: column; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 16px; }
  .icon { width: 44px; height: 44px; }
  .wordmark { font-weight: 600; font-size: 20px; letter-spacing: 0.08em; }
  h1 { font-size: 58px; font-weight: 400; line-height: 1.06; letter-spacing: -0.01em; }
  .lead { font-size: 30px; line-height: 1.3; color: ${color("ink-2")}; margin-top: 22px; text-wrap: balance; }
  .domain { font-size: 20px; color: ${color("ink-3")}; letter-spacing: 0.02em; }
  .right { display: flex; flex-direction: column; }
  .card { background: ${color("sheet")}; border: 1px solid ${color("rule-strong")}; padding: 30px 34px 26px; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  .kicker { font-size: 18px; font-weight: 600; letter-spacing: 0.12em; color: ${color("ink-3")}; }
  .segmented { display: inline-flex; border: 1px solid ${color("ink")}; }
  .segmented span { font-size: 22px; font-weight: 500; color: ${color("ink-2")}; padding: 4px 16px; border-right: 1px solid ${color("ink")}; }
  .segmented span:last-child { border-right: 0; }
  .segmented .on { background: ${color("wash")}; color: ${color("accent-ink")}; font-weight: 600; box-shadow: inset 0 -3px 0 ${color("accent")}; }
  .quote { font-size: 30px; line-height: 1.4; margin-top: 14px; }
  sup { font-family: Archivo, sans-serif; font-size: 17px; font-weight: 600; color: ${color("accent")}; margin-left: 2px; }
  .cite { margin-top: 18px; padding-top: 12px; border-top: 1px solid ${color("rule")}; font-size: 20px; color: ${color("ink-2")}; font-variant-numeric: tabular-nums; }
  .cite b { color: ${color("accent")}; font-weight: 600; }
  .budgets { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; gap: 12px; padding-top: 28px; }
  .label { font-size: 22px; color: ${color("ink-2")}; margin-bottom: 4px; }
  .bar { height: 30px; background: ${color("rule-strong")}; }
  .on .label { color: ${color("accent-ink")}; font-weight: 600; }
  .on .bar { background: ${color("accent")}; }
</style>
</head>
<body>
  <div class="left">
    <div class="brand"><div class="icon">${ICON}</div><div class="wordmark sans">WIKIPEDIA KNOWLEDGE EXPLORER</div></div>
    <div>
      <h1>Any topic, cut to the token budget you need.</h1>
      <p class="lead sans">Cited context from Wikipedia, for people and LLMs.</p>
    </div>
    <span class="domain sans">wke.piotrkrzysztof.dev</span>
  </div>
  <div class="right">
    <div class="card">
      <div class="head">
        <div class="kicker sans">${QUOTE.title.toUpperCase()}</div>
        <div class="segmented sans">${BUDGETS.map((b) => `<span${b === SELECTED ? ' class="on"' : ""}>${k(b)}</span>`).join("")}</div>
      </div>
      <p class="quote">${QUOTE.text}<sup>1</sup></p>
      <div class="cite sans"><b>1</b>&nbsp; Wikipedia, ${QUOTE.title}, revision ${QUOTE.revision}, ${QUOTE.license}</div>
    </div>
    <div class="budgets sans">
      ${BUDGETS.map(
        (b) => `<div${b === SELECTED ? ' class="on"' : ""}>
        <div class="label">${k(b)} tokens</div>
        <div class="bar" style="width: ${(100 * b) / BUDGETS.at(-1)!}%"></div>
      </div>`,
      ).join("")}
    </div>
  </div>
</body>
</html>`;

async function main() {
  const browser = await chromium.launch();
  // The light scheme keeps the dark-mode rule in favicon.svg from applying.
  const page = await browser.newPage({
    viewport: { width: 1200, height: 630 },
    colorScheme: "light",
  });
  await page.setContent(html);
  await page.evaluate(() => document.fonts.ready);
  const problems = await page.evaluate(() => [
    ...(["Newsreader", "Archivo"] as const)
      .filter((family) => !document.fonts.check(`400 16px ${family}`))
      .map((family) => `font ${family} did not load`),
    ...(document.documentElement.scrollHeight > 630 || document.documentElement.scrollWidth > 1200
      ? ["content overflows the 1200x630 card"]
      : []),
  ]);
  if (problems.length > 0) throw new Error(problems.join("; "));
  const outPath = pub("og.png");
  await page.screenshot({ path: outPath, type: "png" });
  await browser.close();
  console.log(`Wrote ${outPath}`);
}

void main();
