// ===========================================================
// SmartPicks Frontend (Patched Version)
// ===========================================================

// -----------------------------------------------------------
// Helpers
// -----------------------------------------------------------
function makeBetId(bet) {
  const raw = `${bet.sport}_${bet.match}_${bet.team}_${bet.market}_${bet.event_time}`;
  return raw.replace(/[^a-zA-Z0-9_]/g, "_");
}

function formatOdds(o) {
  return o > 0 ? `+${o}` : `${o}`;
}

// Load manual overrides from localStorage
function loadManualOverrides() {
  const data = localStorage.getItem("manualOverrides");
  return data ? JSON.parse(data) : {};
}

function saveManualOverrides(overrides) {
  localStorage.setItem("manualOverrides", JSON.stringify(overrides));
}

// Download override JSON file
function downloadOverrides() {
  const overrides = loadManualOverrides();
  const blob = new Blob([JSON.stringify(overrides, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "manual_overrides.json";
  a.click();
  URL.revokeObjectURL(url);
}

// -----------------------------------------------------------
// Tab Switching
// -----------------------------------------------------------
document.querySelectorAll(".tab-button").forEach(btn => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;

    document.querySelectorAll(".tab-content").forEach(sec => {
      sec.classList.remove("active");
    });

    document.getElementById(tab).classList.add("active");
  });
});

// -----------------------------------------------------------
// Main Loader
// -----------------------------------------------------------
fetch("data.json")
  .then(r => r.json())
  .then(data => {
    renderSummaryTab(data);
    renderPicksTab(data.picks);
    renderHistoryTab(data.history);
    renderAnalyticsTab(data.analytics);
    updateScoresTicker();
  })
  .catch(err => {
    console.error("Failed to load data.json:", err);
  });

// -----------------------------------------------------------
// SUMMARY TAB
// -----------------------------------------------------------
function renderSummaryTab(data) {
  const summary = document.getElementById("summary");
  summary.innerHTML = `
    <h2>Summary</h2>
    <p>Generated: ${data.generated}</p>
    <p>Total open bets: ${data.picks.length}</p>
    <p>Total historical bets: ${data.history.length}</p>
  `;
}

// -----------------------------------------------------------
// PICKS TAB
// -----------------------------------------------------------
function renderPicksTab(picks) {
  const sec = document.getElementById("picks");
  sec.innerHTML = "";

  if (!picks || picks.length === 0) {
    sec.innerHTML = "<p>No picks available.</p>";
    return;
  }

  picks.forEach(p => {
    const row = document.createElement("div");
    row.className = "pick-card";

    row.innerHTML = `
      <h3>${p.team} (${p.market})</h3>
      <p>${p.match}</p>
      <p>Odds: ${formatOdds(p.price)}</p>
      <p>EV: ${p.ev.toFixed(3)}</p>
      <p>Stake: $${p.recommended_stake.toFixed(2)}</p>
    `;

    sec.appendChild(row);
  });
}

// -----------------------------------------------------------
// HISTORY TAB
// -----------------------------------------------------------
function renderHistoryTab(history) {
  const sec = document.getElementById("history");
  sec.innerHTML = `
    <h2>Bet History</h2>
    <button id="download-overrides" class="export-btn">Download Manual Overrides</button>
    <div id="history-list"></div>
  `;

  document.getElementById("download-overrides")
    .addEventListener("click", downloadOverrides);

  const list = document.getElementById("history-list");
  const overrides = loadManualOverrides();

  history.forEach(bet => {
    const betId = bet.bet_id || makeBetId(bet);
    const appliedResult = overrides[betId] || bet.result;

    const row = document.createElement("div");
    row.className = "bet-row";
    row.setAttribute("data-bet-id", betId);

    row.innerHTML = `
      <div class="bet-info">
        <strong>${bet.team}</strong> (${bet.market}) — ${bet.match}<br>
        <small>${bet.date} | Odds: ${formatOdds(bet.odds)} | Stake: $${bet.stake}</small>
      </div>

      <div class="bet-result result-field">${appliedResult}</div>

      <div class="manual-grade">
        <button class="grade-btn win-btn">WIN</button>
        <button class="grade-btn loss-btn">LOSS</button>
        <button class="grade-btn push-btn">PUSH</button>
      </div>
    `;

    // Attach handlers
    const winBtn = row.querySelector(".win-btn");
    const lossBtn = row.querySelector(".loss-btn");
    const pushBtn = row.querySelector(".push-btn");

    winBtn.addEventListener("click", () => setManual(betId, "WIN", row));
    lossBtn.addEventListener("click", () => setManual(betId, "LOSS", row));
    pushBtn.addEventListener("click", () => setManual(betId, "PUSH", row));

    list.appendChild(row);
  });
}

function setManual(betId, result, row) {
  const overrides = loadManualOverrides();
  overrides[betId] = result;
  saveManualOverrides(overrides);

  // Update UI
  row.querySelector(".result-field").textContent = result;
}

// -----------------------------------------------------------
// ANALYTICS TAB
// -----------------------------------------------------------
function renderAnalyticsTab(analytics) {
  const sec = document.getElementById("analytics");
  sec.innerHTML = `
    <h2>Analytics</h2>

    <div class="analytics-grid">
      <div class="analytic-card">
        <h3>Total Bets</h3>
        <p>${analytics.total_bets}</p>
      </div>

      <div class="analytic-card">
        <h3>Wins</h3>
        <p>${analytics.wins}</p>
      </div>

      <div class="analytic-card">
        <h3>Losses</h3>
        <p>${analytics.losses}</p>
      </div>

      <div class="analytic-card">
        <h3>Pushes</h3>
        <p>${analytics.pushes}</p>
      </div>

      <div class="analytic-card">
        <h3>ROI</h3>
        <p>${(analytics.roi * 100).toFixed(2)}%</p>
      </div>
    </div>

    <h3>ROI by Sport</h3>
    <div id="sport-roi"></div>

    <h3>Bankroll Over Time</h3>
    <canvas id="bankroll-chart" height="80"></canvas>
  `;

  // Render ROI by sport
  const roiSec = document.getElementById("sport-roi");
  for (const [sport, roi] of Object.entries(analytics.sport_roi)) {
    const div = document.createElement("div");
    div.className = "roi-row";
    div.innerHTML = `
      <strong>${sport}</strong>: ${(roi * 100).toFixed(2)}%
    `;
    roiSec.appendChild(div);
  }

  // Render bankroll chart
  renderBankrollChart(analytics.bankroll_history);
}

// -----------------------------------------------------------
// BANKROLL CHART (Chart.js)
// -----------------------------------------------------------
function renderBankrollChart(history) {
  if (!history || history.length === 0) return;

  const ctx = document.getElementById("bankroll-chart").getContext("2d");

  const labels = history.map(h => h.t);
  const values = history.map(h => h.bankroll);

  new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Bankroll",
          data: values,
          fill: false,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      tension: 0.3,
    },
  });
}

// -----------------------------------------------------------
// SCORE TICKER
// -----------------------------------------------------------
function updateScoresTicker() {
  fetch("scores.json")
    .then(r => r.json())
    .then(scores => {
      const ticker = document.getElementById("score-ticker");
      if (!ticker) return;

      if (!scores || scores.length === 0) {
        ticker.textContent = "No scores available.";
        return;
      }

      let text = "";

      scores.forEach(s => {
        if (!s.completed) return;

        const home = s.home_team || "";
        const away = s.away_team || "";
        const homeScore = s.scores?.[0]?.score || "?";
        const awayScore = s.scores?.[1]?.score || "?";

        text += `${away} ${awayScore} — ${home} ${homeScore} | `;
      });

      ticker.textContent = text || "No completed games yet.";
    })
    .catch(() => {
      const ticker = document.getElementById("score-ticker");
      if (ticker) ticker.textContent = "Failed to load scores.";
    });
}

// -----------------------------------------------------------
// END OF FILE
// -----------------------------------------------------------
