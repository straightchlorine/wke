import { defineConfig, devices } from "@playwright/test";
import { VIEWPORTS, projectGrep } from "../e2e/support";

// Runs the live specs against a `vite preview` on :4180 that proxies the real API.
// Start that stack first: there is no webServer.
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  fullyParallel: false,
  reporter: "dot",
  // The real API and its model take longer than the mocked one.
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: { baseURL: "http://localhost:4180" },
  // A test tagged with only(...) runs on the projects it names; an untagged test runs on both.
  projects: (["mobile-390", "desktop-1440"] as const).map((name) => ({
    name,
    grep: projectGrep(name),
    use: { ...devices["Desktop Chrome"], viewport: VIEWPORTS[name] },
  })),
});
