import type { Page } from "@playwright/test";

type Rgba = readonly [number, number, number, number];

function parseColour(value: string): Rgba {
  const match = /^rgba?\(([^)]+)\)$/.exec(value);
  const parts = (match?.[1] ?? "")
    .split(/[ ,/]+/)
    .filter(Boolean)
    .map(Number);
  const [r, g, b, a = 1] = parts;
  if (r === undefined || g === undefined || b === undefined || parts.some(Number.isNaN)) {
    throw new Error(`cannot compute contrast: unsupported colour "${value}"`);
  }
  return [r, g, b, a];
}

/** Draws `top` over the opaque colour `under`. */
function over(top: Rgba, under: Rgba): Rgba {
  const [r, g, b, a] = top;
  const mix = (front: number, back: number) => front * a + back * (1 - a);
  return [mix(r, under[0]), mix(g, under[1]), mix(b, under[2]), 1];
}

function linear(channel: number): number {
  const x = channel / 255;
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgba): number {
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

/**
 * Returns the WCAG contrast between an element's text colour and the backgrounds layered behind it.
 * It throws on a colour it cannot read and on a background image, because a wrong ratio would pass a test it should fail.
 * The same maths lives in scripts/contrast.py, which checks the token pairs from tokens.css; this one measures what the browser rendered.
 */
export async function contrastOf(page: Page, selector: string): Promise<number> {
  const { text, backgrounds } = await page
    .locator(selector)
    .first()
    .evaluate((el) => {
      const layers: { colour: string; image: string }[] = [];
      for (let node: Element | null = el; node; node = node.parentElement) {
        const style = getComputedStyle(node);
        layers.push({ colour: style.backgroundColor, image: style.backgroundImage });
      }
      return { text: getComputedStyle(el).color, backgrounds: layers };
    });

  // Walk out to the first opaque layer, then draw the layers above it back in order.
  const stack: Rgba[] = [];
  let opaque = false;
  for (const { colour, image } of backgrounds) {
    if (image !== "none") {
      throw new Error(`cannot compute contrast: background image "${image}"`);
    }
    const layer = parseColour(colour);
    if (layer[3] > 0) {
      stack.push(layer);
    }
    if (layer[3] === 1) {
      opaque = true;
      break;
    }
  }
  if (!opaque) {
    throw new Error(`cannot compute contrast: no opaque background behind "${selector}"`);
  }
  const base = stack.toReversed().reduce((under, layer) => over(layer, under));
  const foreground = over(parseColour(text), base);
  const [a, b] = [luminance(foreground), luminance(base)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
