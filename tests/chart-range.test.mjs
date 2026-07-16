import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("visualizations use an independent chart range", () => {
  assert.match(source, /data-chart-range/);
  assert.match(source, /chart-range-form/);
  assert.match(source, /chart_start/);
  assert.match(source, /chart_end/);
  assert.match(source, /describeChartRange\(data\.chart\)/);
  assert.match(source, /data\.chart\?\.daily \|\| data\.daily/);
});
