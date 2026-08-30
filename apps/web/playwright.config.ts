import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  globalSetup: require.resolve("./e2e/global-setup"),
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000",
    storageState: "e2e/.auth/state.json",
    trace: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
