import { defineConfig, devices } from "@playwright/test";
import { PROJECT_NAMES, VIEWPORTS, projectGrep } from "./e2e/support";

const PORT = 4173;
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env["CI"],
  retries: process.env["CI"] ? 2 : 0,
  reporter: "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: {
    command: `vite preview --port ${PORT}`,
    url: baseURL,
    reuseExistingServer: !process.env["CI"],
  },
  // A test tagged with only(...) runs on the projects it names; an untagged test runs on all of them.
  projects: PROJECT_NAMES.map((name) => ({
    name,
    grep: projectGrep(name),
    use: { ...devices["Desktop Chrome"], viewport: VIEWPORTS[name] },
  })),
});
