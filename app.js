console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";

const picksContainer = document.getElementById("picks-container");
const dailyBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");

async function loadSmartPicks() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) throw new Error("Failed to load data.json");

        const data = await response.json();
        console.log("Loaded SmartPicks data:", data);

        // ❌ REMOVE THESE — they break your dashboard
        // renderDailySummary(data.daily_summary);
        // renderPerformance(data.performance);

        // ✅ USE ONLY WHAT EXISTS
        renderPicks(data);
        renderSystemPerformance(data);

    } catch (err) {
        console.error(err);
        picksContainer.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
    }
}
