fetch('data/data.json')
  .then(r => r.json())
  .then(json => {

    const picks = json.top10;
    const container = document.getElementById('picks');

    // Update timestamp
    document.getElementById("last-updated").textContent =
        "Updated: " + new Date().toLocaleString();

    container.innerHTML = "";

    picks.forEach((pick, index) => {

      const evPercent = Math.min(Math.max(parseFloat(pick.ev) * 100, 0), 100).toFixed(1);

      const el = document.createElement('div');
      el.className = 'pick';

      el.innerHTML = `
        <h3>#${index + 1} — ${pick.team} (${pick.market.toUpperCase()})</h3>

        <p><strong>Match:</strong> ${pick.match}</p>
        <p><strong>Line:</strong> ${pick.price}</p>
        <p><strong>EV:</strong> ${pick.ev}</p>

        <div class="ev-bar">
          <div class="ev-bar-fill" style="width: ${evPercent}%;"></div>
        </div>

        <p class="explanation">${pick.explanation}</p>
      `;

      container.appendChild(el);
    });
  })
  .catch(err => {
    console.error("Failed to load data.json:", err);
  });

