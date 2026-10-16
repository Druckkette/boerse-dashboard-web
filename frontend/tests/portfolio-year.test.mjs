import assert from "node:assert/strict";
import test from "node:test";
import { portfolioYearStart, nextPortfolioYearCheck } from "../src/features/portfolio/portfolio-year.ts";

test("portfolio year changes at Berlin midnight even while UTC is still December", () => {
  assert.equal(portfolioYearStart(new Date("2026-12-31T22:59:59.000Z")), "2026-01-01");
  assert.equal(portfolioYearStart(new Date("2026-12-31T23:00:00.000Z")), "2027-01-01");
  assert.equal(nextPortfolioYearCheck(new Date("2026-12-31T22:59:59.000Z")), 1000);
  assert.equal(nextPortfolioYearCheck(new Date("2026-12-31T23:00:00.000Z")), 60000);
});
