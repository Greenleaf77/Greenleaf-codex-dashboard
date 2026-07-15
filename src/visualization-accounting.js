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

export function resolveIgnoreAutoReview(urlValue, cookieValue) {
  if (urlValue === "1" || urlValue === "0") return urlValue === "1";
  if (cookieValue === "1" || cookieValue === "0") return cookieValue === "1";
  return false;
}
