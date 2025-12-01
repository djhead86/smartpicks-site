console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";

// DOM references
const picksBox = document.getElementById("picks-container");
const summaryBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");

async function loadSmartPicks() {
    try {
        const response = await fetch(DATA_URL);
        const data = await response.json();

        renderDailySummary(data.daily_summary);
        renderPicks(data.top10);
        renderPerformance(data.performance);
        renderHistory(data.history);

    } catch (err) {
        console.error(err);
        picksBox.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}

// ----------------------------
// RENDER DAILY SUMMARY
// ----------------------------
function renderDailySummary(summary) {
    if (!summary) summary = {};

    const totalBets = Number(summary.total_bets || 0);
    const wins = Number(summary.wins || 0);
    const losses = Number(summary.losses || 0);
    const pushes = Number(summary.pushes || 0);
    const winRate = Number(summary.win_rate || 0);
    const bankroll = Number(summary.bankroll || 0);
    const roi = Number(summary.roi || 0);

    document.getElementById("total-bets").innerHTML = totalBets.toFixed(0);
    document.getElementById("wins").innerHTML = wins.toFixed(0);
    document.getElementById("losses").innerHTML = losses.toFixed(0);
    document.getElementById("pushes").innerHTML = pushes.toFixed(0);
    document.getElementById("win-rate").innerHTML = winRate.toFixed(2) + "%";
    document.getElementById("bankroll").innerHTML = "$" + bankroll.toFixed(2);
    document.getElementById("roi").innerHTML = roi.toFixed(2) + "%";
}

// ----------------------------
// RENDER TOP 10 PICKS
// ----------------------------
function renderPicks(picks) {
    if (!picks || picks.length === 0) {
        picksBox.innerHTML = "<p>No picks available.</p>";
        return;
    }

    let html = "";

    picks.forEach(p => {
        const prob = p.prob ? (p.prob * 100).toFixed(1) : "--";
        const ev = p.ev ? (p.ev * 100).toFixed(2) : "0.00";
        const kelly = p.kelly ? (p.kelly * 100).toFixed(2) : "0.00";

        html += `
            <div class="pick-card">
                <h3>${p.match}</h3>
                <p><strong>Sport:</strong> ${p.sport}</p>
                <p><strong>Team:</strong> ${p.team}</p>
                <p><strong>Market:</strong> ${p.market}</p>
                <p><strong>Price:</strong> ${p.price}</p>
                <p><strong>Probability:</strong> ${prob}%</p>
                <p><strong>EV:</strong> ${ev}%</p>
                <p><strong>Kelly %:</strong> ${kelly}%</p>
                <p><em>${p.why || ""}</em></p>
            </div>
        `;
    });

    picksBox.innerHTML = html;
}

// ----------------------------
// RENDER PERFORMANCE
// ----------------------------
function renderPerformance(p) {
    if (!p) {
        perfBox.innerHTML = "<p>No performance data.</p>";
        return;
    }

    perfBox.innerHTML = `
        <p><strong>Total Bets:</strong> ${p.total_bets}</p>
        <p><strong>Wins:</strong> ${p.wins}</p>
        <p><strong>Losses:</strong> ${p.losses}</p>
        <p><strong>Pushes:</strong> ${p.pushes}</p>
        <p><strong>Units Wagered:</strong> ${p.units_wagered}</p>
        <p><strong>Expected Profit:</strong> ${p.expected_profit.toFixed(2)}</p>
        <p><strong>Actual Profit:</strong> ${p.actual_profit.toFixed(2)}</p>
        <p><strong>ROI:</strong> ${(p.roi_pct * 100).toFixed(1)}%</p>
        <p><strong>Current Bankroll:</strong> ${p.current_bankroll.toFixed(2)}</p>
    `;
}
// ----------------------------
// RENDER HISTORY (last 50 bets)
// ----------------------------
function renderHistory(history) {
    const historyBox = document.getElementById("history-box");
    if (!history || history.length === 0) {
        historyBox.innerHTML = "<p>No history available.</p>";
        return;
    }

    let html = "<table class='history-table'><tr>"
             + "<th>Date</th><th>Sport</th><th>Match</th><th>Team</th>"
             + "<th>Market</th><th>Price</th><th>Stake</th>"
             + "<th>Result</th><th>Profit</th><th>Bankroll</th>"
             + "</tr>";

    history.forEach(r => {
        html += `<tr>
            <td>${r.date}</td>
            <td>${r.sport}</td>
            <td>${r.match}</td>
            <td>${r.team}</td>
            <td>${r.market}</td>
            <td>${r.price}</td>
            <td>${r.stake}</td>
            <td>${r.result}</td>
            <td>${r.profit}</td>
            <td>${r.bankroll_after}</td>
        </tr>`;
    });

    html += "</table>";
    historyBox.innerHTML = html;
}

loadSmartPicks();
