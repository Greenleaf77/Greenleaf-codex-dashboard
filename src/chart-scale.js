export function chartHeightPercent(tokens, maxTokens) {
  const value = Math.max(0, Number(tokens) || 0);
  const maximum = Math.max(1, Number(maxTokens) || 0);
  return (value / maximum) * 100;
}

export function activityMaxSeconds(days, dailyScale) {
  const minimum = dailyScale ? 24 * 60 * 60 : 1;
  return Math.max(minimum, ...days.map((day) => Number(day.raw_active_seconds || day.active_seconds || 0)));
}

export function activityTicks(maxSeconds) {
  return [1, 0.75, 0.5, 0.25, 0].map((ratio) => Math.round(maxSeconds * ratio));
}

export function chartBarSizing(granularity, count) {
  if (granularity === "month") {
    return { barGap: count <= 16 ? 8 : count <= 32 ? 3 : 0, barFill: 72, barMax: 88 };
  }
  if (granularity === "week") {
    return { barGap: count <= 16 ? 6 : count <= 32 ? 3 : 0, barFill: 76, barMax: 72 };
  }
  return { barGap: count <= 32 ? 2 : 0, barFill: count <= 32 ? 82 : 76, barMax: count <= 32 ? 38 : 24 };
}
