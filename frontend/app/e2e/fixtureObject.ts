import { readFixture } from "./mockApi";

/** Narrows a parsed JSON value to an object, and throws on anything else. */
export function asObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("expected a JSON object");
  }
  return Object.fromEntries(Object.entries(value));
}

/** Reads a recorded fixture as a JSON object. */
export function fixtureObject(name: string): Record<string, unknown> {
  const value: unknown = JSON.parse(readFixture(name));
  return asObject(value);
}
