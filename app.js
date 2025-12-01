console.log("SmartPicksGPT frontend initialized.");

// Paths
const DATA_URL = "data/data.json";

// DOM references
const picksContainer = document.getElementById("picks-container");
const dailyBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");
const loadingEl = document.getElementById("loading");
const lastUpdatedEl = document.getElementById("last-updated");

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

        // Set last updated timestamp
        if (lastUpdatedEl) {
            lastUpdatedEl.textContent = "Last Updated: " + new Date().toLocaleString();
        }

        // Hide loading + fade in
        if (loadingEl) loadingEl.style.display = "none";
        document.body.classList.add("loaded");
    } catch (err) {
        console.error(err);
        showError(err);
    }
}
async function loadScores() {
    try {
        const resp = await fetch("https://site.web.api.espn.com/apis/v2/sports/basketball/nba/scoreboard");
        const data = await resp.json();

        const games = data.events || [];

        // Find today's game your model picked
        const modelPick = window.SMARTPICK_MATCH; // We'll store the match name here
        let banner = document.getElementById("score-banner");

        let found = false;

        for (const game of games) {
            const name = game.shortName; // "MEM @ LAL"

            if (!modelPick || !name.includes(modelPick)) continue;

            found = true;

            const status = game.status?.type?.name || "STATUS_UNKNOWN";
            const isFinal = (status === "STATUS_FINAL");

            const home = game.competitions[0].competitors.find(c => c.homeAway === "home");
            const away = game.competitions[0].competitors.find(c => c.homeAway === "away");

            const scoreText = `${away.team.abbreviation} ${away.score} — ${home.team.abbreviation} ${home.score}`;

            banner.style.display = "block";

            if (isFinal) {
                banner.style.borderLeft = "4px solid #4caf50";
                banner.innerHTML = `🏁 Final Score: ${scoreText}`;
            } else {
                banner.style.borderLeft = "4px solid #FFC107";
                banner.innerHTML = `⏳ Live: ${scoreText} (${game.status.type.shortDetail})`;
            }
        }

        if (!found) {
            banner.style.display = "block";
            banner.innerHTML = "No tracked games for today.";
        }

    } catch (err) {
        console.error("Score fetch failed:", err);
    }
}

// Run score updater periodically
setInterval(loadScores, 60000);
setTimeout(loadScores, 2000);

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
        const evClass = p.adj_ev >= 0 ? "ev-positive" : "ev-negative";

        html += `
        <tr class="${evClass}">
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

// ---------------------------
// ERROR HANDLER
// ---------------------------
function showError(err) {
    if (loadingEl) loadingEl.style.display = "none";

    picksContainer.innerHTML = `
        <div class="card error-card">
            <strong>⚠️ Error loading data.json</strong>
            <p>${err.message}</p>
            <p>Check whether:</p>
            <ul>
                <li><code>data/data.json</code> exists in the site folder</li>
                <li>Your deploy script copied it correctly</li>
                <li>The web server (or GitHub Pages) allows fetching that path</li>
            </ul>
        </div>
    `;

    document.body.classList.add("loaded");
}

// Start
loadSmartPicks();
