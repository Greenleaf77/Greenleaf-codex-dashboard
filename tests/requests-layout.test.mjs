import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("Requests renders grouped totals as readable time windows", () => {
  assert.match(source, /formatRequestWindow\(item\.bucket_start, item\.bucket_end, payload\.timezone\)/);
  assert.match(source, /summed in this window/);
  assert.doesNotMatch(source, /<strong>\$\{escapeHtml\(item\.bucket_start\)\}<\/strong>/);
});

test("Requests footer identifies the calculation timezone", () => {
  assert.match(source, /class="requests-footer"/);
  assert.match(source, /Times, date boundaries, and grouped totals are calculated in/);
  assert.match(source, /requestTimezoneLabel\(payload\)/);
});
