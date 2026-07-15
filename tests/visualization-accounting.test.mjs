import test from "node:test";
import assert from "node:assert/strict";
import {
  WITH_CACHE,
  WITHOUT_CACHE,
  metricValue,
  resolveCacheMode,
  resolveIgnoreAutoReview
} from "../src/visualization-accounting.js";

test("cache accounting defaults to with cache and accepts explicit modes", () => {
  assert.equal(resolveCacheMode(null), WITH_CACHE);
  assert.equal(resolveCacheMode("invalid"), WITH_CACHE);
  assert.equal(resolveCacheMode(WITH_CACHE), WITH_CACHE);
  assert.equal(resolveCacheMode(WITHOUT_CACHE), WITHOUT_CACHE);
});

test("metricValue selects the accounting total and safely falls back", () => {
  const row = { total_tokens: 30, total_with_cached_tokens: 100 };
  assert.equal(metricValue(row, WITH_CACHE), 100);
  assert.equal(metricValue(row, WITHOUT_CACHE), 30);
  assert.equal(metricValue({ total_tokens: 30 }, WITH_CACHE), 30);
  assert.equal(metricValue({ total_tokens: 30, total_with_cached_tokens: null }, WITH_CACHE), 30);
  assert.equal(metricValue({ total_tokens: 30, total_with_cached_tokens: "invalid" }, WITH_CACHE), 30);
});

test("auto-review preference uses URL, then the new cookie, then false", () => {
  assert.equal(resolveIgnoreAutoReview("1", "0"), true);
  assert.equal(resolveIgnoreAutoReview("0", "1"), false);
  assert.equal(resolveIgnoreAutoReview(null, "1"), true);
  assert.equal(resolveIgnoreAutoReview(null, "0"), false);
  assert.equal(resolveIgnoreAutoReview(null, null), false);
});
