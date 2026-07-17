import test from "node:test";
import assert from "node:assert/strict";
import { compactNumber, formatDuration } from "../src/format.js";

test("compactNumber switches from millions to billions at one billion", () => {
  assert.equal(compactNumber(999), "999");
  assert.equal(compactNumber(1_000), "1.0k");
  assert.equal(compactNumber(999_000_000), "999.0M");
  assert.equal(compactNumber(1_000_000_000), "1.0B");
  assert.equal(compactNumber(4_592_343_722), "4.6B");
});

test("compactNumber normalizes missing values to zero", () => {
  assert.equal(compactNumber(undefined), "0");
  assert.equal(compactNumber(null), "0");
});

test("formatDuration renders rounded minutes and accumulated hours", () => {
  assert.equal(formatDuration(0), "0m");
  assert.equal(formatDuration(10 * 60), "10m");
  assert.equal(formatDuration(75 * 60), "1h 15m");
  assert.equal(formatDuration(1250 * 60), "20h 50m");
});
