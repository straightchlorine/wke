/// <reference types="node" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Returns the light-scheme hex value of a --wke-* colour token from src/tokens.css. */
export function lightToken(name: string): string {
  const css = readFileSync(fileURLToPath(new URL("../src/tokens.css", import.meta.url)), "utf8");
  const hex = css.match(new RegExp(`--wke-${name}:\\s*(#[0-9A-Fa-f]{6})\\b`))?.[1];
  if (!hex) throw new Error(`Token --wke-${name} not found in src/tokens.css`);
  return hex;
}
