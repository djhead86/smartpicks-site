console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";

// DOM references
const picksBox = document.getElementById("picks-container");
const summaryBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");

// MAIN LOADER
async function loadSmartPicks() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) throw new Error("Failed to load data.json");

        const data = await response.json();
        console.log("Loaded SmartPicks data:", data);

        // Match your JSON structure exactly:
        renderDailySummary(data.daily_summary);
        renderPicks(data.top10);
        renderPerformance(data.performance);

    } catch (err) {
        console.error(err);
        picksBox.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}

// ----------------------------
// RENDER DAILY SUMMARY
// ----------------------------
function renderDailySummary(ds) {
    if (!ds) {
        summaryBox.innerHTML = "<p>No summary available.</p>";
        return;
    }

    summaryBox.innerHTML = `
        <p><strong>Date:</strong> ${ds.date}</p>
        <p><strong>Total Bets:</strong> ${ds.total_bets}</p>
        <p><strong>Record:</strong> ${ds.record}</p>
        <p><strong>Win %:</strong> ${(ds.win_pct * 100).toFixed(1)}%</p>
        <p><strong>Units Wagered:</strong> ${ds.units_wagered}</p>
        <p><strong>Expected Profit:</strong> ${ds.expected_profit.toFixed(2)}</p>
        <p><strong>Actual Profit:</strong> ${ds.actual_profit.toFixed(2)}</p>
        <p><strong>ROI:</strong> ${(ds.roi_pct * 100).toFixed(1)}%</p>
        <p><strong>Bankroll:</strong> ${ds.bankroll.toFixed(2)}</p>
    `;
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

loadSmartPicks();
