import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("tokens over time uses only the global range", () => {
  assert.doesNotMatch(source, /data-chart-range|chart-range-form|chart_start|chart_end/);
  assert.match(source, /describeRange\(data\.chart\)/);
});
