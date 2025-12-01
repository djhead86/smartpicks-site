async function loadSmartPicks() {
    try {
        const resp = await fetch("data/data.json", { cache: "no-store" });
        if (!resp.ok) {
            throw new Error("Failed to load data.json");
        }
        const data = await resp.json();

        document.getElementById("load-status").innerText = "SmartPicks Loaded.";
        populateTop10(data.top10);
        populateDailySummary(data.daily_summary);
        populatePerformance(data.performance);

    } catch (e) {
        console.error(e);
        document.getElementById("load-status").innerText =
            "⚠️ Failed to load SmartPicks data.json.";
    }
}

// -------------------------
// Top 10 Picks Table
// -------------------------
function populateTop10(top10) {
    const tbody = document.getElementById("top10-body");
    tbody.innerHTML = "";

    top10.forEach((p, idx) => {
        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${idx + 1}</td>
            <td>${p.team}</td>
            <td>${p.market}</td>
            <td>${p.price}</td>
            <td>${(p.prob * 100).toFixed(1)}%</td>
            <td>${p.match}</td>
            <td>${p.event_time}</td>
            <td>${p.why}</td>
        `;

        tbody.appendChild(row);
    });
}

// -------------------------
// Daily Summary
// -------------------------
function populateDailySummary(s) {
    document.getElementById("daily-summary").innerHTML = `
        <p><strong>Date:</strong> ${s.date}</p>
        <p><strong>Total Bets:</strong> ${s.total_bets}</p>
        <p><strong>Record:</strong> ${s.record} (${s.win_pct.toFixed(1)}%)</p>
        <p><strong>Units Wagered:</strong> ${s.units_wagered.toFixed(2)}</p>
        <p><strong>Expected Profit:</strong> ${s.expected_profit.toFixed(2)}</p>
        <p><strong>Actual Profit:</strong> ${s.actual_profit.toFixed(2)}</p>
        <p><strong>ROI:</strong> ${s.roi_pct.toFixed(2)}%</p>
        <p><strong>Bankroll:</strong> ${s.bankroll.toFixed(2)}</p>
    `;
}

// -------------------------
// Performance + Bankroll chart
// -------------------------
function populatePerformance(p) {
    document.getElementById("performance-summary").innerHTML = `
        <p><strong>Total Bets:</strong> ${p.total_bets}</p>
        <p><strong>Wins:</strong> ${p.wins}</p>
        <p><strong>Losses:</strong> ${p.losses}</p>
        <p><strong>Pushes:</strong> ${p.pushes}</p>
        <p><strong>Units Wagered:</strong> ${p.units_wagered.toFixed(2)}</p>
        <p><strong>Expected Profit:</strong> ${p.expected_profit.toFixed(2)}</p>
        <p><strong>Actual Profit:</strong> ${p.actual_profit.toFixed(2)}</p>
        <p><strong>Overall ROI:</strong> ${p.roi_pct.toFixed(2)}%</p>
        <p><strong>Current Bankroll:</strong> ${p.current_bankroll.toFixed(2)}</p>
    `;

    // Build bankroll chart if available
    const chartDiv = document.getElementById("bankroll-chart");
    chartDiv.innerHTML = ""; // reset

    if (p.bankroll_history && p.bankroll_history.length > 0) {
        const canvas = document.createElement("canvas");
        chartDiv.appendChild(canvas);

        const labels = p.bankroll_history.map(x => x.date);
        const values = p.bankroll_history.map(x => x.bankroll);

        new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Bankroll Over Time",
                    data: values,
                    borderColor: "#00ffcc",
                    backgroundColor: "rgba(0,255,200,0.2)",
                    fill: true,
                    tension: 0.2
                }]
            },
            options: {
                scales: {
                    y: { beginAtZero: false }
                },
                plugins: {
                    legend: {
                        labels: { color: "white" }
                    }
                }
            }
        });
    }
}

// Start
loadSmartPicks();

