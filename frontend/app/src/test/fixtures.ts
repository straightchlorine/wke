import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { DossierView } from "../api/dossier";

/** Reads a file from e2e/fixtures, the recorded API responses the tests share. */
export function fixtureText(name: string): string {
  return readFileSync(resolve(process.cwd(), "e2e/fixtures", name), "utf-8");
}

/** Loads a recorded dossier in the flat shape the components read. */
export function loadDossier(name = "dossier_1095706_8000.json"): DossierView {
  return JSON.parse(fixtureText(name));
}
