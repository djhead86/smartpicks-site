// Load JSON helper
async function loadJSON(path) {
    const resp = await fetch(path);
    return await resp.json();
}

// ===== Load Daily Summary =====
async function loadDailySummary() {
    const s = await loadJSON("data/daily_summary.json");

    document.getElementById("daily-summary-box").innerHTML = `
        <strong>Date:</strong> ${s.date}<br>
        <strong>Total Bets:</strong> ${s.total_bets}<br>
        <strong>Wins-Losses-Pushes:</strong> ${s.record}<br>
        <strong>Units Wagered:</strong> ${s.units_wagered}<br>
        <strong>Actual Profit:</strong> ${s.actual_profit}<br>
        <strong>Daily ROI:</strong> ${s.daily_roi}%<br>
        <strong>Bankroll:</strong> ${s.bankroll_end} u
    `;
}

// ===== Load Top 10 Picks =====
async function loadPicks() {
    const picks = await loadJSON("data/top10.json");
    let html = "";

    picks.forEach((p, i) => {
        html += `
            <div class="pick-card">
                <h3>#${i + 1}: ${p.pick} (${p.market})</h3>
                <p><strong>Match:</strong> ${p.match}</p>
                <p><strong>Sport:</strong> ${p.sport}</p>
                <p><strong>Time:</strong> ${p.time}</p>
                <p><strong>Price:</strong> ${p.price}</p>
                <p><strong>Model Score:</strong> ${p.model_score}</p>
                <p><strong>Payout:</strong> Bet $1 → Win $${p.payout}</p>
                <p><em>${p.why}</em></p>
            </div>
        `;
    });

    document.getElementById("picks-container").innerHTML = html;
}

// ===== Load Performance =====
async function loadPerformance() {
    const p = await loadJSON("data/performance.json");

    document.getElementById("performance-box").innerHTML = `
        <strong>Total Settled Bets:</strong> ${p.total_settled}<br>
        <strong>Units Wagered:</strong> ${p.units_wagered}<br>
        <strong>Actual Profit:</strong> ${p.actual_profit}<br>
        <strong>ROI:</strong> ${p.roi}%<br>
        <strong>Current Bankroll:</strong> ${p.bankroll}
    `;
}

// Run everything
loadDailySummary();
loadPicks();
loadPerformance();

