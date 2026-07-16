import test from "node:test";
import assert from "node:assert/strict";
import { paginateRows, truncateModelName, USAGE_TABLE_PAGE_SIZE } from "../src/usage-table.js";

test("usage tables paginate by 15 rows", () => {
  const rows = Array.from({ length: 32 }, (_, index) => index + 1);

  assert.equal(USAGE_TABLE_PAGE_SIZE, 15);
  assert.deepEqual(paginateRows(rows, 1).items, rows.slice(0, 15));
  assert.deepEqual(paginateRows(rows, 2).items, rows.slice(15, 30));
  assert.deepEqual(paginateRows(rows, 3).items, rows.slice(30));
});

test("usage table pages are clamped to the available range", () => {
  const page = paginateRows([1, 2, 3], 99);

  assert.equal(page.page, 1);
  assert.equal(page.totalPages, 1);
});

test("model names longer than 20 characters use an explicit ellipsis", () => {
  assert.equal(truncateModelName("12345678901234567890"), "12345678901234567890");
  assert.equal(truncateModelName("123456789012345678901"), "12345678901234567890...");
});
