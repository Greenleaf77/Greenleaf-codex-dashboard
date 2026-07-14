import "./styles.css";

const app = document.querySelector("#app");
const tooltip = document.createElement("div");
tooltip.className = "heat-tooltip";
document.body.appendChild(tooltip);

const rangeOptions = [
  { value: "all", label: "All" },
  { value: "30d", label: "30d" },
  { value: "7d", label: "7d" },
  { value: "1d", label: "1d" },
  { value: "custom", label: "Custom" }
];
const visualizationOptions = [
  { value: "heatmap", label: "Daily heatmap" },
  { value: "tokens", label: "Tokens over time" }
];
const chartRangeOptions = [
  { value: "all", label: "All" },
  { value: "1y", label: "1y" },
  { value: "6m", label: "6m" },
  { value: "90d", label: "90d" },
  { value: "30d", label: "30d" },
  { value: "custom", label: "Custom" }
];
const chartColors = ["#4f8fc1", "#45d1c4", "#9bd72b", "#ff674f", "#168df2", "#b98cff", "#f2bf4a", "#ea6aa6"];
const iconPaths = {
  brand: '<path d="m12 3.5 7 4v9l-7 4-7-4v-9l7-4Z"/><polyline points="8.2 12 10.7 14.5 15.8 9.4"/>',
  sessions: '<circle cx="12" cy="8" r="3.2"/><path d="M5 20c.6-3.2 3.2-5 7-5s6.4 1.8 7 5"/>',
  input: '<path d="M12 3v11"/><polyline points="8 10 12 14 16 10"/><path d="M5 17v3h14v-3"/>',
  output: '<path d="M12 21V10"/><polyline points="8 14 12 10 16 14"/><path d="M5 7V4h14v3"/>',
  calculator: '<rect x="5" y="3" width="14" height="18" rx="2"/><line x1="8" y1="7" x2="16" y2="7"/><circle cx="9" cy="11" r=".7"/><circle cx="15" cy="11" r=".7"/><circle cx="9" cy="16" r=".7"/><circle cx="15" cy="16" r=".7"/>',
  cache: '<path d="M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3 3-7 3-7-1.3-7-3Z"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
  layers: '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="m4 12 8 4 8-4"/><path d="m4 17 8 4 8-4"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><line x1="4" y1="10" x2="20" y2="10"/><line x1="8" y1="14" x2="8" y2="14"/><line x1="12" y1="14" x2="12" y2="14"/><line x1="16" y1="14" x2="16" y2="14"/>',
  coin: '<circle cx="12" cy="12" r="8"/><path d="M12 7v10"/><path d="M15 9.5c-.7-.7-1.6-1-2.8-1-1.6 0-2.7.8-2.7 2s1.1 1.8 2.7 2.2c1.7.4 2.7 1.1 2.7 2.3s-1.1 2-2.8 2c-1.2 0-2.3-.4-3-1.1"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/>',
  flame: '<path d="M12.5 3.5c.8 3.3-1.7 4.8-3.1 6.8-1.1 1.5-1.4 3.1-.6 4.6.2-1.8 1.2-3 2.5-3.9-.2 2.9 2.8 3.3 2.1 6.1 1.7-.9 3-2.6 3-4.6 0-2.5-1.7-4.8-3.9-9Z"/><path d="M8.8 20.2c-2.4-.8-4-2.7-4-5 0-2.1 1.1-3.8 2.5-5.2"/>',
  trophy: '<path d="M8 4h8v4.5a4 4 0 0 1-8 0V4Z"/><path d="M8 6H4v1a4 4 0 0 0 4 4"/><path d="M16 6h4v1a4 4 0 0 1-4 4"/><path d="M12 12.5V17"/><path d="M8 21h8"/><path d="M9 17h6v4H9z"/>',
  chart: '<line x1="4" y1="20" x2="20" y2="20"/><line x1="6" y1="20" x2="6" y2="12"/><line x1="11" y1="20" x2="11" y2="7"/><line x1="16" y1="20" x2="16" y2="4"/><polyline points="4 8 9 5 13 7 20 3"/>',
  database: '<rect x="4" y="4" width="16" height="16" rx="2"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><circle cx="8" cy="6.5" r=".8"/><circle cx="8" cy="12" r=".8"/><circle cx="8" cy="18" r=".8"/><line x1="11" y1="6.5" x2="17" y2="6.5"/><line x1="11" y1="12" x2="17" y2="12"/><line x1="11" y1="18" x2="17" y2="18"/>',
  usage: '<polyline points="3 13 7 13 9.5 6 14 18 16.5 11 21 11"/>',
  models: '<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/><line x1="10" y1="7" x2="14" y2="7"/><line x1="7" y1="10" x2="7" y2="14"/><line x1="17" y1="10" x2="17" y2="14"/>'
};
const autoReviewModel = "codex-auto-review";
const ignoreAutoReviewCookie = "ignore_codex_auto_review";

const initialState = readUrlState();
let activeRange = initialState.range;
let customStartDate = initialState.start;
let customEndDate = initialState.end;
let activeVisualization = initialState.visualization;
let chartRange = initialState.chartRange;
let chartStartDate = initialState.chartStart;
let chartEndDate = initialState.chartEnd;
let ignoreAutoReview = readIgnoreAutoReviewCookie();
let activeTableView = "usage";
let currentData = null;
let diagnosticsController = null;
let diagnosticsRequestKey = null;
let diagnosticsTimer = null;
let usageLoadTimer = null;
let usageController = null;
const diagnosticsCache = new Map();
const diagnosticsErrors = new Map();
const expandedModels = new Set();

const numberFormatter = new Intl.NumberFormat("en-US");
const moneyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "short" });

function compact(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return numberFormatter.format(number);
}

function full(value) {
  return numberFormatter.format(Number(value || 0));
}

function money(value) {
  return moneyFormatter.format(Number(value || 0));
}

function localDayKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayKey() {
  return localDayKey(new Date());
}

function isIsoDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value || "") && !Number.isNaN(new Date(`${value}T00:00:00`).getTime());
}

function parseDay(value) {
  if (!isIsoDate(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function normalizeCustomRange() {
  if (!isIsoDate(customStartDate)) customStartDate = todayKey();
  if (!isIsoDate(customEndDate)) customEndDate = customStartDate;
  if (customStartDate > customEndDate) {
    [customStartDate, customEndDate] = [customEndDate, customStartDate];
  }
}

function normalizeChartCustomRange() {
  if (!isIsoDate(chartStartDate)) chartStartDate = todayKey();
  if (!isIsoDate(chartEndDate)) chartEndDate = chartStartDate;
  if (chartStartDate > chartEndDate) {
    [chartStartDate, chartEndDate] = [chartEndDate, chartStartDate];
  }
}

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  const range = params.get("range") || "all";
  const visualization = params.get("visualization") || "heatmap";
  const selectedChartRange = params.get("chart_range") || "30d";
  return {
    range: rangeOptions.some((option) => option.value === range) ? range : "all",
    start: params.get("start") || "",
    end: params.get("end") || "",
    visualization: visualizationOptions.some((option) => option.value === visualization) ? visualization : "heatmap",
    chartRange: chartRangeOptions.some((option) => option.value === selectedChartRange) ? selectedChartRange : "30d",
    chartStart: params.get("chart_start") || "",
    chartEnd: params.get("chart_end") || ""
  };
}

function readCookie(name) {
  const encodedName = `${encodeURIComponent(name)}=`;
  const parts = document.cookie.split(";").map((part) => part.trim());
  const match = parts.find((part) => part.startsWith(encodedName));
  if (!match) return null;
  return decodeURIComponent(match.slice(encodedName.length));
}

function writeCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function readIgnoreAutoReviewCookie() {
  const stored = readCookie(ignoreAutoReviewCookie);
  if (stored === null) {
    writeCookie(ignoreAutoReviewCookie, "1");
    return true;
  }
  return stored === "1";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildQuery(rangeName, includeDiagnostics = false) {
  const params = new URLSearchParams();
  params.set("range", rangeName);
  params.set("ignore_auto_review", ignoreAutoReview ? "1" : "0");
  params.set("visualization", activeVisualization);
  params.set("chart_range", chartRange);
  if (rangeName === "custom") {
    normalizeCustomRange();
    params.set("start", customStartDate);
    params.set("end", customEndDate);
  }
  if (chartRange === "custom") {
    normalizeChartCustomRange();
    params.set("chart_start", chartStartDate);
    params.set("chart_end", chartEndDate);
  }
  if (includeDiagnostics) params.set("include_diagnostics", "1");
  return params.toString();
}

function syncUrl() {
  history.replaceState(null, "", `/?${buildQuery(activeRange)}`);
}

function describeRange(data) {
  if (data.range === "custom" && data.range_start && data.range_end) {
    return `${data.range_start} - ${data.range_end}`;
  }
  if (data.range === "1d" && data.range_start) {
    return data.range_start;
  }
  if (data.range === "7d") return "Last 7 days";
  if (data.range === "30d") return "Last 30 days";
  return "All time";
}

function describeChartRange(chart) {
  if (chart.range === "custom" && chart.range_start && chart.range_end) {
    return `${chart.range_start} - ${chart.range_end}`;
  }
  if (chart.range === "1y") return "Last 1 year";
  if (chart.range === "6m") return "Last 6 months";
  if (chart.range === "90d") return "Last 90 days";
  if (chart.range === "30d") return "Last 30 days";
  return "All time";
}

function dayLabel(day, fallbackDay, rangeName) {
  if (day) return day;
  const date = parseDay(fallbackDay);
  if (!date) return fallbackDay;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function modelColor(model, models) {
  const index = Math.max(0, models.findIndex((row) => row.model === model));
  return chartColors[index % chartColors.length];
}

function heatmapCells(daily, rangeName, rangeStart, rangeEnd) {
  const byDay = new Map(daily.map((row) => [row.day, row]));
  const today = new Date();
  const maxTokens = Math.max(0, ...daily.map((row) => row.total_tokens || 0));
  let first = daily.length ? parseDay(daily[0].day) : new Date(today.getFullYear(), today.getMonth(), today.getDate());
  let last = new Date(Math.max(today.getTime(), daily.length ? parseDay(daily.at(-1).day)?.getTime() || today.getTime() : today.getTime()));

  if (rangeName !== "all") {
    first = parseDay(rangeStart) || first;
    last = parseDay(rangeEnd) || first;
  }

  const day = first.getDay() || 7;
  first.setDate(first.getDate() - day + 1);

  const cells = [];
  for (const cursor = new Date(first); cursor <= last; cursor.setDate(cursor.getDate() + 1)) {
    const key = localDayKey(cursor);
    const row = byDay.get(key) || { sessions: 0, total_tokens: 0 };
    const tokens = row.total_tokens || 0;
    let level = 0;
    if (tokens && maxTokens) {
      if (tokens < maxTokens * 0.2) level = 1;
      else if (tokens < maxTokens * 0.45) level = 2;
      else if (tokens < maxTokens * 0.7) level = 3;
      else level = 4;
    }
    cells.push({ day: key, sessions: row.sessions || 0, tokens, level });
  }
  return cells;
}

function renderVisualizationPanel(data, heat, months, heatColumns) {
  return `
    <section>
      <div class="viz-header">
        <div>
          <div class="section-title">
            <span class="section-icon tone-cyan">${icon("usage")}</span>
            <div>
              <h2>${activeVisualization === "tokens" ? "Tokens over time" : "Daily Heatmap"}</h2>
              <div class="viz-note">${activeVisualization === "tokens" ? `Showing ${escapeHtml(describeChartRange(data.chart))}` : "Usage intensity by day"}</div>
            </div>
          </div>
        </div>
        <div class="viz-controls">
          <nav class="segments viz-tabs" aria-label="Visualization">
            ${visualizationOptions.map((option) => `<button class="seg ${activeVisualization === option.value ? "active" : ""}" data-visualization="${option.value}">${option.label}</button>`).join("")}
          </nav>
          ${activeVisualization === "tokens" ? renderChartRangeControls(data.chart) : ""}
        </div>
      </div>
      ${activeVisualization === "tokens" ? renderTokensOverTime(data.chart) : renderHeatmap(heat, months, heatColumns)}
    </section>
  `;
}

function renderHeatmap(heat, months, heatColumns) {
  return `
    <div class="heat-wrap">
      <div class="heatmap-shell">
        <div class="heatmap" style="grid-template-columns: repeat(${heatColumns}, 16px)">
          ${heat.map((cell) => `<div class="heat-cell level-${cell.level}" aria-label="${cell.day}: ${full(cell.tokens)} total tokens" data-tooltip-date="${cell.day}" data-tooltip-tokens="${full(cell.tokens)} total tokens"></div>`).join("")}
        </div>
        <div class="month-labels" style="grid-template-columns: repeat(${heatColumns}, 16px)">
          ${months.map((month) => `<span style="grid-column: ${month.column}">${escapeHtml(month.label)}</span>`).join("")}
        </div>
      </div>
    </div>
  `;
}

function renderChartRangeControls(chart) {
  return `
    <div class="chart-filter">
      <nav class="segments" aria-label="Chart range">
        ${chartRangeOptions.map((option) => `<button class="seg ${chart.range === option.value ? "active" : ""}" data-chart-range="${option.value}">${option.label}</button>`).join("")}
      </nav>
      ${chart.range === "custom" ? `
        <form class="custom-range chart-custom-range" id="chart-range-form">
          <label>
            <span>From</span>
            <input id="chart-start" type="date" value="${escapeHtml(chart.range_start || chartStartDate)}">
          </label>
          <label>
            <span>To</span>
            <input id="chart-end" type="date" value="${escapeHtml(chart.range_end || chartEndDate)}">
          </label>
          <button class="custom-apply" type="submit">Apply</button>
        </form>
      ` : ""}
    </div>
  `;
}

function renderTokensOverTime(chart) {
  const days = chart.days || [];
  const models = chart.models || [];
  const maxTokens = Math.max(1, ...days.map((day) => day.total_tokens || 0));
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((ratio) => Math.round(maxTokens * ratio));
  const labelEvery = Math.max(1, Math.ceil(days.length / 10));
  const { barWidth, barGap, barFill, barMax } = chartBarSizing(chart.granularity, days.length);

  if (!days.length) {
    return '<div class="chart-empty">No usage in this chart range.</div>';
  }

  return `
    <div class="chart-shell">
      <div class="chart-y-axis">
        ${ticks.map((tick) => `<span>${compact(tick)}</span>`).join("")}
      </div>
      <div class="chart-scroll">
        <div class="bar-chart" style="--bar-count: ${days.length}; --bar-width: ${barWidth}px; --bar-gap: ${barGap}px; --bar-fill: ${barFill}%; --bar-max: ${barMax}px">
          <div class="chart-grid">
            ${ticks.map(() => '<span></span>').join("")}
          </div>
          <div class="chart-v-grid">
            ${days.map(() => "<span></span>").join("")}
          </div>
          <div class="chart-bars">
            ${days.map((day, index) => renderChartBar(day, models, maxTokens, index, labelEvery, days.length)).join("")}
          </div>
        </div>
      </div>
    </div>
    ${renderChartLegend(models)}
  `;
}

function chartBarSizing(granularity, count) {
  if (granularity === "month") {
    return { barWidth: count <= 14 ? 96 : 64, barGap: 10, barFill: 72, barMax: 88 };
  }
  if (granularity === "week") {
    return { barWidth: count <= 16 ? 82 : 52, barGap: 8, barFill: 76, barMax: 72 };
  }
  if (count <= 32) {
    return { barWidth: 44, barGap: 6, barFill: 82, barMax: 38 };
  }
  return { barWidth: 28, barGap: 4, barFill: 76, barMax: 24 };
}

function renderChartBar(day, models, maxTokens, index, labelEvery, dayCount) {
  const tokens = Number(day.total_tokens || 0);
  const height = tokens ? Math.max(2, (tokens / maxTokens) * 100) : 0;
  const label = index % labelEvery === 0 || index === dayCount - 1 ? dayLabel(day.label, day.day, chartRange) : "";
  const title = day.bucket_start && day.bucket_end && day.bucket_start !== day.bucket_end ? `${day.bucket_start} - ${day.bucket_end}` : day.day;
  return `
    <div class="bar-slot">
      <div class="stacked-bar ${tokens ? "" : "empty"}" style="height: ${height}%" data-tooltip-title="${escapeHtml(title)}" data-tooltip-body="${full(day.total_tokens)} total tokens">
        ${(day.models || []).map((item) => {
          const segmentHeight = day.total_tokens ? (item.total_tokens / day.total_tokens) * 100 : 0;
          return `<div class="bar-segment" style="height: ${segmentHeight}%; background: ${modelColor(item.model, models)}" data-tooltip-title="${escapeHtml(item.model)}" data-tooltip-body="${escapeHtml(title)}<br>${full(item.total_tokens)} tokens"></div>`;
        }).join("")}
      </div>
      <div class="bar-label">${escapeHtml(label)}</div>
    </div>
  `;
}

function renderChartLegend(models) {
  if (!models.length) return "";
  return `
    <div class="chart-legend">
      ${models.map((row) => `
        <span class="legend-item">
          <span class="legend-swatch" style="background: ${modelColor(row.model, models)}"></span>
          <span>${escapeHtml(row.model)}</span>
        </span>
      `).join("")}
    </div>
  `;
}

function monthLabels(cells) {
  const labels = [];
  let previousMonth = "";
  cells.forEach((cell, index) => {
    const date = new Date(`${cell.day}T00:00:00`);
    const monthKey = `${date.getFullYear()}-${date.getMonth()}`;
    if (monthKey === previousMonth) return;
    previousMonth = monthKey;
    labels.push({
      label: monthFormatter.format(date).replace(".", ""),
      column: Math.floor(index / 7) + 1
    });
  });
  return labels;
}

async function load(rangeName) {
  if (usageController) usageController.abort();
  if (usageLoadTimer) window.clearInterval(usageLoadTimer);
  usageController = new AbortController();
  const controller = usageController;
  const startedAt = Date.now();
  const renderLoading = () => {
    const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1000);
    const elapsed = elapsedSeconds >= 2 ? `<span>${full(elapsedSeconds)}s elapsed</span>` : "";
    app.innerHTML = `<section class="state usage-loading" aria-live="polite"><span class="diagnostics-spinner" aria-hidden="true"></span><strong>Loading usage data…</strong>${elapsed}</section>`;
  };
  renderLoading();
  usageLoadTimer = window.setInterval(renderLoading, 1000);
  try {
    const response = await fetch(`/data.json?${buildQuery(rangeName)}`, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`Usage API returned HTTP ${response.status}`);
    return response.json();
  } finally {
    if (usageController === controller) {
      if (usageLoadTimer) window.clearInterval(usageLoadTimer);
      usageLoadTimer = null;
      usageController = null;
    }
  }
}

function renderModelDetails(row) {
  if (!row.daily?.length) {
    return '<div class="detail-empty">No daily usage for this model in the selected range.</div>';
  }
  return `
    <div class="detail-card">
      <div class="detail-meta">Used on ${full(row.active_days)} day(s) in this range.</div>
      <div class="table-scroll">
        <table class="detail-table">
          <thead><tr><th>Date</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total w/o cached</th><th class="num">Cached</th><th class="num">Total</th><th class="num">Cost</th><th class="num">Sessions</th></tr></thead>
          <tbody>
            ${row.daily.map((item) => `<tr><td>${escapeHtml(item.day)}</td><td class="num">${full(item.input_tokens)}</td><td class="num">${full(item.output_tokens)}</td><td class="num">${full(item.total_tokens)}</td><td class="num">${full(item.cached_input_tokens)}</td><td class="num">${full(item.total_with_cached_tokens)}</td><td class="num">${money(item.cost_usd)}</td><td class="num">${full(item.sessions)}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function diagnosticsKey(data) {
  return [data.range, data.range_start || "", data.range_end || "", data.ignore_auto_review ? "1" : "0"].join("|");
}

function renderUsageTables(data) {
  const totals = data.totals;
  const daily = [...data.daily].reverse();
  return `
    <div class="tables">
      <section>
        <h2 class="section-title"><span class="section-icon tone-lime">${icon("usage")}</span><span>Daily Usage</span></h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Date</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total w/o cached</th><th class="num">Cached</th><th class="num">Total</th><th class="num">Cost</th><th class="num">Sessions</th></tr></thead>
            <tbody>
              ${daily.map((row) => `<tr><td>${escapeHtml(row.day)}</td><td class="num">${full(row.input_tokens)}</td><td class="num">${full(row.output_tokens)}</td><td class="num">${full(row.total_tokens)}</td><td class="num">${full(row.cached_input_tokens)}</td><td class="num">${full(row.total_with_cached_tokens)}</td><td class="num">${money(row.cost_usd)}</td><td class="num">${full(row.sessions)}</td></tr>`).join("") || '<tr><td colspan="8" class="empty">No usage in this range.</td></tr>'}
            </tbody>
            <tfoot><tr><td>Total</td><td class="num">${full(totals.input_tokens)}</td><td class="num">${full(totals.output_tokens)}</td><td class="num">${full(totals.total_tokens)}</td><td class="num">${full(totals.cached_input_tokens)}</td><td class="num">${full(totals.total_with_cached_tokens)}</td><td class="num">${money(totals.cost_usd)}</td><td class="num">${full(totals.sessions)}</td></tr></tfoot>
          </table>
        </div>
      </section>

      <section>
        <h2 class="section-title"><span class="section-icon tone-violet">${icon("models")}</span><span>Models</span></h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Model</th><th class="num">Days</th><th class="num">Sessions</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total w/o cached</th><th class="num">Cached</th><th class="num">Total</th><th class="num">Cost</th><th class="num">Share</th></tr></thead>
            <tbody>
              ${data.models.map((row) => {
                const expanded = expandedModels.has(row.model);
                return `
                  <tr class="model-row ${expanded ? "expanded" : ""}">
                    <td>
                      <button class="model-toggle" type="button" data-model="${escapeHtml(row.model)}" aria-expanded="${expanded}">
                        <span class="model-chevron">${expanded ? "▾" : "▸"}</span>
                        <span>${escapeHtml(row.model)}</span>
                      </button>
                    </td>
                    <td class="num">${full(row.active_days)}</td>
                    <td class="num">${full(row.sessions)}</td>
                    <td class="num">${full(row.input_tokens)}</td>
                    <td class="num">${full(row.output_tokens)}</td>
                    <td class="num">${full(row.total_tokens)}</td>
                    <td class="num">${full(row.cached_input_tokens)}</td>
                    <td class="num">${full(row.total_with_cached_tokens)}</td>
                    <td class="num">${money(row.cost_usd)}</td>
                    <td class="num">${((row.total_tokens / Math.max(totals.total_tokens, 1)) * 100).toFixed(1)}%</td>
                  </tr>
                  ${expanded ? `<tr class="model-detail-row"><td colspan="10">${renderModelDetails(row)}</td></tr>` : ""}
                `;
              }).join("") || '<tr><td colspan="10" class="empty">No models in this range.</td></tr>'}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `;
}

function renderDiagnostics(diagnostics) {
  const summary = diagnostics.summary;
  return `
    <section class="diagnostics-panel">
      <div class="diagnostics-heading">
        <div>
          <h2 class="section-title"><span class="section-icon tone-cyan">${icon("usage")}</span><span>Telemetry Diagnostics</span></h2>
          <p>Local replay analysis, not server billing. Deduplicated usage can be closer to upstream usage but is not proof that a request was accepted.</p>
        </div>
        <div class="diagnostics-source">${full(summary.exact_usage_events)} exact · ${full(summary.fallback_usage_events)} cumulative fallback</div>
      </div>
      <div class="diagnostics-summary">
        <div><span>Raw token events</span><strong>${full(summary.raw_token_events)}</strong></div>
        <div><span>Deduplicated updates</span><strong>${full(summary.deduplicated_usage_updates)}</strong></div>
        <div><span>Replayed events</span><strong>${full(summary.replayed_events)} <small>${(summary.replay_rate * 100).toFixed(1)}%</small></strong></div>
        <div><span>Estimated local overcount</span><strong>${compact(summary.estimated_local_overcount_tokens)}</strong></div>
      </div>
      <div class="diagnostics-integrity">
        Baselines ${full(summary.baseline_events)} · Resets ${full(summary.counter_resets)} · Unverifiable ${full(summary.unverifiable_events)}
      </div>
      <div class="table-scroll">
        <table class="diagnostics-table">
          <thead><tr><th>Hour</th><th>Model</th><th class="num">Raw events</th><th class="num">Updates</th><th class="num">Replayed</th><th class="num">Replay rate</th><th class="num">Reported total</th><th class="num">Deduplicated total</th><th class="num">Est. overcount</th></tr></thead>
          <tbody>
            ${diagnostics.rows.map((row) => `<tr><td>${escapeHtml(row.hour)}</td><td>${escapeHtml(row.model)}</td><td class="num">${full(row.raw_token_events)}</td><td class="num">${full(row.deduplicated_usage_updates)}</td><td class="num">${full(row.replayed_events)}</td><td class="num">${(row.replay_rate * 100).toFixed(1)}%</td><td class="num">${full(row.reported_tokens)}</td><td class="num">${full(row.deduplicated_tokens)}</td><td class="num diagnostic-overcount">${full(row.estimated_local_overcount_tokens)}</td></tr>`).join("") || '<tr><td colspan="9" class="empty">No token telemetry in this range.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderDiagnosticsLoading(elapsedSeconds = 0) {
  const elapsed = elapsedSeconds >= 2 ? `<span>${full(elapsedSeconds)}s elapsed</span>` : "";
  return `<section class="diagnostics-state" aria-live="polite"><span class="diagnostics-spinner" aria-hidden="true"></span><strong>Analyzing rollout telemetry…</strong>${elapsed}</section>`;
}

function renderDiagnosticsError(message) {
  return `<section class="diagnostics-state error"><strong>Could not analyze rollout telemetry.</strong><code>${escapeHtml(message)}</code><button class="diagnostics-retry" type="button">Retry</button></section>`;
}

function renderTableView(data) {
  const key = diagnosticsKey(data);
  let workspace = renderUsageTables(data);
  if (activeTableView === "diagnostics") {
    if (diagnosticsCache.has(key)) workspace = renderDiagnostics(diagnosticsCache.get(key));
    else if (diagnosticsErrors.has(key)) workspace = renderDiagnosticsError(diagnosticsErrors.get(key));
    else workspace = renderDiagnosticsLoading();
  }
  return `
    <div class="table-view-toolbar">
      <nav class="segments" aria-label="Table view">
        <button class="seg ${activeTableView === "usage" ? "active" : ""}" type="button" data-table-view="usage" aria-pressed="${activeTableView === "usage"}">Usage</button>
        <button class="seg ${activeTableView === "diagnostics" ? "active" : ""}" type="button" data-table-view="diagnostics" aria-pressed="${activeTableView === "diagnostics"}">Diagnostics</button>
      </nav>
    </div>
    <div id="table-workspace">${workspace}</div>
  `;
}

function clearDiagnosticsTimer() {
  if (diagnosticsTimer) window.clearInterval(diagnosticsTimer);
  diagnosticsTimer = null;
}

function cancelDiagnosticsRequest() {
  clearDiagnosticsTimer();
  if (diagnosticsController) diagnosticsController.abort();
  diagnosticsController = null;
  diagnosticsRequestKey = null;
}

function updateTableView(data) {
  const container = document.querySelector("#table-view-container");
  if (!container) return;
  container.innerHTML = renderTableView(data);
  bindTableView(data);
}

function bindTableView(data) {
  document.querySelectorAll("[data-table-view]").forEach((button) => {
    button.addEventListener("click", () => {
      activeTableView = button.dataset.tableView;
      updateTableView(data);
      if (activeTableView === "diagnostics") ensureDiagnostics(data);
    });
  });

  document.querySelectorAll(".model-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const model = button.dataset.model;
      if (!model) return;
      if (expandedModels.has(model)) expandedModels.delete(model);
      else expandedModels.add(model);
      updateTableView(data);
    });
  });

  const retry = document.querySelector(".diagnostics-retry");
  if (retry) {
    retry.addEventListener("click", () => {
      diagnosticsErrors.delete(diagnosticsKey(data));
      updateTableView(data);
      ensureDiagnostics(data, true);
    });
  }
}

async function ensureDiagnostics(data, force = false) {
  const key = diagnosticsKey(data);
  if (!force && diagnosticsCache.has(key)) {
    if (activeTableView === "diagnostics") updateTableView(data);
    return;
  }
  if (!force && diagnosticsController && diagnosticsRequestKey === key) return;

  cancelDiagnosticsRequest();
  diagnosticsErrors.delete(key);
  diagnosticsController = new AbortController();
  diagnosticsRequestKey = key;
  const controller = diagnosticsController;
  const startedAt = Date.now();
  if (activeTableView === "diagnostics") updateTableView(data);
  diagnosticsTimer = window.setInterval(() => {
    if (activeTableView !== "diagnostics" || diagnosticsKey(currentData || data) !== key) return;
    const workspace = document.querySelector("#table-workspace");
    if (workspace) workspace.innerHTML = renderDiagnosticsLoading(Math.floor((Date.now() - startedAt) / 1000));
  }, 1000);

  try {
    const response = await fetch(`/data.json?${buildQuery(activeRange, true)}`, {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`Diagnostics API returned HTTP ${response.status}`);
    const payload = await response.json();
    if (!payload.diagnostics) throw new Error("Diagnostics payload is missing");
    diagnosticsCache.set(key, payload.diagnostics);
    if (activeTableView === "diagnostics" && diagnosticsKey(currentData || data) === key) updateTableView(data);
  } catch (error) {
    if (error.name === "AbortError") return;
    diagnosticsErrors.set(key, error.message);
    if (activeTableView === "diagnostics" && diagnosticsKey(currentData || data) === key) updateTableView(data);
  } finally {
    if (diagnosticsController === controller) {
      clearDiagnosticsTimer();
      diagnosticsController = null;
      diagnosticsRequestKey = null;
    }
  }
}

function render(data) {
  currentData = data;
  const totals = data.totals;
  const heat = heatmapCells(data.daily, data.range, data.range_start, data.range_end);
  const months = monthLabels(heat);
  const heatColumns = Math.max(1, Math.ceil(heat.length / 7));

  app.innerHTML = `
    <header>
      <div class="brand-block">
        <span class="brand-mark">${icon("brand")}</span>
        <div>
          <h1>Codex Usage</h1>
          <div class="subtle">Generated ${escapeHtml(data.generated_at)} from local Codex logs</div>
          <div class="segment-note">Showing ${escapeHtml(describeRange(data))}</div>
        </div>
      </div>
      <div class="header-tools">
        <label class="toggle-option">
          <input id="ignore-auto-review" type="checkbox" ${data.ignore_auto_review ? "checked" : ""}>
          <span>Ignore "${escapeHtml(autoReviewModel)}" model</span>
        </label>
        <nav class="segments" aria-label="Range">
          ${rangeOptions.map((range) => `<button class="seg ${data.range === range.value ? "active" : ""}" data-range="${range.value}">${range.label}</button>`).join("")}
        </nav>
        ${data.range === "custom" ? `
          <form class="custom-range" id="custom-range-form">
            <label>
              <span>From</span>
              <input id="custom-start" type="date" value="${escapeHtml(data.range_start || customStartDate)}">
            </label>
            <label>
              <span>To</span>
              <input id="custom-end" type="date" value="${escapeHtml(data.range_end || customEndDate)}">
            </label>
            <button class="custom-apply" type="submit">Apply</button>
          </form>
        ` : ""}
      </div>
    </header>

    <div class="cards">
      ${card("Sessions", full(totals.sessions), "sessions", "violet")}
      ${card("Input tokens", compact(totals.input_tokens), "input", "blue")}
      ${card("Output tokens", compact(totals.output_tokens), "output", "cyan")}
      ${card("Total w/o cached", compact(totals.total_tokens), "calculator", "slate")}
      ${card("Cached input", compact(totals.cached_input_tokens), "cache", "violet")}
      ${card("Total tokens", compact(totals.total_with_cached_tokens), "layers", "cyan")}
      ${card("Active days", full(totals.active_days), "calendar", "slate")}
      ${card("API estimate", `${money(totals.cost_usd)}<span class="metric-note">${escapeHtml(data.pricing?.source || "pricing unavailable")}</span>`, "coin", "lime")}
      ${card("Favorite model", escapeHtml(data.favorite_model), "star", "amber")}
      ${card("Current streak", `${full(data.current_streak)}d`, "flame", "coral")}
      ${card("Longest streak", `${full(data.longest_streak)}d`, "trophy", "amber")}
      ${card("Peak day", `${escapeHtml(data.peak_day)}${data.peak_day_tokens ? `<span class="metric-note">${compact(data.peak_day_tokens)}</span>` : ""}`, "chart", "blue")}
      ${card("Data source", "SQLite + JSONL", "database", "violet")}
    </div>

    ${renderVisualizationPanel(data, heat, months, heatColumns)}
    <div id="table-view-container">${renderTableView(data)}</div>
  `;

  bindTableView(data);
  if (activeTableView === "diagnostics") ensureDiagnostics(data);

  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      activeRange = button.dataset.range;
      if (activeRange === "custom") {
        normalizeCustomRange();
      }
      syncUrl();
      refresh();
    });
  });

  document.querySelectorAll("[data-visualization]").forEach((button) => {
    button.addEventListener("click", () => {
      activeVisualization = button.dataset.visualization;
      syncUrl();
      render(data);
    });
  });

  document.querySelectorAll("[data-chart-range]").forEach((button) => {
    button.addEventListener("click", () => {
      chartRange = button.dataset.chartRange;
      if (chartRange === "custom") {
        normalizeChartCustomRange();
      }
      activeVisualization = "tokens";
      syncUrl();
      refresh();
    });
  });

  const chartRangeForm = document.querySelector("#chart-range-form");
  if (chartRangeForm) {
    chartRangeForm.addEventListener("submit", (event) => {
      event.preventDefault();
      chartStartDate = document.querySelector("#chart-start")?.value || chartStartDate;
      chartEndDate = document.querySelector("#chart-end")?.value || chartEndDate;
      normalizeChartCustomRange();
      chartRange = "custom";
      activeVisualization = "tokens";
      syncUrl();
      refresh();
    });
  }

  const customRangeForm = document.querySelector("#custom-range-form");
  if (customRangeForm) {
    customRangeForm.addEventListener("submit", (event) => {
      event.preventDefault();
      customStartDate = document.querySelector("#custom-start")?.value || customStartDate;
      customEndDate = document.querySelector("#custom-end")?.value || customEndDate;
      normalizeCustomRange();
      activeRange = "custom";
      syncUrl();
      refresh();
    });
  }

  const ignoreAutoReviewInput = document.querySelector("#ignore-auto-review");
  if (ignoreAutoReviewInput) {
    ignoreAutoReviewInput.addEventListener("change", () => {
      ignoreAutoReview = ignoreAutoReviewInput.checked;
      writeCookie(ignoreAutoReviewCookie, ignoreAutoReview ? "1" : "0");
      refresh();
    });
  }

  document.querySelectorAll(".heat-cell").forEach((cell) => {
    cell.addEventListener("mouseenter", showHeatTooltip);
    cell.addEventListener("mousemove", positionHeatTooltip);
    cell.addEventListener("mouseleave", hideHeatTooltip);
  });

  document.querySelectorAll(".stacked-bar, .bar-segment").forEach((item) => {
    item.addEventListener("mouseenter", showChartTooltip);
    item.addEventListener("mousemove", positionHeatTooltip);
    item.addEventListener("mouseleave", hideHeatTooltip);
  });
}

function icon(name, className = "") {
  const paths = iconPaths[name] || iconPaths.layers;
  return `<svg class="icon ${className}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}

function card(label, value, iconName, tone) {
  return `<div class="card metric-${tone}"><span class="metric-icon">${icon(iconName)}</span><div class="metric-copy"><div class="label">${label}</div><div class="value">${value}</div></div></div>`;
}

function showHeatTooltip(event) {
  const target = event.currentTarget;
  tooltip.innerHTML = `${escapeHtml(target.dataset.tooltipDate)}<br><strong>${escapeHtml(target.dataset.tooltipTokens)}</strong>`;
  tooltip.classList.add("visible");
  positionHeatTooltip(event);
}

function showChartTooltip(event) {
  const target = event.currentTarget;
  tooltip.innerHTML = `${escapeHtml(target.dataset.tooltipTitle)}<br><strong>${target.dataset.tooltipBody}</strong>`;
  tooltip.classList.add("visible");
  positionHeatTooltip(event);
}

function positionHeatTooltip(event) {
  if (!tooltip.classList.contains("visible")) return;
  const gap = 12;
  const margin = 8;
  const rect = tooltip.getBoundingClientRect();
  let left = event.clientX - rect.width / 2;
  let top = event.clientY - rect.height - gap;

  left = Math.max(margin, Math.min(left, window.innerWidth - rect.width - margin));
  if (top < margin) {
    top = event.clientY + gap;
  }
  top = Math.max(margin, Math.min(top, window.innerHeight - rect.height - margin));

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideHeatTooltip() {
  tooltip.classList.remove("visible");
}

async function refresh() {
  cancelDiagnosticsRequest();
  try {
    const data = await load(activeRange);
    diagnosticsCache.delete(diagnosticsKey(data));
    diagnosticsErrors.delete(diagnosticsKey(data));
    ignoreAutoReview = Boolean(data.ignore_auto_review);
    if (data.range === "custom") {
      customStartDate = data.range_start || customStartDate;
      customEndDate = data.range_end || customEndDate;
    }
    chartRange = data.chart?.range || chartRange;
    if (data.chart?.range === "custom") {
      chartStartDate = data.chart.range_start || chartStartDate;
      chartEndDate = data.chart.range_end || chartEndDate;
    }
    render(data);
  } catch (error) {
    if (error.name === "AbortError") return;
    app.innerHTML = `<section class="state error"><h1>Codex Usage</h1><p>Could not load usage data.</p><code>${escapeHtml(error.message)}</code></section>`;
  }
}

if (activeRange === "custom") {
  normalizeCustomRange();
  syncUrl();
}

if (chartRange === "custom") {
  normalizeChartCustomRange();
  syncUrl();
}

refresh();
