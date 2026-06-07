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
const autoReviewModel = "codex-auto-review";
const ignoreAutoReviewCookie = "ignore_codex_auto_review";

const initialState = readUrlState();
let activeRange = initialState.range;
let customStartDate = initialState.start;
let customEndDate = initialState.end;
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

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  const range = params.get("range") || "all";
  return {
    range: rangeOptions.some((option) => option.value === range) ? range : "all",
    start: params.get("start") || "",
    end: params.get("end") || ""
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
  if (rangeName === "custom") {
    normalizeCustomRange();
    params.set("start", customStartDate);
    params.set("end", customEndDate);
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

    <section>
      <h2>Daily Heatmap</h2>
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
    </section>

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
    render(data);
  } catch (error) {
    app.innerHTML = `<section class="state error"><h1>Codex Usage</h1><p>Could not load usage data.</p><code>${escapeHtml(error.message)}</code></section>`;
  }
}

if (activeRange === "custom") {
  normalizeCustomRange();
  syncUrl();
}

refresh();
