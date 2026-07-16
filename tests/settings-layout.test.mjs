import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("Unibase operation progress wraps within the settings section", () => {
  assert.match(styles, /\.unibase-settings\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(styles, /\.operation-progress\s*\{[^}]*min-width:\s*0/s);
  assert.match(styles, /\.operation-progress progress\s*\{[^}]*max-width:\s*100%/s);
  assert.match(styles, /\.operation-progress code\s*\{[^}]*overflow-wrap:\s*anywhere/s);
});
