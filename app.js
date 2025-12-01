// ---------------------------
// CONFIDENCE METER FUNCTIONS
// ---------------------------

// Convert American odds → implied probability
function impliedProbability(odds) {
  const o = Number(odds);
  if (isNaN(o)) return null;

  if (o < 0) return Math.abs(o) / (Math.abs(o) + 100);
  return 100 / (o + 100);
}

// Compute confidence 0–100 based on price movement (simple version)
function computeConfidence(pick) {
  const latestProb = impliedProbability(pick.price);
  if (!latestProb) return 50;
  return Math.round(latestProb * 100);
}

// Choose theme based on confidence level
function getConfidenceTheme(score) {
  if (score < 40) return { theme: "low", label: "Cooling Off" };
  if (score < 70) return { theme: "neutral", label: "Neutral Trend" };
  if (score < 90) return { theme: "high", label: "Trending Up" };
  return { theme: "hyper", label: "Sharp Action" };
}

// Build the confidence meter UI block
function attachConfidenceMeter(card, pick) {
  const score = computeConfidence(pick);
  const { theme, label } = getConfidenceTheme(score);

  const wrapper = document.createElement("div");
  wrapper.className = `confidence-wrapper meter-${theme}`;

  const angle = (score / 100) * 180;

  wrapper.innerHTML = `
    <div class="confidence-meter">
      <div class="confidence-arc" style="--confidence-angle: ${angle}deg"></div>
      <div class="confidence-center">
        <span class="confidence-value">${score}%</span>
      </div>
    </div>
    <div class="confidence-label">${label}</div>
  `;

  card.appendChild(wrapper);
}

// ---------------------------
// RENDER PICKS INTO DASHBOARD UI
// ---------------------------

fetch("data.json")
  .then(r => r.json())
  .then(data => {

    const container = document.getElementById("picks");

    data.forEach(pick => {

      // Create unified SmartPicks dashboard card
      const card = document.createElement("div");
      card.className = "pick-card";

      const evClass =
        pick.ev > 0.05 ? "ev-strong-positive" :
        pick.ev > 0     ? "ev-mild-positive" :
        pick.ev === 0   ? "ev-neutral" :
                          "ev-negative";

      card.innerHTML = `
        <div class="pick-header">
          <div class="pick-title">#${pick.rank}: ${pick.team}</div>
          <div class="pick-badge">${pick.market}</div>
        </div>

        <div class="pick-meta"><strong>Match:</strong> ${pick.match}</div>
        <div class="pick-odds"><strong>Price:</strong> ${pick.price}</div>

        <div class="pick-footer">
          <div class="pick-ev-pill ${evClass}">
            <span>EV</span> ${pick.ev}
          </div>
        </div>

        <div class="pick-meta">${pick.reason}</div>
      `;

      // ⭐ Add the confidence meter ⭐
      attachConfidenceMeter(card, pick);

      container.appendChild(card);
    });
  });

