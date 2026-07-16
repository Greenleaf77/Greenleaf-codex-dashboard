export function chartHeightPercent(tokens, maxTokens) {
  const value = Math.max(0, Number(tokens) || 0);
  const maximum = Math.max(1, Number(maxTokens) || 0);
  return (value / maximum) * 100;
}
