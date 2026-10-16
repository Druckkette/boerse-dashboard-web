import assert from "node:assert/strict";
import test from "node:test";
import { positiveDecimalInput } from "../src/lib/number-input.ts";
import { privateWriteOriginAllowed } from "../src/lib/auth/write-policy.ts";

test("invalid stop input is distinct from an explicit empty removal", () => {
  assert.equal(positiveDecimalInput("abc").kind, "invalid");
  for (const input of ["0", "-1", "Infinity", "12foo", "1,2.3"]) assert.equal(positiveDecimalInput(input).kind, "invalid");
  assert.equal(positiveDecimalInput("").kind, "empty");
  assert.deepEqual(positiveDecimalInput("12,50"), { kind: "value", value: 12.5 });
});

test("private writes reject cross-site and missing origins including TLS proxy cases", () => {
  const headers = (origin, site = "same-origin") => new Headers({ ...(origin ? { origin } : {}), host: "dashboard.example", "sec-fetch-site": site });
  assert.equal(privateWriteOriginAllowed(headers("https://dashboard.example"), "http://localhost:3000"), true);
  assert.equal(privateWriteOriginAllowed(headers("https://attacker.example"), "http://localhost:3000"), false);
  assert.equal(privateWriteOriginAllowed(headers("https://dashboard.example", "cross-site"), "http://localhost:3000"), false);
  assert.equal(privateWriteOriginAllowed(headers(null), "http://localhost:3000"), false);
  assert.equal(privateWriteOriginAllowed(headers("not-a-url"), "http://localhost:3000"), false);
});
