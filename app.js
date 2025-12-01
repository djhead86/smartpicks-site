console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";

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

        // data is a FLAT ARRAY
        renderDailySummary(data);
        renderPicks(data);
        renderPerformance(data);

    } catch (err) {
        console.error(err);
        picksBox.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}

// ----------------------------
// RENDERERS
// ----------------------------

// DAILY SUMMARY
function renderDailySummary(data) {
    const wins = data.filter(b => b.outcome === "win").length;
    const losses = data.filter(b => b.outcome === "loss").length;
    const pending = data.filter(b => b.outcome === "pending").length;

    summaryBox.innerHTML = `
        <p><strong>Total Bets:</strong> ${data.length}</p>
        <p><strong>Wins:</strong> ${wins}</p>
        <p><strong>Losses:</strong> ${losses}</p>
        <p><strong>Pending:</strong> ${pending}</p>
    `;
}

// TOP PICKS
function renderPicks(data) {
    let html = "";

    data.forEach(p => {
        html += `
            <div class="pick-card">
                <h3>${p.sport} · ${p.team}</h3>
                <p><strong>Event:</strong> ${p.event}</p>
                <p><strong>Market:</strong> ${p.market}</p>
                <p><strong>Odds:</strong> ${p.odds}</p>
                <p><strong>EV:</strong> ${(p.ev * 100).toFixed(1)}%</p>
                <p><strong>Confidence:</strong> ${(p.confidence * 100).toFixed(1)}%</p>
            </div>
        `;
    });

    picksBox.innerHTML = html;
}

// SYSTEM PERFORMANCE
function renderPerformance(data) {
    const wins = data.filter(b => b.outcome === "win").length;
    const losses = data.filter(b => b.outcome === "loss").length;

    const winRate = wins + losses === 0 ? 0 : (wins / (wins + losses)) * 100;

    perfBox.innerHTML = `
        <p><strong>Win Rate:</strong> ${winRate.toFixed(1)}%</p>
        <p><strong>Total Wins:</strong> ${wins}</p>
        <p><strong>Total Losses:</strong> ${losses}</p>
    `;
}

// KICKSTART
loadSmartPicks();
