import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { chartHeightPercent } from "../src/chart-scale.js";

test("chart heights preserve a linear token scale without a visual floor", () => {
  assert.equal(chartHeightPercent(0, 100), 0);
  assert.equal(chartHeightPercent(25, 100), 25);
  assert.equal(chartHeightPercent(50, 100), 50);
  assert.equal(chartHeightPercent(100, 100), 100);
  assert.equal(chartHeightPercent(0.1, 100), 0.1);
});

test("chart CSS does not reintroduce minimum bar or segment heights", () => {
  const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
  assert.doesNotMatch(styles, /\.stacked-bar\s*\{[^}]*min-height/s);
  assert.doesNotMatch(styles, /\.bar-segment\s*\{[^}]*min-height/s);
  assert.doesNotMatch(source, /Math\.max\(2,\s*\(tokens \/ maxTokens\)/);
});
