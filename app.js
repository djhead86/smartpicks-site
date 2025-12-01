console.log("SmartPicksGPT frontend initialized.");

// Paths
const DATA_URL = "data/data.json";

// DOM references
const picksGrid = document.getElementById("picks-grid");

const todayBets     = document.getElementById("today-bets");
const todayRecord   = document.getElementById("today-record");
const todayUnits    = document.getElementById("today-units");
const todayProfit   = document.getElementById("today-profit");

const overallBankroll = document.getElementById("overall-bankroll");
const overallPL       = document.getElementById("overall-pl");
const overallLastDay  = document.getElementById("overall-lastday");

const bankrollSummary = document.getElementById("bankroll-summary");
const lastUpdated     = document.getElementById("last-updated");

let chartInstance = null;

// Main loader
async function loadSmartPicks() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) throw new Error("Failed to load data.json");

        const data = await response.json();
        console.log("Loaded SmartPicks data:", data);

        renderTodayStats(data.daily_summary);
        renderOverallStats(data.performance);
        renderPicks(data.top10);

        renderBankrollChart(data.performance);
        renderBankrollSummary(data.performance);

        lastUpdated.innerText = "Last update: " + new Date().toLocaleString();

    } catch (err) {
        console.error(err);
        picksGrid.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}

// ---------------------------
// TODAY STATS
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

    picks.forEach((p, idx) => {
        const card = document.createElement("div");
        card.className = "pick-card";

        card.innerHTML = `
            <div class="pick-rank">#${idx + 1}</div>
            <div class="pick-match">${p.match}</div>
            <div class="pick-team">${p.team}</div>
            <div class="pick-market">Market: ${p.market}</div>
            <div class="pick-price">Price: ${p.price}</div>
            <div class="pick-prob">Prob: ${(p.prob * 100).toFixed(1)}%</div>
            <div class="pick-ev">Adj EV: ${p.adj_ev.toFixed(3)}</div>
            <div class="pick-kelly">Kelly: ${p.kelly.toFixed(3)}</div>
            <div class="pick-why">${p.why}</div>
        `;

        picksGrid.appendChild(card);
    });
}

// ---------------------------
// BANKROLL SUMMARY
// ---------------------------
function renderBankrollSummary(p) {
    bankrollSummary.innerHTML = `
        <p><strong>Total Bets:</strong> ${p.total_bets}</p>
        <p><strong>P/L:</strong> ${p.actual_profit.toFixed(2)}u</p>
        <p><strong>ROI:</strong> ${p.roi_pct.toFixed(2)}%</p>
        <p><strong>Bankroll:</strong> ${p.current_bankroll.toFixed(2)}u</p>
    `;
}

// ---------------------------
// BANKROLL CHART
// ---------------------------
function renderBankrollChart(perf) {
    const ctx = document.getElementById("bankrollChart").getContext("2d");

    const x = perf.bankroll_history.map((_, i) => i + 1);
    const y = perf.bankroll_history;

    if (chartInstance) chartInstance.destroy();

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

// Start the dashboard
loadSmartPicks();
