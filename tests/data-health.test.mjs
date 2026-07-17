import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("Data Health is the third details tab after Requests", () => {
  assert.match(source, /data-table-view="usage"[\s\S]*>Models<\/button>[\s\S]*data-table-view="requests"[\s\S]*>Requests<\/button>[\s\S]*data-table-view="diagnostics"[\s\S]*>Data Health<\/button>/);
});

test("Data Health replaces unavailable telemetry with index and source status", () => {
  assert.match(source, /function renderDataHealth\(diagnostics\)/);
  assert.match(source, /Indexed updates/);
  assert.match(source, /Provider coverage/);
  assert.match(source, /Source registry/);
  assert.doesNotMatch(source, /Telemetry Diagnostics/);
  assert.doesNotMatch(source, /No token telemetry in this range/);
});

test("Data Health uses compact responsive grids instead of a wide table", () => {
  assert.match(styles, /\.health-metrics\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s);
  assert.match(styles, /\.health-provider-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3,/s);
  assert.match(styles, /\.health-source-row\s*\{[^}]*grid-template-columns:/s);
  assert.match(styles, /@media \(max-width: 520px\)[\s\S]*\.health-source-row\s*\{[^}]*grid-template-columns:\s*1fr/s);
});
