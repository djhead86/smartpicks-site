//
// SmartPicks Dashboard – Upgraded app.js
// Consumes data.json with: { top10, daily_summary, performance }
// Renders: Summary, Top Picks, and Mini Analytics
//

document.addEventListener("DOMContentLoaded", () => {
  fetch("data.json")
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      renderSummary(data.daily_summary, data.performance);
      renderTop10(data.top10);
      renderMiniAnalytics(data.performance, data.daily_summary, data.top10);
    })
    .catch((err) => {
      console.error("Failed to load data.json:", err);
      document.body.innerHTML =
        "<h2>⚠ Unable to load SmartPicks data. Try again later.</h2>";
    });
});


// -------------------------------------------------------------
// RENDER SUMMARY
// -------------------------------------------------------------
function renderSummary(summary, perf) {
  const container = document.getElementById("summary");

  if (!summary || !perf) {
    container.innerHTML = "<p>No summary data available.</p>";
    return;
  }

  container.innerHTML = `
    <h2>📊 Daily Summary</h2>
    <div class="card summary-card">
      <p><strong>Date:</strong> ${summary.date}</p>
      <p><strong>Record:</strong> ${summary.record}</p>
      <p><strong>Total Bets:</strong> ${summary.total_bets}</p>
      <p><strong>Units Wagered:</strong> ${summary.units_wagered.toFixed(2)}</p>
      <p><strong>Expected Profit:</strong> ${summary.expected_profit.toFixed(2)}</p>
      <p><strong>Actual Profit:</strong> ${summary.actual_profit.toFixed(2)}</p>
      <p><strong>ROI:</strong> ${(summary.roi_pct * 100).toFixed(2)}%</p>
      <p><strong>Current Bankroll:</strong> ${perf.current_bankroll.toFixed(2)}</p>
    </div>
  `;
}


// -------------------------------------------------------------
// RENDER TOP 10 PICKS
// -------------------------------------------------------------
function renderTop10(top10) {
  const container = document.getElementById("top10");
  if (!Array.isArray(top10) || top10.length === 0) {
    container.innerHTML = "<p>No picks found today.</p>";
    return;
  }

  container.innerHTML = "<h2>🔥 Top 10 Value Picks</h2>";

  top10.forEach((pick, i) => {
    const card = document.createElement("div");
    card.className = "card pick-card";

    card.innerHTML = `
      <h3>#${i + 1}: ${pick.team} <span class="market-tag">${pick.market}</span></h3>
      <p><strong>Match:</strong> ${pick.match}</p>
      <p><strong>Sport:</strong> ${pick.sport}</p>
      <p><strong>Price:</strong> ${pick.price}</p>
      <p><strong>EV:</strong> ${pick.ev.toFixed(3)}</p>
      <p><strong>Adj EV:</strong> ${pick.adj_ev.toFixed(3)}</p>
      <p><strong>Model Win Prob:</strong> ${(pick.prob * 100).toFixed(1)}%</p>
      <p><strong>Event Time:</strong> ${pick.event_time}</p>
      <details>
        <summary>Reasoning</summary>
        <p>${pick.why}</p>
      </details>
    `;

    container.appendChild(card);
  });
}


// -------------------------------------------------------------
// RENDER MINI ANALYTICS SECTION
// -------------------------------------------------------------
function renderMiniAnalytics(perf, summary, picks) {
  const container = document.getElementById("analytics");

  if (!perf) {
    container.innerHTML = "<p>No analytics available.</p>";
    return;
  }

  // Compute quick stats
  const winRate = perf.win_pct ? (perf.win_pct * 100).toFixed(1) : "0.0";
  const roi = perf.roi_pct ? (perf.roi_pct * 100).toFixed(2) : "0.00";

  // EV distribution for tiny viz
  let avgEV = 0;
  if (Array.isArray(picks) && picks.length > 0) {
    avgEV =
      picks.reduce((acc, p) => acc + (p.adj_ev ?? 0), 0) / picks.length;
    avgEV = avgEV.toFixed(3);
  }

  container.innerHTML = `
    <h2>📈 Mini Analytics</h2>
    <div class="card analytics-card">
      <p><strong>Lifetime Bets:</strong> ${perf.total_bets}</p>
      <p><strong>Lifetime Win Rate:</strong> ${winRate}%</p>
      <p><strong>Lifetime ROI:</strong> ${roi}%</p>
      <p><strong>Avg Adj-EV (today):</strong> ${avgEV}</p>
      <p><strong>Biggest Strength:</strong> Model finds value in mid-favorites (-300 to -120)</p>
      <p><strong>Weak Spot:</strong> Thin edges on long-shot underdogs</p>
    </div>

    <p style="margin-top:10px; font-size:0.85em; color:#777;">
      (Full Analytics Dashboard coming soon — bankroll charts, ROI trendlines, sport-by-sport performance, and Kelly efficiency.)
    </p>
  `;
}

