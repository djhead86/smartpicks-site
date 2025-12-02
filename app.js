const DATA_URL = "data/data.json";

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadData();
});

/* ===== TAB LOGIC ===== */

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const sections = document.querySelectorAll(".tab-content");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");

      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      sections.forEach((sec) => {
        sec.classList.toggle("active", sec.id === target);
      });
    });
  });
}

/* ===== DATA LOADING ===== */

async function loadData() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderSummaryTab(data);
    renderPicksTab(data);
    renderAnalyticsTab(data);
    renderHistoryTab(data);

    setLastUpdated();
  } catch (err) {
    console.error("Failed to load data.json", err);
    const summary = document.getElementById("summary");
    summary.innerHTML =
      '<p class="muted">Unable to load data. Check data/data.json and try again.</p>';
  }
}

/* ===== SUMMARY TAB ===== */

function renderSummaryTab(data) {
  const section = document.getElementById("summary");
  const daily = data.daily_summary || {};
  const perf = data.performance || {};

  const date = daily.date || "—";
  const totalBets = daily.total_bets ?? perf.total_bets ?? 0;
  const record = daily.record || `${perf.wins || 0}-${perf.losses || 0}-${perf.pushes || 0}`;
  const winPct = (daily.win_pct ?? (perf.wins || 0) / (perf.total_bets || 1)) * 100;
  const unitsWagered = daily.units_wagered ?? perf.units_wagered ?? 0;
  const expectedProfit = daily.expected_profit ?? perf.expected_profit ?? 0;
  const actualProfit = daily.actual_profit ?? perf.actual_profit ?? 0;
  const roiPct = daily.roi_pct ?? perf.roi_pct ?? 0;
  const bankroll = daily.bankroll ?? perf.current_bankroll ?? 0;

  const safePct = (x) =>
    Number.isFinite(x) ? x.toFixed(1) + "%" : "—";

  const fmtMoney = (x) =>
    typeof x === "number" ? (x >= 0 ? `+${x.toFixed(2)}u` : `${x.toFixed(2)}u`) : "—";

  const fmtNum = (x) =>
    typeof x === "number" ? x.toFixed(2) : "—";

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
        <div class="metric-value">${safePct(winPct)}</div>
        <div class="metric-sub">Incl. pushes in denominator</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Expected Profit</div>
        <div class="metric-value">${fmtMoney(expectedProfit)}</div>
        <div class="metric-sub">Model-implied edge</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Actual Profit</div>
        <div class="metric-value">${fmtMoney(actualProfit)}</div>
        <div class="metric-sub">Closed bets only</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">ROI</div>
        <div class="metric-value">${safePct(roiPct)}</div>
        <div class="metric-sub">On ${fmtNum(unitsWagered)}u staked</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Bankroll</div>
        <div class="metric-value">${fmtNum(bankroll)}u</div>
        <div class="metric-sub">Starting from initial stake</div>
      </div>
    </div>

    <div class="summary-blurb">
      SmartPicksGPT ranks bets by expected value using implied probabilities from market lines.
      This dashboard is for experimentation and education only &mdash; not financial advice.
    </div>
  `;
}

/* ===== PICKS TAB ===== */

function renderPicksTab(data) {
  const section = document.getElementById("picks");
  const picks = data.top10 || [];

  if (!picks.length) {
    section.innerHTML = `<p class="muted">No picks loaded for today.</p>`;
    return;
  }

  const cards = picks
    .map((pick, idx) => {
      const rank = idx + 1;
      const match = pick.match || "Unknown match";
      const team = pick.team || "Unknown side";
      const market = pick.market || "h2h";
      const price = pick.price;
      const ev = pick.adj_ev ?? pick.ev ?? 0;
      const why = pick.why || "Model-selected based on implied edge.";
      const eventTime = pick.event_time || "";

      const evLabel = formatEVLabel(ev);
      const evClass = classifyEVBadge(ev);
      const americanOdds = formatAmericanOdds(price);

      return `
        <article class="pick-card">
          <div class="pick-header">
            <div>
              <div class="pick-rank">#${rank}</div>
              <div class="pick-main">${team} <span class="muted">@ ${match}</span></div>
            </div>
            <div class="pick-rank">${market.toUpperCase()}</div>
          </div>

          <div class="pick-match">${eventTime}</div>

          <div class="pick-meta-row">
            <span class="badge badge-sport">${normalizeSport(pick.sport)}</span>
            <span class="badge badge-price">Odds: ${americanOdds}</span>
            <span class="badge ${evClass}">EV: ${evLabel}</span>
          </div>

          <p class="pick-reason">${why}</p>
        </article>
      `;
    })
    .join("");

  section.innerHTML = `
    <div class="section-title">Today’s Top Value Bets</div>
    <div class="picks-grid">
      ${cards}
    </div>
  `;
}

function formatEVLabel(ev) {
  if (typeof ev !== "number" || !Number.isFinite(ev)) return "—";
  // ev is in units currency; interpret as percentage-ish edge if small
  if (Math.abs(ev) < 0.0000001) return "~0%";
  const pct = ev * 100;
  return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
}

function classifyEVBadge(ev) {
  if (typeof ev !== "number" || !Number.isFinite(ev)) return "badge-ev-neutral";
  if (ev > 0.01) return "badge-ev-positive";
  if (ev < -0.01) return "badge-ev-negative";
  return "badge-ev-neutral";
}

function formatAmericanOdds(price) {
  if (typeof price !== "number" || !Number.isFinite(price)) return "—";
  if (price > 0) return `+${price}`;
  return `${price}`;
}

function normalizeSport(sport) {
  if (!sport) return "Unknown";
  const map = {
    basketball_nba: "NBA",
    americanfootball_nfl: "NFL",
    americanfootball_ncaaf: "NCAAF",
    icehockey_nhl: "NHL",
  };
  return map[sport] || sport;
}

/* ===== ANALYTICS TAB ===== */

let bankrollChartInstance = null;
let winrateChartInstance = null;

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
          <canvas id="winrateChart"></canvas>
        </div>
        <div class="small-metrics-grid">
          <div class="small-metric">Wins: ${wins}</div>
          <div class="small-metric">Losses: ${losses}</div>
          <div class="small-metric">Pushes: ${pushes}</div>
          <div class="small-metric">Total Bets: ${perf.total_bets || 0}</div>
        </div>
      </div>
    </div>
  `;

  renderBankrollChart(history);
  renderWinrateChart({ wins, losses, pushes });
}

function renderBankrollChart(history) {
  const ctx = document.getElementById("bankrollChart");
  if (!ctx) return;

  if (!history || !history.length) {
    // Graceful fallback: simple static message over blank chart.
    return;
  }

  const labels = history.map((h) => h.date || "");
  const values = history.map((h) => h.bankroll || 0);

  if (bankrollChartInstance) bankrollChartInstance.destroy();

  bankrollChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Bankroll (u)",
          data: values,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: "#e5e7eb",
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#9ca3af" },
          grid: { color: "rgba(55, 65, 81, 0.5)" },
        },
        y: {
          ticks: { color: "#9ca3af" },
          grid: { color: "rgba(55, 65, 81, 0.5)" },
        },
      },
    },
  });
}

function renderWinrateChart({ wins, losses, pushes }) {
  const ctx = document.getElementById("winrateChart");
  if (!ctx) return;

  const total = wins + losses + pushes;
  if (!total) {
    // No bets yet; don’t render chart.
    return;
  }

  if (winrateChartInstance) winrateChartInstance.destroy();

  winrateChartInstance = new Chart(ctx, {
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
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#e5e7eb",
            boxWidth: 14,
          },
        },
      },
      cutout: "60%",
      responsive: true,
      maintainAspectRatio: false,
    },
  });
}

/* ===== HISTORY TAB ===== */

function renderHistoryTab(data) {
  const section = document.getElementById("history");
  const history = data.history || [];

  if (!history.length) {
    section.innerHTML = `
      <div class="section-title">Bet History</div>
      <p class="muted">
        No bet history available in <code>data/data.json</code> yet.
        Once your script writes a <code>"history"</code> array, it will render here automatically.
      </p>
    `;
    return;
  }

  const rows = history
    .map((bet) => {
      const date = bet.date || bet.event_date || "—";
      const sport = normalizeSport(bet.sport);
      const match = bet.match || "—";
      const market = bet.market || bet.type || "—";
      const team = bet.team || bet.selection || "—";
      const odds = typeof bet.odds === "number" ? formatAmericanOdds(bet.odds) : bet.odds || "—";
      const stake = bet.stake ?? bet.units ?? "—";
      const result = bet.result || "pending";
      const ev = typeof bet.ev === "number" ? bet.ev.toFixed(3) : bet.ev || "—";

      return `
        <tr>
          <td>${date}</td>
          <td>${sport}</td>
          <td>${match}</td>
          <td>${market}</td>
          <td>${team}</td>
          <td>${odds}</td>
          <td>${stake}</td>
          <td>${result}</td>
          <td>${ev}</td>
        </tr>
      `;
    })
    .join("");

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
            <th>Selection</th>
            <th>Odds</th>
            <th>Stake (u)</th>
            <th>Result</th>
            <th>EV</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

/* ===== MISC ===== */

function setLastUpdated() {
  const el = document.getElementById("last-updated");
  if (!el) return;
  const now = new Date();
  el.textContent = `Last update: ${now.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

