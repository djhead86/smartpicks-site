console.log("SmartPicksGPT frontend initialized.");

// Paths
const DATA_URL = "data/data.json";

// DOM references
const picksContainer = document.getElementById("picks-container");
const dailyBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");

// Main loader
async function loadSmartPicks() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) throw new Error("Failed to load data.json");

        const data = await response.json();
        console.log("Loaded SmartPicks data:", data);

        renderDailySummary(data.daily_summary);
        renderPicks(data.top10);
        renderPerformance(data.performance);
    } catch (err) {
        console.error(err);
        picksContainer.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}

// ---------------------------
// RENDER: Daily Summary
// ---------------------------
function renderTodayStats(s) {
    if (!s) return;

    todayBets.innerText   = s.total_bets;
    todayRecord.innerText = s.record + ` (${s.win_pct.toFixed(1)}%)`;
    todayUnits.innerText  = s.units_wagered.toFixed(2) + "u";
    todayProfit.innerText = s.actual_profit.toFixed(2) + "u";
}


// ---------------------------
// OVERALL STATS
// ---------------------------
function renderOverallStats(p) {
    if (!p) return;

    overallBankroll.innerText = p.current_bankroll.toFixed(2) + "u";
    overallPL.innerText       = p.actual_profit.toFixed(2) + "u";

    overallLastDay.innerText = p.bankroll_history.length
        ? p.bankroll_history[p.bankroll_history.length - 1].toFixed(2)
        : "--";
}

// ---------------------------
// PICKS GRID
// ---------------------------
function renderPicks(picks) {
    picksGrid.innerHTML = ""; // clear old picks

    if (!picks || picks.length === 0) {
        picksGrid.innerHTML = "<p>No picks today.</p>";
        return;
    }

    dailyBox.innerHTML = `
        <p><strong>Date:</strong> ${s.date}</p>
        <p><strong>Total Bets:</strong> ${s.total_bets}</p>
        <p><strong>Record:</strong> ${s.record} (${s.win_pct.toFixed(1)}%)</p>
        <p><strong>Units Wagered:</strong> ${s.units_wagered.toFixed(2)}u</p>
        <p><strong>Expected Profit:</strong> ${s.expected_profit.toFixed(2)}u</p>
        <p><strong>Actual Profit:</strong> ${s.actual_profit.toFixed(2)}u</p>
        <p><strong>ROI:</strong> ${s.roi_pct.toFixed(2)}%</p>
        <p><strong>Bankroll:</strong> ${s.bankroll.toFixed(2)}u</p>
    `;
}

// ---------------------------
// RENDER: Picks
// ---------------------------
function renderPicks(picks) {
    if (!picks || picks.length === 0) {
        picksContainer.innerHTML = "<p>No picks available.</p>";
        return;
    }

    let html = `
        <table class="picks-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Match</th>
                    <th>Team</th>
                    <th>Market</th>
                    <th>Price</th>
                    <th>Prob</th>
                    <th>Adj EV</th>
                    <th>Kelly</th>
                    <th>Why</th>
                </tr>
            </thead>
            <tbody>
    `;

    picks.forEach((p, i) => {
        html += `
        <tr>
            <td>${i + 1}</td>
            <td>${p.match}</td>
            <td>${p.team}</td>
            <td>${p.market}</td>
            <td>${p.price}</td>
            <td>${(p.prob * 100).toFixed(1)}%</td>
            <td>${p.adj_ev.toFixed(3)}</td>
            <td>${p.kelly.toFixed(3)}</td>
            <td>${p.why}</td>
        </tr>
        `;
    });

    chartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: x,
            datasets: [
                {
                    label: "Bankroll (units)",
                    data: y,
                    borderColor: "#4CAF50",
                    backgroundColor: "rgba(76, 175, 80, 0.2)",
                    borderWidth: 2,
                    tension: 0.2
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: "Units"
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: "Bet Number"
                    }
                }
            }
        }
    });
}
function renderDailySummary(data) {
  const elem = document.getElementById("daily-summary");
  if (!elem) return;

  let total = data.length;
  let wins = data.filter(b => b.outcome === "win").length;
  let losses = data.filter(b => b.outcome === "loss").length;
  let pending = data.filter(b => b.outcome === "pending").length;

  elem.innerHTML = `
    <div class="summary-card">
      <h3>Daily Summary</h3>
      <p><strong>Total Bets:</strong> ${total}</p>
      <p><strong>Wins:</strong> ${wins}</p>
      <p><strong>Losses:</strong> ${losses}</p>
      <p><strong>Pending:</strong> ${pending}</p>
    </div>
  `;
}

// Start the dashboard
loadSmartPicks();

