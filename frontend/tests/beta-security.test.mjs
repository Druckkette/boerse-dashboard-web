import assert from "node:assert/strict";
import test from "node:test";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import ts from "typescript";

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "./api-policy.json") return { url: new URL(specifier, context.parentURL).href, shortCircuit: true };
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith("/api-policy.json")) return { format: "module", shortCircuit: true, source: `export default ${readFileSync(new URL(url), "utf8")};` };
    if (url.includes("/lib/beta/") && url.endsWith(".ts")) return { format: "module", shortCircuit: true, source: ts.transpileModule(readFileSync(new URL(url), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText };
    return nextLoad(url, context);
  }
});
const { betaApiAllowed, betaPageAllowed, betaWriteOriginAllowed, isBetaMode } = await import("../src/lib/beta/policy.ts");
const { betaAccessConfigured, betaAuthorized } = await import("../src/lib/beta/auth.ts");
const { shouldAutoRefresh, refreshPollInterval, betaRefreshQueryKeys } = await import("../src/lib/beta/refresh-state.ts");
const rules = JSON.parse(readFileSync(new URL("../src/lib/beta/api-policy.json", import.meta.url), "utf8"));
const auth = (password, user = "beta") => new Headers({ authorization: "Basic " + Buffer.from(`${user}:${password}`).toString("base64") });
function configured(extra = {}) {
  for (const key of ["BETA_ACCESS_MODE", "BETA_PUBLIC_ENABLED", "BETA_AUTH_PASSWORD", "BETA_PROXY_SECRET", "APP_BETA_MODE"]) delete process.env[key];
  Object.assign(process.env, { APP_BETA_MODE: "1", BETA_PROXY_SECRET: "t".repeat(40), BETA_AUTH_PASSWORD: "test-only-shared-password", ...extra });
}

test("each explicit analysis route and only the two POST computations is allowed", () => {
  for (const rule of rules) {
    const path = rule.path.replace("{ticker}", "NVDA").replace("{group}", "software").replace("{job}", "beta_" + "a".repeat(32));
    assert.equal(betaApiAllowed(rule.method, path), true, path);
    for (const method of ["PUT", "PATCH", "DELETE"]) assert.equal(betaApiAllowed(method, path), false);
    assert.equal(betaApiAllowed(rule.method, path, "?role=admin"), false);
  }
  assert.equal(rules.filter(rule => rule.method === "POST").length, 2);
});

test("private paths, exports, jobs, direct preview, unknown endpoints and traversal are blocked", () => {
  for (const path of ["home", "portfolio", "workspace", "jobs", "settings", "setup", "trade-journal", "sell/preview", "sell/NVDA/manual", "stocks/NVDA/report.pdf", "stocks/screening/export", "stocks/institutional/13f/mappings", "industry-groups/review", "industry-groups/rs/diagnostics", "stocks/%2fportfolio/assessment", "stocks/../portfolio/assessment", "stocks/NVDA\\/assessment", "market/new-private-feature"]) {
    assert.equal(betaApiAllowed("GET", path), false, path);
    assert.equal(betaApiAllowed("POST", path), false, path);
  }
  assert.equal(betaApiAllowed("GET", "stocks/search", "?q=" + "a".repeat(401)), false);
  assert.equal(betaApiAllowed("POST", "jobs"), false);
});

test("HTML and RSC page gate allows beta pages and denies all private pages including extension bypasses", () => {
  for (const path of ["/", "/market", "/sectors", "/industry-groups", "/industry-groups/software", "/stocks", "/stocks/NVDA", "/sell-check"]) assert.equal(betaPageAllowed(path), true);
  for (const path of ["/portfolio", "/portfolio.png", "/sell-monitor", "/sell-monitor/NVDA", "/settings", "/setup", "/jobs", "/workspace", "/trade-journal", "/api/other"]) assert.equal(betaPageAllowed(path), false);
});

test("missing and malformed beta authentication cannot become public access", () => {
  configured({ BETA_AUTH_PASSWORD: "" });
  assert.equal(betaAccessConfigured(), false);
  assert.equal(betaAuthorized(auth("")), false);
  configured({ BETA_ACCESS_MODE: "unknown" });
  assert.equal(betaAccessConfigured(), false);
  configured({ BETA_PROXY_SECRET: "" });
  assert.equal(betaAccessConfigured(), false);
  configured({ APP_BETA_MODE: "true" });
  assert.equal(isBetaMode(), true);
  assert.equal(betaAccessConfigured(), false);
});

test("public access requires both explicit switches and a valid proxy credential", () => {
  configured({ BETA_ACCESS_MODE: "public", BETA_AUTH_PASSWORD: "" });
  assert.equal(betaAuthorized(new Headers()), false);
  process.env.BETA_PUBLIC_ENABLED = "1";
  assert.equal(betaAuthorized(new Headers()), true);
  delete process.env.BETA_PROXY_SECRET;
  assert.equal(betaAuthorized(new Headers()), false);
});

test("shared beta password is independent of private authentication and roles", () => {
  configured();
  process.env.APP_AUTH_PASSWORD = "private-owner-password";
  assert.equal(betaAuthorized(auth("test-only-shared-password")), true);
  assert.equal(betaAuthorized(auth("private-owner-password")), false);
  assert.equal(betaAuthorized(auth("test-only-shared-password", "owner")), false);
  assert.equal(betaAuthorized(new Headers({ "x-role": "admin", "x-beta-mode": "0" })), false);
  process.env.APP_BETA_MODE = "0";
  assert.equal(isBetaMode(), false);
});

test("POST origin gate rejects CSRF and server actions", () => {
  assert.equal(betaWriteOriginAllowed(new Headers({ origin: "https://beta.example", "sec-fetch-site": "same-origin" }), "https://beta.example"), true);
  assert.equal(betaWriteOriginAllowed(new Headers({ origin: "https://evil.example" }), "https://beta.example"), false);
  assert.equal(betaWriteOriginAllowed(new Headers(), "https://beta.example"), false);
  assert.equal(betaWriteOriginAllowed(new Headers({ origin: "https://beta.example", host: "beta.example" }), "http://localhost:3000"), true);
  process.env.BETA_PUBLIC_ORIGIN = "https://beta.example";
  try {
    assert.equal(betaWriteOriginAllowed(new Headers({ origin: "https://beta.example", host: "internal:3000" }), "http://localhost:3000"), true);
    assert.equal(betaWriteOriginAllowed(new Headers({ origin: "https://evil.example" }), "https://beta.example"), false);
  } finally { delete process.env.BETA_PUBLIC_ORIGIN; }
});

test("current stocks do not auto-refresh and stale data triggers at most one attempt per view", () => {
  assert.equal(shouldAutoRefresh(undefined, false), false);
  assert.equal(shouldAutoRefresh({ fresh: true }, false), false);
  assert.equal(shouldAutoRefresh({ fresh: false }, false), true);
  assert.equal(shouldAutoRefresh({ fresh: false }, true), false);
  assert.equal(refreshPollInterval({ finished: true }), false);
  assert.equal(refreshPollInterval({ finished: false }), 6000);
  const keys = betaRefreshQueryKeys("NVDA");
  for (const key of [["stock-assessment", "NVDA"], ["stock-screening"], ["stock-fundamentals", "NVDA"], ["stock-assessment-ranking"], ["stock-assessment-compare"]]) assert.equal(keys.some(value => JSON.stringify(value) === JSON.stringify(key)), true);
  assert.equal(keys.some(value => value[0] === "jobs"), false);
});


test("beta panel requests stay bounded and a failed request releases the slot", async () => {
  const { createRequestLimiter } = await import("../src/lib/beta/request-limiter.ts");
  const run = createRequestLimiter(1, 2);
  let active = 0, peak = 0;
  let release;
  const first = run(async () => { active++; peak = Math.max(peak, active); await new Promise(resolve => { release = resolve; }); active--; throw new Error("provider unavailable"); });
  const failure = assert.rejects(first, /provider unavailable/);
  const second = run(async () => { active++; peak = Math.max(peak, active); active--; return 2; });
  const third = run(async () => 3);
  await assert.rejects(run(async () => 4), /Zu viele/);
  release();
  await failure;
  assert.deepEqual(await Promise.all([second, third]), [2, 3]);
  assert.equal(peak, 1);
  assert.equal(await run(async () => 5), 5);
});
