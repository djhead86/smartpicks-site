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
function renderDailySummary(s) {
    if (!s) {
        dailyBox.innerHTML = "<p>No summary available.</p>";
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

    html += `</tbody></table>`;
    picksContainer.innerHTML = html;
}

// ---------------------------
// RENDER: Performance
// ---------------------------
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
        <p><strong>Units Wagered:</strong> ${p.units_wagered.toFixed(2)}u</p>
        <p><strong>Expected Profit:</strong> ${p.expected_profit.toFixed(2)}u</p>
        <p><strong>Actual Profit:</strong> ${p.actual_profit.toFixed(2)}u</p>
        <p><strong>ROI:</strong> ${p.roi_pct.toFixed(2)}%</p>
        <p><strong>Current Bankroll:</strong> ${p.current_bankroll.toFixed(2)}u</p>
    `;
}

// Start
loadSmartPicks();

