export const WITH_CACHE = "with";
export const WITHOUT_CACHE = "without";

export function resolveCacheMode(value) {
  return value === WITHOUT_CACHE ? WITHOUT_CACHE : WITH_CACHE;
}

export function metricValue(row, mode) {
  const fallback = Number(row?.total_tokens || 0);
  if (mode !== WITH_CACHE) return fallback;
  const rawInclusive = row?.total_with_cached_tokens;
  const inclusive = rawInclusive === null || rawInclusive === undefined ? Number.NaN : Number(rawInclusive);
  return Number.isFinite(inclusive) ? inclusive : fallback;
}
