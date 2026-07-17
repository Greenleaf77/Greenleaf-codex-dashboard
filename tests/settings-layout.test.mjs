import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("Unibase operation progress wraps within the settings section", () => {
  assert.match(styles, /\.unibase-settings\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(styles, /\.operation-progress\s*\{[^}]*min-width:\s*0/s);
  assert.match(styles, /\.operation-progress progress\s*\{[^}]*max-width:\s*100%/s);
  assert.match(styles, /\.operation-progress code\s*\{[^}]*overflow-wrap:\s*anywhere/s);
});

test("operation polling preserves stable Settings controls and respects closure", () => {
  assert.match(source, /id="settings-close"/);
  assert.match(source, /id="settings-cancel"/);
  assert.match(source, /if \(!settingsOpen\) return;/);
  assert.match(source, /if \(settingsOpen\) await openSettings\(\);/);
});

test("Settings Apply is single-flight and visibly pending", () => {
  assert.match(source, /if \(settingsApplyPending \|\| !settingsIsDirty\(\)\) return;/);
  assert.match(source, /settingsApplyPending = true;[\s\S]*renderSettingsUpdate\(\);[\s\S]*fetch\("\/api\/settings"/);
  assert.match(source, /settingsApplyPending \? "Applying…"/);
  assert.match(source, /settingsApplied && !dirty \? "Applied" : "Apply"/);
});

test("header refresh is described as an incremental change check", () => {
  assert.match(source, /async function refreshSourceChanges\(\)/);
  assert.match(source, /aria-label="Check for source changes"/);
  assert.match(source, /response\.status === 409[\s\S]*conflict\.source_sync/);
  assert.doesNotMatch(source, /Refresh all sources/);
});

test("Settings uses General and Models tabs", () => {
  assert.match(source, /data-settings-tab="general"[^>]*>General</);
  assert.match(source, /data-settings-tab="models"[^>]*>Models</);
  assert.match(source, /settingsActiveTab === "general"/);
  assert.match(source, /\["gpt", "claude", "others"\]/);
});

test("source choices are compact wrapping rows without horizontal scrolling", () => {
  assert.match(styles, /\.settings-dialog,[\s\S]*overflow-x:\s*hidden/);
  assert.match(styles, /\.settings-source-groups\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(styles, /\.settings-source-group\s*\{[^}]*grid-template-columns:\s*92px minmax\(0, 1fr\)/s);
  assert.match(styles, /\.settings-source-list\s*\{[^}]*flex-wrap:\s*wrap/s);
});

test("experimental CODEX deduplication is an explicit setting", () => {
  assert.match(source, /id="settings-codex-deduplication"/);
  assert.match(source, /last_token_usage \+ rate_limits/);
});
