// SmartPicksGPT Ultra Dashboard JS
// Patched to support ALL known SmartPicks schema formats, including:
// 1) Ultra format: { picks, summary, meta, history }
// 2) Your current format: { top10, daily_summary, performance, history }
// 3) Legacy array-only format: [ { pick }, ... ]

let allPicks = [];
let filteredPicks = [];
let allHistory = [];
let summaryData = null;
let metaData = null;

// Pagination
const PAGE_SIZE = 15;
let currentHistoryPage = 1;

// Chart instances
let performanceChart = null;
let evChart = null;

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTabs();
  initSearch();
  initHistoryPagination();
  loadData();
});

/* ============================================================
   THE CRITICAL FIX: JSON SCHEMA AUTO-ADAPTER
   ============================================================ */

function applySchema(json) {
  // ---------------------------------------------
  // 1) ULTRA SCHEMA
  // ---------------------------------------------
  if (json.picks || json.summary || json.meta) {
    return {
      picks: json.picks ?? [],
      history: json.history ?? [],
      summary: json.summary ?? null,
      meta: json.meta ?? null
    };
  }

  // ---------------------------------------------
  // 2) YOUR CURRENT SMARTPICKS FORMAT
  // ---------------------------------------------
  if (json.top10) {
    const perf = json.performance ?? {};
    const daily = json.daily_summary ?? {};

    // Build summary object the Ultra UI expects
    const total_bets = perf.total_bets ?? daily.num_bets ?? 0;
    const wins = perf.wins ?? null;
    const win_rate =
      wins !== null && total_bets > 0 ? wins / total_bets : null;

    const roi_pct = perf.roi_pct ?? daily.roi_pct ?? null;
    const roi = roi_pct != null ? roi_pct / 100 : null;

    const net_profit =
      perf.total_profit ?? daily.profit ?? 0;

    const generated =
      daily.date ??
      perf.generated_at ??
      null;

    return {
      picks: json.top10,
      history: json.history ?? [],
      summary: {
        total_bets,
        settled_bets: (json.history ?? []).filter(
          (h) => h.result && h.result !== "PENDING"
        ).length,
        win_rate,
        roi,
        net_profit,
        generated_at: generated
      },
      meta: {
        generated_at: generated
      }
    };
  }

  // ---------------------------------------------
  // 3) LEGACY ARRAY OF PICKS ONLY
  // ---------------------------------------------
  if (Array.isArray(json)) {
    return {
      picks: json,
      history: [],
      summary: null,
      meta: null
    };
  }

  // Fallback empty
  return {
    picks: [],
    history: [],
    summary: null,
    meta: null
  };
}

/* ============================================================
   CORE LOAD
   ============================================================ */

function loadData() {
  fetch("data.json", { cache: "no-store" })
    .then((r) => r.json())
    .then((raw) => {
      const mapped = applySchema(raw);

      allPicks = mapped.picks ?? [];
      filteredPicks = [...allPicks];
      allHistory = mapped.history ?? [];
      summaryData = mapped.summary ?? null;
      metaData = mapped.meta ?? null;

      renderAll();
    })
    .catch((err) => {
      console.error("Error loading data.json:", err);
      showLoadError(err.message);
    });
}

/* ============================================================
   THE REST OF YOUR FILE…
   (tabs, theme, rendering, charts, helpers)
   ============================================================ */
/* ============================================================
   THEME TOGGLE
   ============================================================ */

function initTheme() {
  const saved = localStorage.getItem("sp_theme");
  if (saved === "dark") document.body.classList.add("dark");

  updateThemeIcon();

  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;

  toggleBtn.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem(
      "sp_theme",
      document.body.classList.contains("dark") ? "dark" : "light"
    );
    updateThemeIcon();
  });
}

function updateThemeIcon() {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;

  toggleBtn.textContent = document.body.classList.contains("dark")
    ? "☀️"
    : "🌙";
}

/* ============================================================
   TABS
   ============================================================ */

function initTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.dataset.tab;

      document.querySelectorAll(".tab-button").forEach((b) => {
        b.classList.remove("active");
      });
      btn.classList.add("active");

      document.querySelectorAll(".tab-content").forEach((tab) => {
        tab.classList.remove("active");
      });

      const target = document.getElementById(`tab-${targetTab}`);
      if (target) target.classList.add("active");
    });
  });
}

/* ============================================================
   SEARCH FILTER
   ============================================================ */

function initSearch() {
  const input = document.getElementById("picks-search");
  if (!input) return;

  input.addEventListener("input", (e) => {
    const term = e.target.value.toLowerCase();

    if (!term) {
      filteredPicks = [...allPicks];
    } else {
      filteredPicks = allPicks.filter((p) => {
        return (
          (p.team ?? "").toLowerCase().includes(term) ||
          (p.match ?? "").toLowerCase().includes(term) ||
          (p.market ?? "").toLowerCase().includes(term) ||
          (p.sport ?? "").toLowerCase().includes(term)
        );
      });
    }

    renderPicks();
    updateEvChart();
  });
}

/* ============================================================
   HISTORY PAGINATION
   ============================================================ */

function initHistoryPagination() {
  const prev = document.getElementById("history-prev");
  const next = document.getElementById("history-next");

  if (prev) {
    prev.addEventListener("click", () => {
      if (currentHistoryPage > 1) {
        currentHistoryPage--;
        renderHistory();
      }
    });
  }

  if (next) {
    next.addEventListener("click", () => {
      const totalPages = Math.ceil(allHistory.length / PAGE_SIZE);
      if (currentHistoryPage < totalPages) {
        currentHistoryPage++;
        renderHistory();
      }
    });
  }
}

/* ============================================================
   ROOT RENDER
   ============================================================ */

function renderAll() {
  renderMeta();
  renderSummary();
  renderPicks();
  renderHistory();
  setupAutoHiding();
  updateCharts();
}

/* ============================================================
   META (LAST UPDATED)
   ============================================================ */

function renderMeta() {
  const label = document.getElementById("last-updated-value");
  if (!label) return;

  const ts =
    (metaData && metaData.generated_at) ||
    (summaryData && summaryData.generated_at) ||
    "Unknown";

  label.textContent = ts;
}

/* ============================================================
   SUMMARY
   ============================================================ */

function renderSummary() {
  const elTotal = document.getElementById("summary-total-bets");
  const elWinRate = document.getElementById("summary-win-rate");
  const elROI = document.getElementById("summary-roi");
  const elBankroll = document.getElementById("summary-bankroll");
  const elCount = document.getElementById("history-count-label");

  if (!summaryData) {
    // No summary available — empty UI
    if (elTotal) elTotal.textContent = "–";
    if (elWinRate) elWinRate.textContent = "–";
    if (elROI) elROI.textContent = "–";
    if (elBankroll) elBankroll.textContent = "–";
    if (elCount) elCount.textContent = "0 settled bets";
    return;
  }

  const settled = summaryData.settled_bets ?? allHistory.length ?? 0;

  if (elTotal) elTotal.textContent = formatNumber(summaryData.total_bets);
  if (elWinRate) elWinRate.textContent = formatPercent(summaryData.win_rate);
  if (elROI) elROI.textContent = formatPercent(summaryData.roi);
  if (elBankroll) elBankroll.textContent = formatCurrency(summaryData.net_profit);
  if (elCount) elCount.textContent = `${settled} settled bets`;
}

/* ============================================================
   PICKS
   ============================================================ */

function renderPicks() {
  const container = document.getElementById("picks-container");
  const empty = document.getElementById("picks-empty");
  const count = document.getElementById("picks-count-label");

  if (!container || !empty) return;

  container.innerHTML = "";

  if (count) {
    count.textContent = `${filteredPicks.length} pick${
      filteredPicks.length === 1 ? "" : "s"
    } loaded`;
  }

  if (filteredPicks.length === 0) {
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");

  filteredPicks.forEach((p, i) => {
    const card = document.createElement("article");
    card.className = "pick-card";

    const rank = p.rank ?? i + 1;
    const ev = parseNumber(p.ev ?? p.adj_ev ?? 0);
    const evClass = getEvClass(ev);

    card.innerHTML = `
      <div class="pick-header">
        <div>
          <div class="pick-title">#${rank} – ${p.team}</div>
          <div class="pick-meta">
            ${p.match}<br />
            <span class="pick-badge">${p.market}</span>
          </div>
        </div>
      </div>
      <div class="pick-footer">
        <div><strong>Odds:</strong> ${formatOdds(p.price)}</div>
        <div class="pick-ev-pill ${evClass}">
          <span>${ev >= 0 ? "Positive EV" : "Negative EV"}</span>
          <strong>${formatEV(ev)}</strong>
        </div>
      </div>
      <div class="pick-reason">
        ${sanitize(p.explanation ?? "")}
      </div>
    `;

    container.appendChild(card);
  });
}

/* ============================================================
   HISTORY
   ============================================================ */

function renderHistory() {
  const tbody = document.getElementById("history-body");
  const empty = document.getElementById("history-empty");
  const pager = document.getElementById("history-pagination");
  const info = document.getElementById("history-page-info");

  if (!tbody || !empty || !pager || !info) return;

  tbody.innerHTML = "";

  if (!allHistory.length) {
    empty.classList.remove("hidden");
    pager.classList.add("hidden");
    return;
  }

  empty.classList.add("hidden");
  pager.classList.remove("hidden");

  // Pagination
  const totalPages = Math.ceil(allHistory.length / PAGE_SIZE);
  if (currentHistoryPage > totalPages) currentHistoryPage = totalPages;

  const start = (currentHistoryPage - 1) * PAGE_SIZE;
  const items = allHistory.slice(start, start + PAGE_SIZE);

  items.forEach((bet) => {
    const tr = document.createElement("tr");

    const pnl = parseNumber(bet.actual_profit ?? bet.profit ?? 0);
    const pnlClass = pnl > 0 ? "pnl-positive" : pnl < 0 ? "pnl-negative" : "";

    tr.innerHTML = `
      <td>${sanitize(bet.date)}</td>
      <td>${sanitize(bet.sport)}</td>
      <td>${sanitize(bet.match)}</td>
      <td>${sanitize(bet.team)}</td>
      <td>${sanitize(bet.market)}</td>
      <td>${formatOdds(bet.price)}</td>
      <td>${sanitize(bet.result)}</td>
      <td class="${pnlClass}">${formatCurrency(pnl)}</td>
    `;

    tbody.appendChild(tr);
  });

  info.textContent = `Page ${currentHistoryPage} / ${totalPages}`;
}

/* ============================================================
   AUTO-HIDING EMPTY TABS
   ============================================================ */

function setupAutoHiding() {
  // Summary tab
  const summaryBtn = document.querySelector('[data-tab="summary"]');
  const summaryTab = document.getElementById("tab-summary");

  if (summaryBtn && summaryTab) {
    if (!summaryData && !allHistory.length) {
      summaryBtn.classList.add("hidden");
      summaryTab.classList.add("hidden");
    }
  }

  // Picks tab
  const picksBtn = document.querySelector('[data-tab="picks"]');
  const picksTab = document.getElementById("tab-picks");
  if (picksBtn && picksTab && !allPicks.length) {
    picksBtn.classList.add("hidden");
    picksTab.classList.add("hidden");
  }

  // History tab
  const historyBtn = document.querySelector('[data-tab="history"]');
  const historyTab = document.getElementById("tab-history");
  if (historyBtn && historyTab && !allHistory.length) {
    historyBtn.classList.add("hidden");
    historyTab.classList.add("hidden");
  }
}
/* ============================================================
   CHARTS
   ============================================================ */

function updateCharts() {
  updatePerformanceChart();
  updateEvChart();
}

function updatePerformanceChart() {
  const canvas = document.getElementById("chart-performance");
  const emptyMsg = document.getElementById("chart-performance-empty");
  if (!canvas || !emptyMsg) return;

  if (!allHistory.length) {
    emptyMsg.classList.remove("hidden");
    if (performanceChart) {
      performanceChart.destroy();
      performanceChart = null;
    }
    return;
  }

  // Aggregate PnL by date and build cumulative curve
  const byDate = {};
  allHistory.forEach((bet) => {
    const date =
      bet.date ||
      bet.game_date ||
      (bet.resolved_time || bet.event_time || "").slice(0, 10) ||
      "Unknown";
    const pnl = parseNumber(bet.actual_profit ?? bet.profit ?? 0);
    if (!byDate[date]) byDate[date] = 0;
    byDate[date] += pnl;
  });

  const dates = Object.keys(byDate).sort();
  if (!dates.length) {
    emptyMsg.classList.remove("hidden");
    if (performanceChart) {
      performanceChart.destroy();
      performanceChart = null;
    }
    return;
  }

  let running = 0;
  const cumulative = dates.map((d) => {
    running += byDate[d];
    return running;
  });

  emptyMsg.classList.add("hidden");

  if (performanceChart) {
    performanceChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  performanceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: [
        {
          label: "Cumulative PnL",
          data: cumulative,
          borderWidth: 2,
          tension: 0.25,
          pointRadius: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8 }
        }
      }
    }
  });
}

function updateEvChart() {
  const canvas = document.getElementById("chart-ev");
  const emptyMsg = document.getElementById("chart-ev-empty");
  if (!canvas || !emptyMsg) return;

  const source = filteredPicks.length ? filteredPicks : allPicks;
  if (!source.length) {
    emptyMsg.classList.remove("hidden");
    if (evChart) {
      evChart.destroy();
      evChart = null;
    }
    return;
  }

  const evValues = source
    .map((p) => parseNumber(p.ev ?? p.adj_ev))
    .filter((v) => !Number.isNaN(v));

  if (!evValues.length) {
    emptyMsg.classList.remove("hidden");
    if (evChart) {
      evChart.destroy();
      evChart = null;
    }
    return;
  }

  emptyMsg.classList.add("hidden");

  const buckets = {
    negative: 0,
    low: 0,
    medium: 0,
    high: 0
  };

  evValues.forEach((ev) => {
    if (ev < 0) buckets.negative++;
    else if (ev < 2.5) buckets.low++;
    else if (ev < 5) buckets.medium++;
    else buckets.high++;
  });

  if (evChart) {
    evChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  evChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["EV < 0", "0 – 2.5", "2.5 – 5", "> 5"],
      datasets: [
        {
          label: "Count of picks",
          data: [
            buckets.negative,
            buckets.low,
            buckets.medium,
            buckets.high
          ],
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      }
    }
  });
}

/* ============================================================
   ERROR DISPLAY
   ============================================================ */

function showLoadError(message) {
  const picksContainer = document.getElementById("picks-container");
  const picksEmpty = document.getElementById("picks-empty");

  if (picksContainer) picksContainer.innerHTML = "";
  if (picksEmpty) {
    picksEmpty.classList.remove("hidden");
    picksEmpty.textContent = `⚠️ Could not load picks (${message}).`;
  }
}

/* ============================================================
   HELPERS
   ============================================================ */

function parseNumber(value) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const cleaned = value.replace(/[^\d.-]/g, "");
    const n = Number(cleaned);
    return Number.isNaN(n) ? 0 : n;
  }
  return 0;
}

function formatNumber(value) {
  const n = parseNumber(value);
  if (!Number.isFinite(n)) return "–";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "–";
  const n = typeof value === "number" ? value : parseNumber(value);
  if (!Number.isFinite(n)) return "–";
  return (n * 100).toFixed(1) + "%";
}

function formatCurrency(value) {
  const n = parseNumber(value);
  if (!Number.isFinite(n)) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return (
    sign +
    "$" +
    abs.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
  );
}

function formatOdds(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" && /[+\-]\d+/.test(value.trim())) {
    return value;
  }
  const n = parseNumber(value);
  if (!n) return "-";
  return (n > 0 ? "+" : "") + n.toString();
}

function formatEV(value) {
  const n = parseNumber(value);
  if (!Number.isFinite(n)) return "–";
  return n.toFixed(2) + "%";
}

function getEvClass(ev) {
  if (!Number.isFinite(ev)) return "ev-neutral";
  if (ev >= 5) return "ev-strong-positive";
  if (ev >= 0) return "ev-mild-positive";
  if (ev < 0) return "ev-negative";
  return "ev-neutral";
}

function sanitize(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

