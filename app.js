// SmartPicksGPT Dashboard app.js
// Consumes data.json with { top10, daily_summary, performance }
// Renders Summary, Top Picks, and Analytics charts using Chart.js

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadData();
});

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const tabs = document.querySelectorAll(".tab-content");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");
      buttons.forEach((b) => b.classList.remove("active"));
      tabs.forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      const tabEl = document.getElementById(target);
      if (tabEl) tabEl.classList.add("active");
    });
  });
}

function loadData() {
  fetch("data.json")
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const { top10, daily_summary, performance } = data;
      renderSummary(daily_summary, performance);
      renderTop10(top10);
      renderAnalytics(performance, top10);
      updateLastUpdated(performance);
    })
    .catch((err) => {
      console.error("Failed to load data.json:", err);
      const layout = document.querySelector(".layout");
      if (layout) {
        layout.innerHTML =
          "<h2>⚠ Unable to load SmartPicks data. Try again later.</h2>";
      }
    });
}

function updateLastUpdated(performance) {
  const el = document.getElementById("last-updated");
  if (!el) return;
  const now = new Date();
  const ts = now.toLocaleString();
  el.textContent = "Last updated: " + ts;
}

// ---------------- SUMMARY ----------------
function renderSummary(summary, perf) {
  const container = document.getElementById("summary");
  if (!container) return;

  if (!summary || !perf) {
    container.innerHTML = "<p>No summary data available.</p>";
    return;
  }

  const roi = (summary.roi_pct * 100).toFixed(2);
  const winRate = (summary.win_pct * 100).toFixed(1);

  container.innerHTML = `
    <h2>📊 Daily Summary</h2>
    <div class="card summary-card">
      <p><strong>Date:</strong> ${summary.date}</p>
      <p><strong>Record:</strong> ${summary.record} (Win rate: ${winRate}%)</p>
      <p><strong>Total Bets:</strong> ${summary.total_bets}</p>
      <p><strong>Units Wagered:</strong> ${summary.units_wagered.toFixed(2)}</p>
      <p><strong>Expected Profit:</strong> ${summary.expected_profit.toFixed(2)}</p>
      <p><strong>Actual Profit:</strong> ${summary.actual_profit.toFixed(2)}</p>
      <p><strong>Daily ROI:</strong> ${roi}%</p>
      <p><strong>Current Bankroll:</strong> ${perf.current_bankroll.toFixed(2)}</p>
    </div>
  `;
}

// ---------------- TOP 10 ----------------
function renderTop10(top10) {
  const container = document.getElementById("top10");
  if (!container) return;

  if (!Array.isArray(top10) || top10.length === 0) {
    container.innerHTML = "<p>No picks found today.</p>";
    return;
  }

  container.innerHTML = "<h2>🔥 Top 10 Value Picks</h2>";

  top10.forEach((pick, i) => {
    const card = document.createElement("div");
    card.className = "card pick-card";

    const probPct = pick.prob != null ? (pick.prob * 100).toFixed(1) + "%" : "--";
    const ev = pick.ev != null ? pick.ev.toFixed(3) : "0.000";
    const adjEv = pick.adj_ev != null ? pick.adj_ev.toFixed(3) : "0.000";

    card.innerHTML = `
      <h3>#${i + 1}: ${pick.team} <span class="market-tag">${pick.market}</span></h3>
      <div class="pick-meta">
        <span>${pick.sport}</span>
        <span>Price: ${pick.price}</span>
        <span>EV: ${ev}</span>
        <span>Adj EV: ${adjEv}</span>
        <span>Win Prob: ${probPct}</span>
      </div>
      <p><strong>Match:</strong> ${pick.match}</p>
      <p><strong>Event Time:</strong> ${pick.event_time ?? ""}</p>
      <details>
        <summary>Reasoning</summary>
        <p>${pick.why ?? "No explanation available."}</p>
      </details>
    `;

    container.appendChild(card);
  });
}

// ---------------- ANALYTICS (CHARTS) ----------------
let bankrollChart, roiChart, evChart, probOddsChart;

function renderAnalytics(perf, top10) {
  const analyticsSection = document.getElementById("analytics");
  if (!analyticsSection) return;

  if (!perf) {
    analyticsSection.innerHTML = "<p>No analytics data available.</p>";
    return;
  }

  const history = Array.isArray(perf.bankroll_history)
    ? perf.bankroll_history
    : [];

  const ctxBankroll = document.getElementById("bankrollChart");
  const ctxRoi = document.getElementById("roiChart");
  const ctxEv = document.getElementById("evChart");
  const ctxProbOdds = document.getElementById("probOddsChart");

  if (history.length > 0 && ctxBankroll && ctxRoi) {
    const labels = history.map((h) => h.date);
    const bankrolls = history.map((h) => h.bankroll);
    const start = bankrolls[0] || 1;
    const roiSeries = bankrolls.map((b) => ((b - start) / start) * 100);

    if (bankrollChart) bankrollChart.destroy();
    bankrollChart = new Chart(ctxBankroll, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Bankroll",
            data: bankrolls,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { title: { display: true, text: "Date" } },
          y: { title: { display: true, text: "Bankroll (units)" } },
        },
      },
    });

    if (roiChart) roiChart.destroy();
    roiChart = new Chart(ctxRoi, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "ROI %",
            data: roiSeries,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { title: { display: true, text: "Date" } },
          y: {
            title: { display: true, text: "ROI (%)" },
            ticks: { callback: (v) => v + "%" },
          },
        },
      },
    });
  }

  // EV distribution for today's top10
  if (Array.isArray(top10) && top10.length > 0 && ctxEv) {
    const labels = top10.map((p, i) => `#${i + 1}`);
    const evs = top10.map((p) => p.adj_ev ?? p.ev ?? 0);

    if (evChart) evChart.destroy();
    evChart = new Chart(ctxEv, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Adj EV",
            data: evs,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { title: { display: true, text: "Pick Rank" } },
          y: { title: { display: true, text: "Adj EV (units per 1 stake)" } },
        },
      },
    });
  }

  // Win prob vs odds scatter
  if (Array.isArray(top10) && top10.length > 0 && ctxProbOdds) {
    const points = top10.map((p) => ({
      x: p.price,
      y: (p.prob ?? 0) * 100,
    }));

    if (probOddsChart) probOddsChart.destroy();
    probOddsChart = new Chart(ctxProbOdds, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Win Prob vs Odds",
            data: points,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: {
            title: { display: true, text: "American Odds" },
          },
          y: {
            title: { display: true, text: "Model Win Probability (%)" },
          },
        },
      },
    });
  }
}
