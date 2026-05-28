import "./styles.css";

const app = document.querySelector("#app");
const tooltip = document.createElement("div");
tooltip.className = "heat-tooltip";
document.body.appendChild(tooltip);

const ranges = ["all", "30d", "7d"];
let activeRange = new URLSearchParams(window.location.search).get("range") || "all";
if (!ranges.includes(activeRange)) activeRange = "all";

const numberFormatter = new Intl.NumberFormat("en-US");
const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "short" });

function compact(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return numberFormatter.format(number);
}

function full(value) {
  return numberFormatter.format(Number(value || 0));
}

function localDayKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function heatmapCells(daily, rangeName) {
  const byDay = new Map(daily.map((row) => [row.day, row]));
  const today = new Date();
  const maxTokens = Math.max(0, ...daily.map((row) => row.total_tokens || 0));
  let first = daily.length ? new Date(`${daily[0].day}T00:00:00`) : today;
  const last = new Date(Math.max(today.getTime(), daily.length ? new Date(`${daily.at(-1).day}T00:00:00`).getTime() : today.getTime()));

  if (rangeName === "7d") first = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6);
  if (rangeName === "30d") first = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29);

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
  const response = await fetch(`/data.json?range=${encodeURIComponent(rangeName)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Usage API returned HTTP ${response.status}`);
  return response.json();
}

function render(data) {
  const totals = data.totals;
  const daily = [...data.daily].reverse();
  const heat = heatmapCells(data.daily, data.range);
  const months = monthLabels(heat);
  const heatColumns = Math.max(1, Math.ceil(heat.length / 7));

  app.innerHTML = `
    <header>
      <div>
        <h1>Codex Usage</h1>
        <div class="subtle">Generated ${escapeHtml(data.generated_at)} from local Codex logs</div>
      </div>
      <nav class="segments" aria-label="Range">
        ${ranges.map((range) => `<button class="seg ${data.range === range ? "active" : ""}" data-range="${range}">${range === "all" ? "All" : range}</button>`).join("")}
      </nav>
    </header>

    <div class="cards">
      ${card("Sessions", full(totals.sessions))}
      ${card("Total tokens", compact(totals.total_tokens))}
      ${card("Input tokens", compact(totals.input_tokens))}
      ${card("Output tokens", compact(totals.output_tokens))}
      ${card("Active days", full(totals.active_days))}
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
            <thead><tr><th>Date</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total</th><th class="num">Sessions</th></tr></thead>
            <tbody>
              ${daily.map((row) => `<tr><td>${escapeHtml(row.day)}</td><td class="num">${full(row.input_tokens)}</td><td class="num">${full(row.output_tokens)}</td><td class="num">${full(row.total_tokens)}</td><td class="num">${full(row.sessions)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">No usage in this range.</td></tr>'}
            </tbody>
            <tfoot><tr><td>Total</td><td class="num">${full(totals.input_tokens)}</td><td class="num">${full(totals.output_tokens)}</td><td class="num">${full(totals.total_tokens)}</td><td class="num">${full(totals.sessions)}</td></tr></tfoot>
          </table>
        </div>
      </section>

      <section>
        <h2>Models</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Model</th><th class="num">Sessions</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total</th><th class="num">Share</th></tr></thead>
            <tbody>
              ${data.models.map((row) => `<tr><td>${escapeHtml(row.model)}</td><td class="num">${full(row.sessions)}</td><td class="num">${full(row.input_tokens)}</td><td class="num">${full(row.output_tokens)}</td><td class="num">${full(row.total_tokens)}</td><td class="num">${((row.total_tokens / Math.max(totals.total_tokens, 1)) * 100).toFixed(1)}%</td></tr>`).join("") || '<tr><td colspan="6" class="empty">No models in this range.</td></tr>'}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `;

  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      activeRange = button.dataset.range;
      history.replaceState(null, "", `/?range=${activeRange}`);
      refresh();
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
    render(data);
  } catch (error) {
    app.innerHTML = `<section class="state error"><h1>Codex Usage</h1><p>Could not load usage data.</p><code>${escapeHtml(error.message)}</code></section>`;
  }
}

refresh();
