/// <reference types="node" />
/**
 * Writes dist/third-party-licenses.txt with the licence text of every
 * production dependency, because the bundled JavaScript drops their notices.
 * Runs after `vite build`.
 */
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

interface Dependency {
  name: string;
  versions: string[];
  paths: string[];
}

const LICENSE_FILE = /^(licen[cs]e|copying)(\.(md|txt))?$/i;

const output = execFileSync("pnpm", ["licenses", "list", "--prod", "--json"], {
  encoding: "utf8",
});
const byLicense: unknown = JSON.parse(output);

const isStrings = (v: unknown) => Array.isArray(v) && v.every((x) => typeof x === "string");

// pnpm prints an object keyed by licence name, each holding its packages.
function isDependencyMap(value: unknown): value is Record<string, Dependency[]> {
  return (
    typeof value === "object" &&
    value !== null &&
    Object.values(value).every(
      (deps) =>
        Array.isArray(deps) &&
        deps.every(
          (d: Partial<Record<keyof Dependency, unknown>>) =>
            typeof d.name === "string" && isStrings(d.versions) && isStrings(d.paths),
        ),
    )
  );
}
if (!isDependencyMap(byLicense)) throw new Error("unexpected `pnpm licenses list` output");

const sections = Object.entries(byLicense)
  .flatMap(([license, deps]) => deps.map((dep) => ({ license, ...dep })))
  .toSorted((a, b) => a.name.localeCompare(b.name))
  .map(({ license, name, versions, paths }) => {
    const dir = paths[0] ?? "";
    const file = readdirSync(dir).find((entry) => LICENSE_FILE.test(entry));
    if (!file) throw new Error(`${name} has no licence file in ${dir}`);
    const text = readFileSync(join(dir, file), "utf8").trim();
    return `${name} ${versions.join(", ")} (${license})\n\n${text}\n`;
  });

const outPath = fileURLToPath(new URL("../dist/third-party-licenses.txt", import.meta.url));
writeFileSync(
  outPath,
  `Third-party software bundled into this site.\n\n${sections.join(`\n${"-".repeat(72)}\n\n`)}`,
);
console.log(`Wrote ${outPath} (${sections.length} packages)`);
