import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("visualizations use an independent chart range", () => {
  assert.match(source, /data-chart-range/);
  assert.match(source, /chart-range-form/);
  assert.match(source, /chart-range-dialog/);
  assert.match(source, /chartCustomRangeOpen/);
  assert.match(source, /chart_start/);
  assert.match(source, /chart_end/);
  assert.match(source, /describeChartRange\(data\.chart\)/);
  assert.match(source, /data\.chart\?\.daily \|\| data\.daily/);
});

test("visualizations keep separate default ranges", () => {
  assert.match(source, /chartRangeDefaults = \{ heatmap: "all", tokens: "30d", activity: "30d" \}/);
  assert.match(source, /activity: \{ range: chartRangeDefaults\.activity/);
  assert.match(source, /chartStateByVisualization\[activeVisualization\] = \{/);
  assert.match(source, /restoreChartState\(activeVisualization\)/);
  assert.match(source, /start: chartStartDate/);
  assert.match(source, /end: chartEndDate/);
});

test("Active time uses short day presets", () => {
  assert.match(source, /activityChartRangeOptions = \[[\s\S]*"3d"[\s\S]*"7d"[\s\S]*"14d"[\s\S]*"21d"[\s\S]*"30d"[\s\S]*"custom"/);
  assert.match(source, /visualization === "activity" \? activityChartRangeOptions : chartRangeOptions/);
});
