//
// SmartPicks Site – Correct Data Loader
//

async function loadJSON(path) {
    try {
        const res = await fetch(path);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error("Failed loading:", path, e);
        return null;
    }
}

async function loadData() {
    const daily = await loadJSON("data/daily_summary.json");
    const performance = await loadJSON("data/performance.json");
    const picks = await loadJSON("data/top10.json");

    if (!daily || !performance || !picks) {
        document.getElementById("status").innerText =
            "Failed to load SmartPicks data. Check JSON paths.";
        return null;
    }

    return { daily, performance, picks };
}

//
// Render functions
//

function renderPicks(list) {
    const container = document.getElementById("picks");
    container.innerHTML = "";

    list.forEach((p, i) => {
        const card = document.createElement("div");
        card.className = "pick-card";
        card.innerHTML = `
            <h3>#${i + 1}: ${p.team} (${p.market})</h3>
            <p><b>Match:</b> ${p.match}</p>
            <p><b>Price:</b> ${p.price}</p>
            <p><b>Prob:</b> ${(p.prob * 100).toFixed(1)}%</p>
            <p><b>EV:</b> ${p.ev.toFixed(3)}</p>
        `;
        container.appendChild(card);
    });
}

function renderDaily(daily, performance) {
    document.getElementById("today_bets").innerText = daily.total_bets;
    document.getElementById("today_record").innerText = daily.record;
    document.getElementById("today_units").innerText = daily.units_wagered;
    document.getElementById("today_profit").innerText = daily.actual_profit;

    document.getElementById("all_bankroll").innerText =
        performance.current_bankroll;
    document.getElementById("lifetime_pl").innerText =
        performance.lifetime_pl;
    document.getElementById("last_day").innerText =
        performance.last_day_profit;
}

function renderBankrollChart(performance) {
    const ctx = document.getElementById("bankrollChart");

    if (!performance.bankroll_history) return;

    const labels = performance.bankroll_history.map(x => x.date);
    const values = performance.bankroll_history.map(x => x.bankroll);

    new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Bankroll",
                    data: values,
                    borderColor: "#4ade80",
                    backgroundColor: "rgba(74, 222, 128, 0.25)",
                    tension: 0.2
                }
            ]
        },
        options: {
            scales: {
                y: { beginAtZero: false }
            }
        }
    });
}

//
// MAIN
//
async function main() {
    const data = await loadData();
    if (!data) return;

    const { daily, performance, picks } = data;

    renderPicks(picks);
    renderDaily(daily, performance);
    renderBankrollChart(performance);

    document.getElementById("status").innerText =
        "SmartPicks data loaded successfully ✔";
}

main();

