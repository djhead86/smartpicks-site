// SMARTPICKSGPT DASHBOARD SCRIPT
// ================================================
// Features:
// - Load data.json with cache-busting
// - Summary, Top Picks, Performance, Analytics charts
// - History tab: only bets within next 24 hours
// - Future Bets tab: upcoming 7 days (collapsible)
// - Pagination for History & Future tables
// - Colored status badges (WIN / LOSS / PENDING)
// ================================================

let historyDataFiltered = [];
let futureDataFiltered = [];
let historyPage = 1;
let futurePage = 1;
const HISTORY_PER_PAGE = 10;
const FUTURE_PER_PAGE = 10;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  buildFutureTabSkeleton();
  loadData();
});

// ----------------------------
// Load data.json
// ----------------------------
async function loadData() {
  try {
    const response = await fetch("data/data.json?cache=" + Date.now());
    const data = await response.json();

    populateLastUpdated(data);
    populateTopPicks(data.top10 || []);
    populateDailySummary(data.daily_summary);
    populatePerformance(data.performance);
    populateBetHistoryFiltered(data.history || []);
    populateFutureBets(data.history || []);
    renderCharts(data.analytics || {});
  } catch (err) {
    console.error("Failed to load data.json:", err);
  }
}

// ----------------------------
// Last Updated timestamp
// ----------------------------
function populateLastUpdated(data) {
  const el = document.getElementById("last-updated");
  if (!el || !data.last_updated) return;
  el.textContent = "Last update: " + new Date(data.last_updated).toLocaleString();
}

// ----------------------------
// TOP PICKS
// ----------------------------
function populateTopPicks(topPicks) {
  const container = document.getElementById("top-picks");
  if (!container) return;

  container.innerHTML = "";

  if (!Array.isArray(topPicks) || topPicks.length === 0) {
    container.innerHTML = `<p class="muted">No top picks available.</p>`;
    return;
  }

  topPicks.forEach((pick) => {
    const card = document.createElement("div");
    card.className = "pick-card";

    const confidencePct =
      pick.confidence != null ? (pick.confidence * 100).toFixed(1) + "%" : "—";

    card.innerHTML = `
      <div class="pick-header">
        <h3>${formatSport(pick.sport)}</h3>
        <span class="event-time">${formatDateTime(pick.event_time)}</span>
      </div>
      <p class="match"><strong>${pick.match}</strong></p>
      <p>Pick: <strong>${pick.team}</strong> (${pick.market.toUpperCase()})</p>
      <p>Price: ${pick.price}</p>
      <p>Model Prob: ${(pick.prob * 100).toFixed(1)}%</p>
      <p>Confidence: ${confidencePct}</p>
      <p>Stake: ${pick.recommended_stake.toFixed(2)} units</p>
      <p class="why">${pick.why || ""}</p>
    `;

    container.appendChild(card);
  });
}

// ----------------------------
// DAILY SUMMARY
// ----------------------------
function populateDailySummary(sum) {
  const el = document.getElementById("summary");
  if (!el || !sum) return;

  el.innerHTML = `
    <div class="summary-grid">
      <div class="summary-item"><span>Bets Today</span><strong>${sum.total_bets}</strong></div>
      <div class="summary-item"><span>Record</span><strong>${sum.record}</strong></div>
      <div class="summary-item"><span>Win %</span><strong>${(sum.win_pct * 100).toFixed(1)}%</strong></div>
      <div class="summary-item"><span>Units Wagered</span><strong>${sum.units_wagered.toFixed(2)}</strong></div>
      <div class="summary-item"><span>Expected Profit</span><strong>${sum.expected_profit.toFixed(2)}</strong></div>
      <div class="summary-item"><span>Actual Profit</span><strong>${sum.actual_profit.toFixed(2)}</strong></div>
      <div class="summary-item"><span>ROI</span><strong>${(sum.roi_pct * 100).toFixed(2)}%</strong></div>
      <div class="summary-item"><span>Bankroll</span><strong>${sum.bankroll.toFixed(2)}</strong></div>
    </div>
  `;
}

// ----------------------------
// PERFORMANCE OVERALL
// ----------------------------
function populatePerformance(perf) {
  const el = document.getElementById("performance");
  if (!el || !perf) return;

  el.innerHTML = `
    <div class="perf-grid">
      <div><span>Total Bets</span><strong>${perf.total_bets}</strong></div>
      <div><span>Wins</span><strong>${perf.wins}</strong></div>
      <div><span>Losses</span><strong>${perf.losses}</strong></div>
      <div><span>Win %</span><strong>${(perf.win_pct * 100).toFixed(1)}%</strong></div>
      <div><span>Units Wagered</span><strong>${perf.units_wagered.toFixed(2)}</strong></div>
      <div><span>Expected Profit</span><strong>${perf.expected_profit.toFixed(2)}</strong></div>
      <div><span>Actual Profit</span><strong>${perf.actual_profit.toFixed(2)}</strong></div>
      <div><span>ROI</span><strong>${(perf.roi_pct * 100).toFixed(2)}%</strong></div>
      <div><span>Current Bankroll</span><strong>${perf.current_bankroll.toFixed(2)}</strong></div>
    </div>
  `;
}

// ------------------------------------------------------
// HISTORY TAB — ONLY NEXT 24 HOURS (Option A)
// ------------------------------------------------------
function populateBetHistoryFiltered(history) {
  const now = new Date();
  const cutoff = new Date(now.getTime() + 24 * 60 * 60 * 1000);

  historyDataFiltered = (history || []).filter((item) => {
    const eventTime = new Date(item.event_time);
    return eventTime >= now && eventTime <= cutoff;
  });

  historyPage = 1;
  renderHistoryPage();
}

function renderHistoryPage() {
  const tbody = document.getElementById("history-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!historyDataFiltered.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted">No bets in the next 24 hours.</td></tr>`;
    renderHistoryPagination();
    return;
  }

  const start = (historyPage - 1) * HISTORY_PER_PAGE;
  const end = start + HISTORY_PER_PAGE;
  const pageData = historyDataFiltered.slice(start, end);

  pageData.forEach((row, idx) => {
    const tr = document.createElement("tr");
    tr.className = idx % 2 === 0 ? "row-even" : "row-odd";

    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${formatDateTime(row.event_time)}</td>
      <td>${formatSport(row.sport)}</td>
      <td>${row.match}</td>
      <td>${row.team} (${row.market})</td>
      <td>${row.price}</td>
      <td>${row.stake.toFixed(2)}</td>
      <td>${statusBadgeHtml(row.result)}</td>
      <td>${row.profit.toFixed(2)}</td>
      <td>${row.bankroll_after.toFixed(2)}</td>
    `;

    tbody.appendChild(tr);
  });

  renderHistoryPagination();
}

function renderHistoryPagination() {
  const container = document.getElementById("history-pagination");
  if (!container) return;

  container.innerHTML = "";

  if (!historyDataFiltered.length) return;

  const totalPages = Math.ceil(historyDataFiltered.length / HISTORY_PER_PAGE);

  const prevBtn = document.createElement("button");
  prevBtn.textContent = "Prev";
  prevBtn.disabled = historyPage === 1;
  prevBtn.onclick = () => {
    if (historyPage > 1) {
      historyPage--;
      renderHistoryPage();
    }
  };

  const nextBtn = document.createElement("button");
  nextBtn.textContent = "Next";
  nextBtn.disabled = historyPage === totalPages;
  nextBtn.onclick = () => {
    if (historyPage < totalPages) {
      historyPage++;
      renderHistoryPage();
    }
  };

  const pageInfo = document.createElement("span");
  pageInfo.className = "page-info";
  pageInfo.textContent = `Page ${historyPage} of ${totalPages}`;

  container.appendChild(prevBtn);
  container.appendChild(pageInfo);
  container.appendChild(nextBtn);
}

// ------------------------------------------------------
// FUTURE BETS TAB — UPCOMING 7 DAYS (Collapsible)
// ------------------------------------------------------
function buildFutureTabSkeleton() {
  const root = document.getElementById("future-root");
  if (!root || root.dataset.built === "true") return;
  root.dataset.built = "true";

  root.innerHTML = `
    <div class="future-header">
      <h2>Future Bets</h2>
      <p class="muted">Upcoming bets over the next 7 days.</p>
      <button id="future-toggle" class="collapse-button">Hide / Show Upcoming 7 Days</button>
    </div>
    <div id="future-content" class="future-content open">
      <div id="future-summary" class="future-summary"></div>
      <div class="table-wrapper">
        <table class="bets-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Event Time</th>
              <th>Sport</th>
              <th>Match</th>
              <th>Pick</th>
              <th>Price</th>
              <th>Stake</th>
              <th>Status</th>
              <th>Profit</th>
              <th>Bankroll After</th>
            </tr>
          </thead>
          <tbody id="future-table-body"></tbody>
        </table>
      </div>
      <div id="future-pagination" class="pagination"></div>
    </div>
  `;

  const toggleBtn = document.getElementById("future-toggle");
  const content = document.getElementById("future-content");

  if (toggleBtn && content) {
    toggleBtn.addEventListener("click", () => {
      content.classList.toggle("open");
      content.classList.toggle("closed");
    });
  }
}

function populateFutureBets(history) {
  const now = new Date();
  const sevenDaysOut = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

  futureDataFiltered = (history || []).filter((item) => {
    const eventTime = new Date(item.event_time);
    return eventTime > now && eventTime <= sevenDaysOut;
  });

  futurePage = 1;
  renderFuturePage();
  renderFutureSummary();
}

function renderFuturePage() {
  const tbody = document.getElementById("future-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!futureDataFiltered.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted">No upcoming bets in the next 7 days.</td></tr>`;
    renderFuturePagination();
    return;
  }

  const start = (futurePage - 1) * FUTURE_PER_PAGE;
  const end = start + FUTURE_PER_PAGE;
  const pageData = futureDataFiltered.slice(start, end);

  pageData.forEach((row, idx) => {
    const tr = document.createElement("tr");
    tr.className = idx % 2 === 0 ? "row-even" : "row-odd";

    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${formatDateTime(row.event_time)}</td>
      <td>${formatSport(row.sport)}</td>
      <td>${row.match}</td>
      <td>${row.team} (${row.market})</td>
      <td>${row.price}</td>
      <td>${row.stake.toFixed(2)}</td>
      <td>${statusBadgeHtml(row.result)}</td>
      <td>${row.profit.toFixed(2)}</td>
      <td>${row.bankroll_after.toFixed(2)}</td>
    `;

    tbody.appendChild(tr);
  });

  renderFuturePagination();
}

function renderFuturePagination() {
  const container = document.getElementById("future-pagination");
  if (!container) return;

  container.innerHTML = "";

  if (!futureDataFiltered.length) return;

  const totalPages = Math.ceil(futureDataFiltered.length / FUTURE_PER_PAGE);

  const prevBtn = document.createElement("button");
  prevBtn.textContent = "Prev";
  prevBtn.disabled = futurePage === 1;
  prevBtn.onclick = () => {
    if (futurePage > 1) {
      futurePage--;
      renderFuturePage();
    }
  };

  const nextBtn = document.createElement("button");
  nextBtn.textContent = "Next";
  nextBtn.disabled = futurePage === totalPages;
  nextBtn.onclick = () => {
    if (futurePage < totalPages) {
      futurePage++;
      renderFuturePage();
    }
  };

  const pageInfo = document.createElement("span");
  pageInfo.className = "page-info";
  pageInfo.textContent = `Page ${futurePage} of ${totalPages}`;

  container.appendChild(prevBtn);
  container.appendChild(pageInfo);
  container.appendChild(nextBtn);
}

function renderFutureSummary() {
  const summaryEl = document.getElementById("future-summary");
  if (!summaryEl) return;

  if (!futureDataFiltered.length) {
    summaryEl.innerHTML = `<p class="muted">No upcoming bets scheduled in the next 7 days.</p>`;
    return;
  }

  const count = futureDataFiltered.length;
  const totalStake = futureDataFiltered.reduce(
    (sum, r) => sum + (r.stake || 0),
    0
  );

  summaryEl.innerHTML = `
    <div class="future-summary-grid">
      <div><span>Upcoming Bets (7 Days)</span><strong>${count}</strong></div>
      <div><span>Total Stake</span><strong>${totalStake.toFixed(2)} units</strong></div>
    </div>
  `;
}

// ----------------------------
// CHARTS
// ----------------------------
function renderCharts(analytics) {
  renderROIChart(analytics.roi_history || []);
  renderBankrollChart(analytics.bankroll_history || []);
  renderWinrateChart(analytics.sport_winrates || {});
}

function renderROIChart(history) {
  const ctx = document.getElementById("roi-chart");
  if (!ctx || !history.length) return;

  new Chart(ctx, {
    type: "line",
    data: {
      labels: history.map((e) => e.date),
      datasets: [
        {
          label: "ROI %",
          data: history.map((e) => e.roi_pct * 100),
          borderWidth: 2
        }
      ]
    }
  });
}

function renderBankrollChart(history) {
  const ctx = document.getElementById("bankroll-chart");
  if (!ctx || !history.length) return;

  new Chart(ctx, {
    type: "line",
    data: {
      labels: history.map((e) => e.date),
      datasets: [
        {
          label: "Bankroll",
          data: history.map((e) => e.bankroll),
          borderWidth: 2
        }
      ]
    }
  });
}

function renderWinrateChart(winrates) {
  const ctx = document.getElementById("winrate-chart");
  if (!ctx || !Object.keys(winrates).length) return;

  const labels = Object.keys(winrates);
  const values = Object.values(winrates).map((v) => v * 100);

  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Win % by Sport",
          data: values,
          borderWidth: 1
        }
      ]
    }
  });
}

// ----------------------------
// TAB HANDLER
// ----------------------------
function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const contents = document.querySelectorAll(".tab-content");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.tab;

      buttons.forEach((b) => b.classList.remove("active"));
      contents.forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const target = document.getElementById(targetId);
      if (target) target.classList.add("active");
    });
  });
}

// ----------------------------
// HELPERS
// ----------------------------
function formatDateTime(dtString) {
  if (!dtString) return "—";
  const d = new Date(dtString);
  if (isNaN(d.getTime())) return dtString;
  return d.toLocaleString();
}

function formatSport(s) {
  if (!s) return "";
  return s.replace(/_/g, " ").toUpperCase();
}

function statusBadgeHtml(status) {
  const s = (status || "").toUpperCase();
  let cls = "status-badge ";

  if (s === "WIN") cls += "status-win";
  else if (s === "LOSS") cls += "status-loss";
  else if (s === "PENDING") cls += "status-pending";
  else cls += "status-other";

  return `<span class="${cls}">${s || "—"}</span>`;
}


