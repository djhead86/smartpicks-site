const DATA_URL = "data/data.json";

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadData();
});

/* ========= TAB SYSTEM ========= */

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const sections = document.querySelectorAll(".tab-content");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");

      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      sections.forEach((sec) =>
        sec.classList.toggle("active", sec.id === target)
      );
    });
  });
}

/* ========= LOAD DATA.JSON ========= */

async function loadData() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    const data = await res.json();

    renderSummaryTab(data);
    renderPicksTab(data);
    renderAnalyticsTab(data);
    renderHistoryTab(data);

    setLastUpdated();
  } catch (err) {
    console.error("Failed to load data.json", err);
    document.getElementById("summary").innerHTML =
      "<p class='muted'>Failed to load SmartPicks data.json.</p>";
  }
}

/* ========= SUMMARY TAB ========= */

function renderSummaryTab(data) {
  const section = document.getElementById("summary");
  const daily = data.daily_summary || {};
  const perf = data.performance || {};

  const date = daily.date || "—";
  const totalBets = daily.total_bets ?? perf.total_bets ?? 0;
  const record =
    daily.record ||
    `${perf.wins || 0}-${perf.losses || 0}-${perf.pushes || 0}`;

  const winPct =
    (daily.win_pct ?? (perf.wins || 0) / (perf.total_bets || 1)) * 100;

  const unitsWagered = daily.units_wagered ?? perf.units_wagered ?? 0;
  const expectedProfit = daily.expected_profit ?? perf.expected_profit ?? 0;
  const actualProfit = daily.actual_profit ?? perf.actual_profit ?? 0;
  const roiPct = daily.roi_pct ?? perf.roi_pct ?? 0;
  const bankroll = daily.bankroll ?? perf.current_bankroll ?? 0;

  const formatPct = (x) =>
    Number.isFinite(x) ? `${x.toFixed(1)}%` : "—";
  const money = (x) =>
    Number.isFinite(x) ? (x >= 0 ? `+${x.toFixed(2)}u` : `${x.toFixed(2)}u`) : "—";
  const num = (x) => (Number.isFinite(x) ? x.toFixed(2) : "—");

  section.innerHTML = `
    <div class="section-title">Today at a Glance (${date})</div>

    <div class="summary-grid">
      <div class="metric-card">
        <div class="metric-label">Record</div>
        <div class="metric-value">${record}</div>
        <div class="metric-sub">Total bets: ${totalBets}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Win Rate</div>
        <div class="metric-value">${formatPct(winPct)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Expected Profit</div>
        <div class="metric-value">${money(expectedProfit)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Actual Profit</div>
        <div class="metric-value">${money(actualProfit)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">ROI</div>
        <div class="metric-value">${formatPct(roiPct)}</div>
        <div class="metric-sub">${num(unitsWagered)}u staked</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Bankroll</div>
        <div class="metric-value">${num(bankroll)}u</div>
      </div>
    </div>

    <div class="summary-blurb">
      SmartPicksGPT evaluates implied probabilities from market odds to identify value.
      For educational use only.
    </div>
  `;
}

/* ========= PICKS TAB ========= */

function normalizeSport(sport) {
  const map = {
    basketball_nba: "NBA",
    americanfootball_nfl: "NFL",
    americanfootball_ncaaf: "NCAAF",
    icehockey_nhl: "NHL",
    soccer: "Soccer",
    soccer_epl: "EPL",
    soccer_laliga: "La Liga",
    soccer_bundesliga: "Bundesliga",
    mma: "MMA",
    ufc: "UFC",
    mixedmartialarts_ufc: "UFC",
  };
  return map[sport] || (sport ? sport.toUpperCase() : "Unknown");
}

function normalizeMarket(m) {
  const map = {
    h2h: "Moneyline",
    spreads: "Spread",
    totals: "Over/Under",
    ou: "Over/Under",
  };
  return map[m] || m?.toUpperCase() || "—";
}

function formatAmericanOdds(price) {
  if (!Number.isFinite(price)) return "—";
  return price > 0 ? `+${price}` : `${price}`;
}

function classifyEVBadge(ev) {
  if (!Number.isFinite(ev)) return "badge-ev-neutral";
  if (ev > 0.01) return "badge-ev-positive";
  if (ev < -0.01) return "badge-ev-negative";
  return "badge-ev-neutral";
}

function formatEV(ev) {
  if (!Number.isFinite(ev)) return "—";
  if (Math.abs(ev) < 0.0000001) return "~0%";
  return (ev >= 0 ? "+" : "") + (ev * 100).toFixed(2) + "%";
}

function renderPicksTab(data) {
  const section = document.getElementById("picks");
  const picks = data.top10 || [];

  if (!picks.length) {
    section.innerHTML = `<p class="muted">No picks available.</p>`;
    return;
  }

  section.innerHTML = `
    <div class="section-title">Today’s Top Value Bets</div>
    <div class="picks-grid">
      ${picks
        .map((p, i) => {
          return `
          <article class="pick-card">
            <div class="pick-header">
              <div>
                <div class="pick-rank">#${i + 1}</div>
                <div class="pick-main">${p.team} <span class="muted">${p.match}</span></div>
              </div>
              <div class="pick-rank">${normalizeMarket(p.market)}</div>
            </div>

            <div class="pick-match">${p.event_time || ""}</div>

            <div class="pick-meta-row">
              <span class="badge badge-sport">${normalizeSport(p.sport)}</span>
              <span class="badge badge-price">Odds: ${formatAmericanOdds(p.price)}</span>
              <span class="badge ${classifyEVBadge(p.adj_ev ?? p.ev)}">
                EV: ${formatEV(p.adj_ev ?? p.ev)}
              </span>
            </div>

            <p class="pick-reason">${p.why || ""}</p>
          </article>`;
        })
        .join("")}
    </div>
  `;
}

/* ========= ANALYTICS TAB ========= */

let bankrollChartInstance = null;
let winChartInstance = null;

function renderAnalyticsTab(data) {
  const section = document.getElementById("analytics");
  const perf = data.performance || {};

  const history = perf.bankroll_history || [];
  const wins = perf.wins || 0;
  const losses = perf.losses || 0;
  const pushes = perf.pushes || 0;

  section.innerHTML = `
    <div class="section-title">Performance Analytics</div>

    <div class="analytics-grid">

      <div class="analytics-card">
        <h3>Bankroll Over Time</h3>
        <div class="chart-wrapper">
          <canvas id="bankrollChart"></canvas>
        </div>
      </div>

      <div class="analytics-card">
        <h3>Win / Loss Breakdown</h3>
        <div class="chart-wrapper">
          <canvas id="winChart"></canvas>
        </div>
      </div>

    </div>
  `;

  drawBankrollChart(history);
  drawWinChart({ wins, losses, pushes });
}

function drawBankrollChart(history) {
  const ctx = document.getElementById("bankrollChart");
  if (!ctx) return;

  if (bankrollChartInstance) bankrollChartInstance.destroy();

  if (history.length <= 1) {
    // Draw a single bar rather than a 1-point line
    bankrollChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: history.map((h) => h.date),
        datasets: [
          {
            label: "Bankroll (u)",
            data: history.map((h) => h.bankroll),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
      },
    });
    return;
  }

  // Multi-point line chart
  bankrollChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: history.map((h) => h.date),
      datasets: [
        {
          label: "Bankroll (u)",
          data: history.map((h) => h.bankroll),
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
    },
  });
}

function drawWinChart({ wins, losses, pushes }) {
  const ctx = document.getElementById("winChart");
  if (!ctx) return;

  if (winChartInstance) winChartInstance.destroy();

  const total = wins + losses + pushes;
  if (total === 0) return;

  winChartInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Wins", "Losses", "Pushes"],
      datasets: [
        {
          data: [wins, losses, pushes],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

/* ========= HISTORY TAB ========= */

function renderHistoryTab(data) {
  const section = document.getElementById("history");
  const history = data.history || [];

  if (!history.length) {
    section.innerHTML = `
      <div class="section-title">Bet History</div>
      <p class="muted">
        You have no bet history yet.  
        Once smart_picks.py writes a <code>"history"</code> array into data.json,  
        all graded bets will automatically appear here.
      </p>
    `;
    return;
  }

  section.innerHTML = `
    <div class="section-title">Bet History</div>

    <div class="table-wrapper">
      <table class="history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Sport</th>
            <th>Match</th>
            <th>Market</th>
            <th>Team</th>
            <th>Odds</th>
            <th>Stake</th>
            <th>Result</th>
            <th>EV</th>
          </tr>
        </thead>
        <tbody>
          ${history
            .map((b) => {
              return `
              <tr>
                <td>${b.date}</td>
                <td>${normalizeSport(b.sport)}</td>
                <td>${b.match}</td>
                <td>${normalizeMarket(b.market)}</td>
                <td>${b.team}</td>
                <td>${formatAmericanOdds(b.odds)}</td>
                <td>${b.stake ?? "—"}</td>
                <td>${b.result}</td>
                <td>${Number.isFinite(b.ev) ? b.ev.toFixed(3) : "—"}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

/* ========= META ========= */

function setLastUpdated() {
  const el = document.getElementById("last-updated");
  if (!el) return;
  el.textContent = "Last update: " + new Date().toLocaleString();
}

