import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("Active time keeps a persistent pressed-state workdays toggle", () => {
  assert.match(source, /workdaysOnly/);
  assert.match(source, /params\.set\("workdays", "1"\)/);
  assert.match(source, /<button[^>]*id="workdays-only"[^>]*aria-pressed="\$\{workdaysOnly\}"/);
  assert.match(source, /data-workdays-only/);
  assert.doesNotMatch(source, /id="workdays-only" type="checkbox"/);
  assert.match(source, /workdaysOnly = !workdaysOnly;[\s\S]*syncUrl\(\);[\s\S]*refresh\(\);/);
  assert.match(source, /Workdays only/);
});

test("excluded activity remains visible with explicit treatment", () => {
  assert.match(source, /excluded_active_seconds/);
  assert.match(source, /Excluded non-working day/);
  assert.match(source, /non-working days are dimmed and excluded from totals/);
  assert.match(styles, /\.activity-time-bar\.excluded/);
  assert.match(styles, /\.bar-slot\.excluded-day::before/);
  assert.match(styles, /repeating-linear-gradient/);
});

test("activity details are available from keyboard focus", () => {
  assert.match(source, /class="bar-slot[^"\n]*"[^>]*tabindex="0"[^>]*aria-label=/);
  assert.match(source, /class="activity-time-segment excluded"[^>]*tabindex="0"[^>]*aria-label=/);
  assert.match(source, /item\.addEventListener\("focus", showChartTooltip\)/);
  assert.match(source, /item\.addEventListener\("blur", hideHeatTooltip\)/);
  assert.match(styles, /\.activity-time-segment:focus-visible/);
  assert.match(styles, /outline-offset:\s*-2px/);
});

test("Active time range presets never wrap inside the panel", () => {
  assert.match(styles, /\.chart-range-tabs\s*\{[^}]*flex-wrap:\s*nowrap/s);
  assert.match(styles, /\.chart-range-tabs\s*\{[^}]*width:\s*max-content/s);
  assert.match(source, /viz-primary-controls[\s\S]*id="workdays-only"[\s\S]*chart-filter-scroll[\s\S]*chart-range-tabs/);
  assert.match(styles, /\.chart-filter-scroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.doesNotMatch(styles, /\.chart-filter\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(styles, /@media[^}]*[\s\S]*?\.chart-filter\s*\{[^}]*justify-content:\s*flex-start/s);
});

test("Active time keeps neutral tooltips outside workdays mode", () => {
  assert.match(source, /const title =[^;]+;[\s\S]*const includedTooltip = workdaysOnly/);
  assert.match(source, /workdaysOnly\s*\?[^:]*requests counted[^:]*:\s*""/s);
  assert.match(source, /\.activity-time-segment\[data-tooltip-title\]/);
  assert.match(source, /classList\.contains\("activity-time-segment"\)/);
});

test("weekday controls expose full accessible names", () => {
  assert.match(source, /full:\s*"Monday"/);
  assert.match(source, /aria-label="\$\{option\.full\} is a non-working day"/);
});
