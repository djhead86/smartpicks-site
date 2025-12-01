// SmartPicksGPT Ultra Dashboard JS
// Supports both:
// 1) Old schema: data.json = [ array of picks ]
// 2) New schema: data.json = { picks: [...], history: [...], summary: {...}, meta: {...} }

let allPicks = [];
let filteredPicks = [];
let allHistory = [];
let summaryData = null;
let metaData = null;

// History pagination
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

/* ========== INIT ========== */

function initTheme() {
  const saved = localStorage.getItem("sp_theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
  }

  const toggleBtn = document.getElementById("theme-toggle");
  updateThemeIcon();

  toggleBtn.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem(
      "sp_theme",
      document.body.classList.contains("dark") ? "dark" : "light"
    );
    updateThemeIcon();
    // Charts need to update theme colors if needed; keep it simple for now
  });
}

function updateThemeIcon() {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;
  toggleBtn.textContent = document.body.classList.contains("dark") ? "☀️" : "🌙";
}

function initTabs() {
  const buttons = document.querySelectorAll(".tab-button");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");

      document
        .querySelectorAll(".tab-button")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      document
        .querySelectorAll(".tab-content")
        .forEach((section) => section.classList.remove("active"));

      const target = document.getElementById(`tab-${tab}`);
      if (target) {
        target.classList.add("active");
      }
    });
  });
}

function initSearch() {
  const searchInput = document.getElementById("picks-search");
  if (!searchInput) return;

  searchInput.addEventListener("input", (e) => {
    const term = e.target.value.toLowerCase().trim();
    if (!term) {
      filteredPicks = [...allPicks];
    } else {
      filteredPicks = allPicks.filter((p) => {
        const team = String(p.team || "").toLowerCase();
        const match = String(p.match || "").toLowerCase();
        const market = String(p.market || "").toLowerCase();
        return (
          team.includes(term) || match.includes(term) || market.includes(term)
        );
      });
    }
    renderPicks();
    updateEvChart();
  });
}

function initHistoryPagination() {
  const prevBtn = document.getElementById("history-prev");
  const nextBtn = document.getElementById("history-next");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentHistoryPage > 1) {
        currentHistoryPage--;
        renderHistory();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(allHistory.length / PAGE_SIZE));
      if (currentHistoryPage < totalPages) {
        currentHistoryPage++;
        renderHistory();
      }
    });
  }
}

/* ========== DATA LOADING ========== */

function loadData() {
  fetch("data.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load data.json (${r.status})`);
      return r.json();
    })
    .then((json) => {
      // Detect schema
      if (Array.isArray(json)) {
        allPicks = json;
        filteredPicks = [...allPicks];
        allHistory = [];
        summaryData = null;
        metaData = null;
      } else if (json && typeof json === "object") {
        allPicks = Array.isArray(json.picks) ? json.picks : [];
        filteredPicks = [...allPicks];
        allHistory = Array.isArray(json.history) ? json.history : [];
        summaryData = json.summary || null;
        metaData = json.meta || null;
      } else {
        allPicks = [];
        filteredPicks = [];
        allHistory = [];
        summaryData = null;
        metaData = null;
      }

      renderAll();
    })
    .catch((err) => {
      console.error(err);
      showLoadError(err.message);
    });
}

function showLoadError(message) {
  const picksContainer = document.getElementById("picks-container");
  const picksEmpty = document.getElementById("picks-empty");
  if (picksContainer) picksContainer.innerHTML = "";
  if (picksEmpty) {
    picksEmpty.classList.remove("hidden");
    picksEmpty.textContent = `⚠️ Could not load picks (${message}).`;
  }
}

/* ========== RENDER ROOT ========== */

function renderAll() {
  renderMeta();
  renderSummary();
  renderPicks();
  renderHistory();
  setupAutoHiding();
  updateCharts();
}

/* ========== META / LAST UPDATED ========== */

function renderMeta() {
  const labelEl = document.getElementById("last-updated-value");
  if (!labelEl) return;

  // Try meta.generated_at then summary.generated_at, else fallback
  let ts = null;
  if (metaData && metaData.generated_at) ts = metaData.generated_at;
  else if (summaryData && summaryData.generated_at)
    ts = summaryData.generated_at;

  labelEl.textContent = ts || "Unknown";
}

/* ========== SUMMARY ========== */

function renderSummary() {
  const totalBetsEl = document.getElementById("summary-total-bets");
  const winRateEl = document.getElementById("summary-win-rate");
  const roiEl = document.getElementById("summary-roi");
  const bankrollEl = document.getElementById("summary-bankroll");
  const countLabel = document.getElementById("history-count-label");

  // If we have explicit summary data, use it
  if (summaryData) {
    if (totalBetsEl)
      totalBetsEl.textContent = formatNumber(summaryData.total_bets ?? "–");
    if (winRateEl)
      winRateEl.textContent = formatPercent(summaryData.win_rate);
    if (roiEl) roiEl.textContent = formatPercent(summaryData.roi);
    if (bankrollEl)
      bankrollEl.textContent = formatCurrency(summaryData.net_profit);

    if (countLabel) {
      const settled = summaryData.settled_bets ?? allHistory.length ?? 0;
      countLabel.textContent = `${settled} settled bets`;
    }
    return;
  }

  // Otherwise, derive simple stats from history if present
  const bets = allHistory;
  if (!bets || bets.length === 0) {
    if (totalBetsEl) totalBetsEl.textContent = "–";
    if (winRateEl) winRateEl.textContent = "–";
    if (roiEl) roiEl.textContent = "–";
    if (bankrollEl) bankrollEl.textContent = "–";
    if (countLabel) countLabel.textContent = "0 settled bets";
    return;
  }

  const total = bets.length;
  const wins = bets.filter((b) =>
    String(b.result || "").toLowerCase().includes("win")
  ).length;

  const pnlValues = bets.map((b) => parseNumber(b.profit ?? b.pnl ?? 0));
  const totalPnl = pnlValues.reduce((a, v) => a + v, 0);

  const stakeValues = bets.map((b) => parseNumber(b.stake ?? b.staked ?? 0));
  const totalStake = stakeValues.reduce((a, v) => a + v, 0);

  const winRate = total > 0 ? wins / total : null;
  const roi = totalStake > 0 ? totalPnl / totalStake : null;

  if (totalBetsEl) totalBetsEl.textContent = formatNumber(total);
  if (winRateEl) winRateEl.textContent = formatPercent(winRate);
  if (roiEl) roiEl.textContent = formatPercent(roi);
  if (bankrollEl) bankrollEl.textContent = formatCurrency(totalPnl);
  if (countLabel) countLabel.textContent = `${total} settled bets`;
}

/* ========== PICKS ========== */

function renderPicks() {
  const container = document.getElementById("picks-container");
  const emptyEl = document.getElementById("picks-empty");
  const countLabel = document.getElementById("picks-count-label");

  if (!container || !emptyEl) return;

  container.innerHTML = "";

  const picks = filteredPicks || [];
  if (countLabel) {
    countLabel.textContent = `${picks.length} pick${picks.length === 1 ? "" : "s"} loaded`;
  }

  if (picks.length === 0) {
    emptyEl.classList.remove("hidden");
    return;
  } else {
    emptyEl.classList.add("hidden");
  }

  picks.forEach((pick, idx) => {
    const card = document.createElement("article");
    card.className = "pick-card";

    const rank = pick.rank ?? idx + 1;
    const team = pick.team ?? "Unknown team";
    const market = pick.market ?? "market";
    const match = pick.match ?? pick.game ?? "Unknown matchup";
    const price = pick.price ?? pick.odds ?? "-";
    const reason = pick.reason ?? "";
    const sport = pick.sport ?? pick.league ?? "";
    const evRaw = pick.ev ?? pick.edge;
    const ev = parseNumber(evRaw);

    const evClass = getEvClass(ev);
    const evLabel = ev >= 0 ? "Positive EV" : "Negative EV";

    card.innerHTML = `
      <div class="pick-header">
        <div>
          <div class="pick-title">#${rank} – ${team}</div>
          <div class="pick-meta">
            ${match}${sport ? " · " + sport : ""}<br />
            <span class="pick-badge">${market}</span>
          </div>
        </div>
      </div>
      <div class="pick-footer">
        <div class="pick-odds">
          <strong>Odds:</strong> ${formatOdds(price)}
        </div>
        <div class="pick-ev-pill ${evClass}">
          <span>${evLabel}</span>
          <strong>${formatEV(evRaw)}</strong>
        </div>
      </div>
      ${
        reason
          ? `<div class="pick-meta"><strong>Reason:</strong> ${sanitize(reason)}</div>`
          : ""
      }
    `;

    container.appendChild(card);
  });
}

/* ========== HISTORY ========== */

function renderHistory() {
  const tbody = document.getElementById("history-body");
  const emptyEl = document.getElementById("history-empty");
  const pager = document.getElementById("history-pagination");
  const pageInfo = document.getElementById("history-page-info");
  const prevBtn = document.getElementById("history-prev");
  const nextBtn = document.getElementById("history-next");

  if (!tbody || !emptyEl || !pager || !pageInfo) return;

  tbody.innerHTML = "";

  const total = allHistory.length;
  if (total === 0) {
    emptyEl.classList.remove("hidden");
    pager.classList.add("hidden");
    return;
  }
  emptyEl.classList.add("hidden");
  pager.classList.remove("hidden");

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (currentHistoryPage > totalPages) currentHistoryPage = totalPages;

  const startIdx = (currentHistoryPage - 1) * PAGE_SIZE;
  const pageItems = allHistory.slice(startIdx, startIdx + PAGE_SIZE);

  pageItems.forEach((bet) => {
    const tr = document.createElement("tr");

    const date = bet.date ?? bet.game_date ?? bet.settled_at ?? "";
    const sport = bet.sport ?? bet.league ?? "";
    const match = bet.match ?? bet.game ?? "";
    const pick = bet.team ?? bet.selection ?? "";
    const market = bet.market ?? "";
    const price = bet.price ?? bet.odds ?? "";
    const resultRaw = String(bet.result ?? bet.outcome ?? "").toLowerCase();
    const pnlRaw = bet.profit ?? bet.pnl ?? 0;
    const pnl = parseNumber(pnlRaw);

    const resultClass = resultRaw.includes("win")
      ? "result-win"
      : resultRaw.includes("loss") || resultRaw.includes("lose")
      ? "result-loss"
      : "";
    const pnlClass =
      pnl > 0 ? "pnl-positive" : pnl < 0 ? "pnl-negative" : "";

    tr.innerHTML = `
      <td>${sanitize(date)}</td>
      <td>${sanitize(sport)}</td>
      <td>${sanitize(match)}</td>
      <td>${sanitize(pick)}</td>
      <td>${sanitize(market)}</td>
      <td>${formatOdds(price)}</td>
      <td class="${resultClass}">${sanitize(bet.result ?? bet.outcome ?? "")}</td>
      <td class="${pnlClass}">${formatCurrency(pnl)}</td>
    `;

    tbody.appendChild(tr);
  });

  // Update pagination controls
  pageInfo.textContent = `Page ${currentHistoryPage} / ${totalPages}`;
  if (prevBtn) prevBtn.disabled = currentHistoryPage <= 1;
  if (nextBtn) nextBtn.disabled = currentHistoryPage >= totalPages;
}

/* ========== AUTO-HIDING EMPTY SECTIONS ========== */

function setupAutoHiding() {
  // Summary: hide tab if no summary and no history
  const summaryTabButton = document.querySelector('[data-tab="summary"]');
  const summarySection = document.getElementById("tab-summary");
  const hideSummary = !summaryData && (!allHistory || allHistory.length === 0);

  if (summaryTabButton && summarySection) {
    if (hideSummary) {
      summaryTabButton.classList.add("hidden");
      summarySection.classList.add("hidden");
      // If summary is currently active, switch to picks
      if (summarySection.classList.contains("active")) {
        summarySection.classList.remove("active");
        const picksSection = document.getElementById("tab-picks");
        const picksTabButton = document.querySelector('[data-tab="picks"]');
        if (picksSection && picksTabButton) {
          picksSection.classList.add("active");
          document
            .querySelectorAll(".tab-button")
            .forEach((b) => b.classList.remove("active"));
          picksTabButton.classList.add("active");
        }
      }
    }
  }

  // Picks: hide tab if no picks
  const picksTabButton = document.querySelector('[data-tab="picks"]');
  const picksSection = document.getElementById("tab-picks");
  if (picksTabButton && picksSection) {
    if (!allPicks || allPicks.length === 0) {
      picksTabButton.classList.add("hidden");
      picksSection.classList.add("hidden");
    }
  }

  // History: hide tab if no history
  const historyTabButton = document.querySelector('[data-tab="history"]');
  const historySection = document.getElementById("tab-history");
  if (historyTabButton && historySection) {
    if (!allHistory || allHistory.length === 0) {
      historyTabButton.classList.add("hidden");
      historySection.classList.add("hidden");
    }
  }
}

/* ========== CHARTS ========== */

function updateCharts() {
  updatePerformanceChart();
  updateEvChart();
}

function updatePerformanceChart() {
  const canvas = document.getElementById("chart-performance");
  const emptyMsg = document.getElementById("chart-performance-empty");
  if (!canvas || !emptyMsg) return;

  if (!allHistory || allHistory.length === 0) {
    emptyMsg.classList.remove("hidden");
    if (performanceChart) {
      performanceChart.destroy();
      performanceChart = null;
    }
    return;
  }

  // Build cumulative PnL by date (best effort)
  const byDate = {};
  allHistory.forEach((b) => {
    const date =
      b.date ?? b.game_date ?? (b.settled_at || "").slice(0, 10) ?? "Unknown";
    const pnl = parseNumber(b.profit ?? b.pnl ?? 0);
    if (!byDate[date]) byDate[date] = 0;
    byDate[date] += pnl;
  });

  const dates = Object.keys(byDate).sort();
  if (dates.length === 0) {
    emptyMsg.classList.remove("hidden");
    if (performanceChart) {
      performanceChart.destroy();
      performanceChart = null;
    }
    return;
  }

  const cumulative = [];
  let running = 0;
  dates.forEach((d) => {
    running += byDate[d];
    cumulative.push(running);
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

  if (!filteredPicks || filteredPicks.length === 0) {
    emptyMsg.classList.remove("hidden");
    if (evChart) {
      evChart.destroy();
      evChart = null;
    }
    return;
  }

  const evValues = filteredPicks
    .map((p) => parseNumber(p.ev ?? p.edge))
    .filter((v) => !isNaN(v));

  if (evValues.length === 0) {
    emptyMsg.classList.remove("hidden");
    if (evChart) {
      evChart.destroy();
      evChart = null;
    }
    return;
  }

  emptyMsg.classList.add("hidden");

  // Simple buckets: <0, 0–2.5, 2.5–5, >5
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
      labels: ["EV < 0", "0–2.5", "2.5–5", "> 5"],
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

/* ========== HELPERS ========== */

function parseNumber(value) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const cleaned = value.replace(/[^\d.-]/g, "");
    const n = Number(cleaned);
    return isNaN(n) ? 0 : n;
  }
  return 0;
}

function formatNumber(value) {
  const n = parseNumber(value);
  if (!isFinite(n)) return "–";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "–";
  const n = typeof value === "number" ? value : parseNumber(value);
  if (!isFinite(n)) return "–";
  return (n * 100).toFixed(1) + "%";
}

function formatCurrency(value) {
  const n = parseNumber(value);
  if (!isFinite(n) || n === 0) return "$0";
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
  const asNum = parseNumber(value);
  // If original looked like +XXX or -XXX, return as is; otherwise add sign
  if (typeof value === "string" && /[+\-]\d+/.test(value.trim())) {
    return value;
  }
  if (asNum === 0) return "-";
  return (asNum > 0 ? "+" : "") + asNum.toString();
}

function formatEV(value) {
  // Could be already percent or decimal
  const n = parseNumber(value);
  if (!isFinite(n)) return "–";
  return n.toFixed(2) + "%";
}

function getEvClass(ev) {
  if (!isFinite(ev)) return "ev-neutral";
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

