export const providerOptions = [
  { value: "all", label: "ALL" },
  { value: "codex", label: "CODEX" },
  { value: "claude", label: "CLAUDE" },
  { value: "opencode", label: "OPENCODE" }
];

export function normalizeProvider(value) {
  return providerOptions.some((option) => option.value === value) ? value : "all";
}
