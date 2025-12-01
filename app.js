fetch('data/data.json')
  .then(r => r.json())
  .then(json => {

    // Your picks are inside json.top10
    const data = json.top10;

    const container = document.getElementById('picks');
    if (!container) {
      console.error("ERROR: #picks container missing in HTML.");
      return;
    }

    container.innerHTML = ""; // Clear stale content

    data.forEach((pick, index) => {
      const el = document.createElement('div');
      el.className = 'pick';

      el.innerHTML = `
        <h3>#${index + 1}: ${pick.team} (${pick.market})</h3>

        <p><strong>Match:</strong> ${pick.match}</p>
        <p><strong>Price:</strong> ${pick.price}</p>
        <p><strong>EV:</strong> ${pick.ev}</p>

        <p><strong>Explanation:</strong> ${pick.explanation || "No explanation available"}</p>
      `;

      container.appendChild(el);
    });
  })
  .catch(err => {
    console.error("Failed to load JSON:", err);
  });

