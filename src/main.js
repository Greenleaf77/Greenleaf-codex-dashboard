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

function buildQuery(rangeName) {
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
          <h2>${activeVisualization === "tokens" ? "Tokens over time" : "Daily Heatmap"}</h2>
          <div class="viz-note">${activeVisualization === "tokens" ? `Showing ${escapeHtml(describeChartRange(data.chart))}` : "Usage intensity by day"}</div>
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
  app.innerHTML = '<section class="state">Loading usage data...</section>';
  const response = await fetch(`/data.json?${buildQuery(rangeName)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Usage API returned HTTP ${response.status}`);
  return response.json();
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

function render(data) {
  const totals = data.totals;
  const daily = [...data.daily].reverse();
  const heat = heatmapCells(data.daily, data.range, data.range_start, data.range_end);
  const months = monthLabels(heat);
  const heatColumns = Math.max(1, Math.ceil(heat.length / 7));

  app.innerHTML = `
    <header>
      <div>
        <h1>Codex Usage</h1>
        <div class="subtle">Generated ${escapeHtml(data.generated_at)} from local Codex logs</div>
        <div class="segment-note">Showing ${escapeHtml(describeRange(data))}</div>
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
      ${card("Sessions", full(totals.sessions))}
      ${card("Input tokens", compact(totals.input_tokens))}
      ${card("Output tokens", compact(totals.output_tokens))}
      ${card("Total w/o cached", compact(totals.total_tokens))}
      ${card("Cached input", compact(totals.cached_input_tokens))}
      ${card("Total tokens", compact(totals.total_with_cached_tokens))}
      ${card("Active days", full(totals.active_days))}
      ${card("API estimate", `${money(totals.cost_usd)}<span class="metric-note">${escapeHtml(data.pricing?.source || "pricing unavailable")}</span>`)}
      ${card("Favorite model", escapeHtml(data.favorite_model))}
      ${card("Current streak", `${full(data.current_streak)}d`)}
      ${card("Longest streak", `${full(data.longest_streak)}d`)}
      ${card("Peak day", `${escapeHtml(data.peak_day)}${data.peak_day_tokens ? `<span class="metric-note">${compact(data.peak_day_tokens)}</span>` : ""}`)}
      ${card("Data source", "SQLite + JSONL")}
    </div>

    ${renderVisualizationPanel(data, heat, months, heatColumns)}

    <div class="tables">
      <section>
        <h2>Daily Usage</h2>
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
        <h2>Models</h2>
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

  document.querySelectorAll(".model-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const model = button.dataset.model;
      if (!model) return;
      if (expandedModels.has(model)) expandedModels.delete(model);
      else expandedModels.add(model);
      render(data);
    });
  });

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

function card(label, value) {
  return `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`;
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
  try {
    const data = await load(activeRange);
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
