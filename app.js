///////////////////////////////////////////////////////////////////////////////
// SmartPicksGPT – Fully Regenerated Application Script
// Dynamic Rendering • Confidence Meter • Search • Clean Dashboard Logic
///////////////////////////////////////////////////////////////////////////////


// ---------------------------------------------------------------------------
//  CONFIDENCE METER LOGIC
// ---------------------------------------------------------------------------

// Convert American odds to implied probability
function impliedProbability(odds) {
  const o = Number(odds);
  if (isNaN(o)) return null;
  if (o < 0) return Math.abs(o) / (Math.abs(o) + 100);
  return 100 / (o + 100);
}

// Compute a 0–100 confidence score
function computeConfidence(pick) {
  const prob = impliedProbability(pick.price);
  if (prob == null) return 50;
  return Math.round(prob * 100);
}

// Map score to a visual style + text label
function getConfidenceTheme(score) {
  if (score < 40) return { theme: "low", label: "Cooling Off" };
  if (score < 70) return { theme: "neutral", label: "Neutral Trend" };
  if (score < 90) return { theme: "high", label: "Trending Up" };
  return { theme: "hyper", label: "Sharp Action" };
}

// Build and append the confidence meter into a card
function attachConfidenceMeter(card, pick) {
  const score = computeConfidence(pick);
  const { theme, label } = getConfidenceTheme(score);
  const angle = (score / 100) * 180;

  const wrapper = document.createElement("div");
  wrapper.className = `confidence-wrapper meter-${theme}`;

  wrapper.innerHTML = `
    <div class="confidence-meter">
      <div class="confidence-arc" style="--confidence-angle:${angle}deg"></div>
      <div class="confidence-center">
        <span class="confidence-value">${score}%</span>
      </div>
    </div>
    <div class="confidence-label">${label}</div>
  `;

  card.appendChild(wrapper);
}


// ---------------------------------------------------------------------------
//  CARD COMPONENT BUILDER
// ---------------------------------------------------------------------------

function createPickCard(pick) {
  const card = document.createElement("article");
  card.className = "pick-card";

  // Determine EV styling class
  let evClass = "ev-neutral";
  if (pick.ev > 0.05) evClass = "ev-strong-positive";
  else if (pick.ev > 0) evClass = "ev-mild-positive";
  else if (pick.ev < 0) evClass = "ev-negative";

  // Build card inner HTML
  card.innerHTML = `
    <div class="pick-header">
      <div>
        <div class="pick-title">#${pick.rank} – ${pick.team}</div>
        <div class="pick-meta">
          ${pick.match}<br>
          <span class="pick-badge">${pick.market}</span>
        </div>
      </div>
    </div>

    <div class="pick-footer">
      <div><strong>Odds:</strong> ${pick.price}</div>
      <div class="pick-ev-pill ${evClass}">
        <span>${pick.ev >= 0 ? "Positive EV" : "Negative EV"}</span>
        <strong>${(pick.ev * 100).toFixed(2)}%</strong>
      </div>
    </div>

    <div class="pick-reason">
      ${pick.reason}
    </div>
  `;

  // Add confidence meter section
  attachConfidenceMeter(card, pick);

  return card;
}


// ---------------------------------------------------------------------------
//  RENDER ALL PICKS
// ---------------------------------------------------------------------------

function renderPicks(picks) {
  const container = document.getElementById("picks-container");
  container.innerHTML = "";

  picks.forEach(pick => {
    const card = createPickCard(pick);
    container.appendChild(card);
  });

  // Update “X picks loaded” label
  const label = document.getElementById("picks-count-label");
  if (label) label.textContent = `${picks.length} picks loaded`;
}


// ---------------------------------------------------------------------------
//  SEARCH / FILTER
// ---------------------------------------------------------------------------

function setupSearch(picks) {
  const input = document.getElementById("picks-search");
  if (!input) return;

  input.addEventListener("input", () => {
    const q = input.value.toLowerCase();

    const filtered = picks.filter(p =>
      p.team.toLowerCase().includes(q) ||
      p.match.toLowerCase().includes(q) ||
      p.market.toLowerCase().includes(q)
    );

    renderPicks(filtered);
  });
}


// ---------------------------------------------------------------------------
//  LAST UPDATED TIME
// ---------------------------------------------------------------------------

function updateLastUpdated() {
  const el = document.getElementById("last-updated-value");
  if (!el) return;
  el.textContent = new Date().toISOString();
}


// ---------------------------------------------------------------------------
//  MAIN INITIALIZATION
// ---------------------------------------------------------------------------

fetch("data.json")
  .then(r => r.json())
  .then(picks => {
    renderPicks(picks);    // Build cards dynamically
    setupSearch(picks);    // Activate search
    updateLastUpdated();   // Timestamp
  })
  .catch(err => {
    console.error("Failed to load picks:", err);
  });

