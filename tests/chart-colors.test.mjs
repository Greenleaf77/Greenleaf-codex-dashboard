import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  BASE_MODEL_COLORS,
  chartColorMap,
  modelColorForSlot,
} from "../src/chart-colors.js";

const BASE = [
  "#1E88E5", "#FB8C00", "#43A047", "#D81B60", "#C9A227",
  "#5E35B1", "#00ACC1", "#E53935", "#00897B", "#8D6E63",
];

test("the first ten slots use the approved base families", () => {
  assert.deepEqual(BASE_MODEL_COLORS, BASE);
  assert.deepEqual(Array.from({ length: 10 }, (_, slot) => modelColorForSlot(slot)), BASE);
});

test("tone and shifted blocks remain distinct", () => {
  const firstForty = Array.from({ length: 40 }, (_, slot) => modelColorForSlot(slot));
  const firstEighty = Array.from({ length: 80 }, (_, slot) => modelColorForSlot(slot));
  assert.equal(new Set(firstForty).size, 40);
  assert.equal(new Set(firstEighty).size, 80);
  assert.notEqual(modelColorForSlot(0), modelColorForSlot(10));
  assert.notEqual(modelColorForSlot(0), modelColorForSlot(40));
  assert.match(modelColorForSlot(84), /^#[0-9A-F]{6}$/);
});

test("shifted blocks do not repeat after one hue rotation", () => {
  const colors = Array.from({ length: 840 }, (_, slot) => modelColorForSlot(slot));
  assert.equal(new Set(colors).size, 840);
});

test("chart colors follow the current legend order and ignore persisted metadata", () => {
  const models = [
    { model: "gpt", color_slot: 84, raw_model: "legacy-gpt" },
    { model: "claude", color_slot: 0, raw_model: "legacy-claude" },
  ];
  const colors = chartColorMap(models);
  assert.equal(colors.get("gpt"), modelColorForSlot(0));
  assert.equal(colors.get("claude"), modelColorForSlot(1));

  const reordered = chartColorMap(models.toReversed());
  assert.equal(reordered.get("claude"), modelColorForSlot(0));
  assert.equal(reordered.get("gpt"), modelColorForSlot(1));
});

test("token bars and legend share one color map per render", () => {
  const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
  assert.match(source, /const colors = chartColorMap\(models\)/);
  assert.match(source, /renderChartBar\(day, models, colors,/);
  assert.match(source, /renderChartLegend\(models, colors\)/);
  assert.match(source, /colors\.get\(item\.model\) \|\| modelColorForSlot\(0\)/);
  assert.match(source, /colors\.get\(row\.model\) \|\| modelColorForSlot\(0\)/);
  assert.doesNotMatch(source, /modelColor\(/);
});

test("invalid direct slots are rejected", () => {
  assert.throws(() => modelColorForSlot(-1), RangeError);
  assert.throws(() => modelColorForSlot(1.5), RangeError);
});
