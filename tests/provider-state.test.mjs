import assert from "node:assert/strict";
import test from "node:test";

import { normalizeProvider, providerOptions } from "../src/provider-state.js";

test("provider selector order is All, Codex, Claude, OpenCode", () => {
  assert.deepEqual(providerOptions.map((provider) => provider.value), ["all", "codex", "claude", "opencode"]);
});

test("missing and invalid providers normalize to All", () => {
  assert.equal(normalizeProvider(null), "all");
  assert.equal(normalizeProvider("invalid"), "all");
  assert.equal(normalizeProvider("codex"), "codex");
});
