import { defineConfig } from "@playwright/test";

const secret = "test-only-beta-proxy-secret-" + "x".repeat(32);
export default defineConfig({
  testDir: "./tests/e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:18301", httpCredentials: { username: "beta", password: "test-only-beta-password" }, trace: "retain-on-failure" },
  webServer: [
    { command: `${process.env.BETA_TEST_PYTHON || "../backend/.venv/bin/python"} tests/e2e/fixture_backend.py`, url: "http://127.0.0.1:18380/__fixture/stats", reuseExistingServer: false, env: { BETA_PROXY_SECRET: secret, API_RATE_LIMIT_ENABLED: "0", DATABASE_URL: "postgresql+psycopg://unused:unused@127.0.0.1:1/unused" } },
    { command: "node tests/e2e/start-frontend.mjs", url: "http://127.0.0.1:18301/", reuseExistingServer: false, env: { PORT: "18301", HOSTNAME: "127.0.0.1", APP_BETA_MODE: "1", BETA_PROXY_SECRET: secret, BETA_ACCESS_MODE: "password", BETA_AUTH_PASSWORD: "test-only-beta-password", BETA_PUBLIC_ENABLED: "0", API_INTERNAL_BASE_URL: "http://127.0.0.1:18380" } },
    { command: "node tests/e2e/start-frontend.mjs", url: "http://127.0.0.1:18300/", reuseExistingServer: false, env: { PORT: "18300", HOSTNAME: "127.0.0.1", APP_BETA_MODE: "0", APP_AUTH_ENABLED: "1", APP_AUTH_USER: "owner", APP_AUTH_PASSWORD: "test-only-private-password", API_INTERNAL_BASE_URL: "http://127.0.0.1:18380" } },
    { command: "node tests/e2e/start-frontend.mjs", wait: { stdout: /Ready in/ }, reuseExistingServer: false, env: { PORT: "18302", HOSTNAME: "127.0.0.1", APP_BETA_MODE: "1", BETA_PROXY_SECRET: secret, BETA_ACCESS_MODE: "password", BETA_AUTH_PASSWORD: "", BETA_PUBLIC_ENABLED: "0", API_INTERNAL_BASE_URL: "http://127.0.0.1:18380" } }
  ]
});
