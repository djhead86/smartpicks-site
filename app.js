/**
 * SmartPicks Frontend Application
 * Loads data.json and scores.json, renders picks and live scores
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const DATA_URL = 'data.json';
const SCORES_URL = 'scores.json';
const REFRESH_INTERVAL = 60000; // 60 seconds

// ============================================================================
// STATE
// ============================================================================

let appData = null;
let scoresData = null;
let refreshTimer = null;

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('SmartPicks Frontend Initializing...');
    loadData();
    startAutoRefresh();
});

// ============================================================================
// DATA LOADING
// ============================================================================

async function loadData() {
    try {
        // Load picks data
        await loadPicksData();
        
        // Load scores data
        await loadScoresData();
        
        // Render everything
        renderAll();
        
        hideError();
    } catch (error) {
        console.error('Error loading data:', error);
        showError(`Failed to load data: ${error.message}`);
    }
}

async function loadPicksData() {
    try {
        const response = await fetch(DATA_URL);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        appData = await response.json();
        console.log('✓ Loaded picks data:', appData);
    } catch (error) {
        console.error('Failed to load picks data:', error);
        
        // If running on file:// protocol, show helpful error
        if (window.location.protocol === 'file:') {
            throw new Error('Cannot load data via file:// protocol. Please run a local web server (see console for instructions)');
        }
        
        throw error;
    }
}

async function loadScoresData() {
    try {
        const response = await fetch(SCORES_URL);
        
        if (!response.ok) {
            console.warn('Scores data not available');
            scoresData = { games: [] };
            return;
        }
        
        scoresData = await response.json();
        console.log('✓ Loaded scores data:', scoresData);
    } catch (error) {
        console.warn('Failed to load scores data:', error);
        scoresData = { games: [] };
    }
}

// ============================================================================
// RENDERING
// ============================================================================

function renderAll() {
    if (!appData) {
        console.error('No data to render');
        return;
    }
    
    // Render header stats
    renderHeaderStats();
    
    // Render performance summary
    renderPerformance();
    
    // Render parlay card
    renderParlayCard();
    
    // Render placed bets tabs
    renderPlacedBets();
    
    // Render sport pick cards
    renderSportPicks('nba');
    renderSportPicks('nfl');
    renderSportPicks('nhl');
    renderSportPicks('epl');
    renderSportPicks('uefa');
    renderSportPicks('ufc');
    
    // Render live scores ticker
    renderScoresTicker();
    
    // Setup tab functionality
    setupTabs();
}

function renderHeaderStats() {
    // Bankroll
    const bankroll = appData.bankroll || 0;
    document.getElementById('bankroll').textContent = formatCurrency(bankroll);
    
    // Open bets
    const openBets = appData.open_bets || 0;
    document.getElementById('open-bets').textContent = openBets;
    
    // Performance stats
    const perf = appData.performance || {};
    const winRate = (perf.win_rate || 0) * 100;
    const roi = (perf.roi || 0) * 100;
    
    document.getElementById('win-rate').textContent = `${winRate.toFixed(1)}%`;
    document.getElementById('roi').textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`;
    
    // Color code ROI
    const roiElement = document.getElementById('roi');
    roiElement.style.color = roi >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
    
    // Last updated
    const timestamp = appData.generated_at || '';
    document.getElementById('last-updated').textContent = formatTimestamp(timestamp);
}

function renderParlayCard() {
    const container = document.getElementById('parlay-card');
    const parlay = appData.parlay_card;
    
    if (!parlay || !parlay.picks || parlay.picks.length === 0) {
        container.innerHTML = '<div class="no-picks">No parlay available</div>';
        return;
    }
    
    const totalStake = parlay.total_stake || 0;
    const totalEV = parlay.total_ev || 0;
    
    let html = `
        <div class="parlay-header">
            <div class="parlay-stat">
                <span class="label">Legs:</span>
                <span class="value">${parlay.legs}</span>
            </div>
            <div class="parlay-stat">
                <span class="label">Total Stake:</span>
                <span class="value">${formatCurrency(totalStake)}</span>
            </div>
            <div class="parlay-stat">
                <span class="label">Total EV:</span>
                <span class="value ev-positive">${formatCurrency(totalEV)}</span>
            </div>
        </div>
        <div class="parlay-picks">
    `;
    
    parlay.picks.forEach((pick, index) => {
        html += `
            <div class="parlay-pick-item">
                <div class="pick-number">${index + 1}</div>
                <div class="pick-content">
                    <div class="pick-matchup">${escapeHtml(pick.matchup || 'TBD')}</div>
                    <div class="pick-details">
                        <span class="pick-choice">${escapeHtml(pick.pick || 'N/A')}</span>
                        <span class="pick-odds">${formatOdds(pick.odds)}</span>
                        <span class="pick-ev">EV: ${formatCurrency(pick.ev)}</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

function renderSportPicks(sport) {
    const container = document.getElementById(`${sport}-picks`);
    const group = document.getElementById(`${sport}-group`);
    // Map backend sport keys to DOM IDs
    // Map backend sport keys to DOM sections
    const SPORT_KEY_TO_DOM_ID = {
        "basketball_nba": "NBA_picks",
        "americanfootball_nfl": "NFL_picks",
        "icehockey_nhl": "NHL_picks",
        "soccer_epl": "EPL_picks",
        "soccer_uefa_champs_league": "UEFA_picks",
        "mma_mixed_martial_arts": "UFC_picks"
    };

// Render pick cards
for (const sportKey in data.pick_cards) {
    const domId = SPORT_KEY_TO_DOM_ID[sportKey];
    if (!domId) {
        console.warn("No DOM mapping for sport:", sportKey);
        continue;
    }

    const container = document.getElementById(domId);
    if (!container) {
        console.error("Missing DOM element:", domId);
        continue;
    }

    const picks = data.pick_cards[sportKey];

    if (!picks || picks.length === 0) {
        container.innerHTML = `<div class="loading">No picks available.</div>`;
        continue;
    }

    container.innerHTML = picks.map(p => createPickCard(p)).join("");
}


for (const sportKey in data.pick_cards) {
    const domId = SPORT_KEY_TO_DOM_ID[sportKey];
    if (!domId) {
        console.warn("No DOM mapping for sport:", sportKey);
        continue;
    }

    const container = document.getElementById(domId);
    if (!container) {
        console.error("Missing DOM element:", domId);
        continue;
    }

    const picks = data.pick_cards[sportKey];

    if (!picks || picks.length === 0) {
        container.innerHTML = `<div class="loading">No picks available.</div>`;
        continue;
    }

    container.innerHTML = picks.map(p => createPickCard(p)).join("");
}


function createPickCard(pick) {
    const statusClass = getStatusClass(pick.status);
    const resultBadge = pick.result ? `<span class="result-badge result-${pick.result.toLowerCase()}">${pick.result}</span>` : '';
    
    return `
        <div class="pick-card ${statusClass}">
            <div class="pick-header">
                <span class="pick-sport">${escapeHtml(pick.sport || 'N/A')}</span>
                ${resultBadge}
                <span class="pick-status">${escapeHtml(pick.status || 'open')}</span>
            </div>
            
            <div class="pick-matchup">
                ${escapeHtml(pick.matchup || 'TBD')}
            </div>
            
            <div class="pick-choice">
                <strong>${escapeHtml(pick.pick || 'N/A')}</strong>
                <span class="pick-type">(${formatPickType(pick.pick_type)})</span>
            </div>
            
            <div class="pick-metrics">
                <div class="metric">
                    <span class="metric-label">Odds</span>
                    <span class="metric-value">${formatOdds(pick.odds)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">EV</span>
                    <span class="metric-value ev-positive">${formatCurrency(pick.ev)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Smart Score</span>
                    <span class="metric-value">${formatNumber(pick.smart_score, 2)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Stake</span>
                    <span class="metric-value">${formatCurrency(pick.stake)}</span>
                </div>
            </div>
            
            ${pick.profit !== null && pick.profit !== undefined ? `
                <div class="pick-profit ${pick.profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                    Profit: ${formatCurrency(pick.profit, true)}
                </div>
            ` : ''}
            
            <div class="pick-time">
                ${formatGameTime(pick.commence_time)}
            </div>
        </div>
    `;
}

function renderScoresTicker() {
    const ticker = document.getElementById('ticker');
    
    if (!scoresData || !scoresData.games || scoresData.games.length === 0) {
        ticker.innerHTML = '<div class="ticker-item">No live games</div>';
        return;
    }
    
    let html = '';
    scoresData.games.forEach(game => {
        const homeScore = game.home_score !== null ? game.home_score : '-';
        const awayScore = game.away_score !== null ? game.away_score : '-';
        const status = game.status === 'final' ? 'FINAL' : 'LIVE';
        const statusClass = game.status === 'final' ? 'final' : 'live';
        
        html += `
            <div class="ticker-item">
                <span class="ticker-sport">${escapeHtml(game.sport)}</span>
                <span class="ticker-teams">
                    ${escapeHtml(game.away_team)} ${awayScore} @ ${escapeHtml(game.home_team)} ${homeScore}
                </span>
                <span class="ticker-status ${statusClass}">${status}</span>
            </div>
        `;
    });
    
    ticker.innerHTML = html;
}

// ============================================================================
// PERFORMANCE RENDERING
// ============================================================================

function renderPerformance() {
    const container = document.getElementById('performance-grid');
    const perf = appData.performance || {};
    
    if (!perf || perf.total_bets === 0) {
        container.innerHTML = '<div class="no-picks">No performance data yet - place some bets!</div>';
        return;
    }
    
    const winRate = (perf.win_rate || 0) * 100;
    const roi = (perf.roi || 0) * 100;
    const roiClass = roi >= 0 ? 'positive' : 'negative';
    
    const html = `
        <div class="perf-card">
            <div class="perf-label">Total Bets</div>
            <div class="perf-value">${perf.total_bets || 0}</div>
        </div>
        <div class="perf-card">
            <div class="perf-label">Record</div>
            <div class="perf-value">${perf.wins || 0}-${perf.losses || 0}-${perf.pushes || 0}</div>
        </div>
        <div class="perf-card">
            <div class="perf-label">Win Rate</div>
            <div class="perf-value">${winRate.toFixed(1)}%</div>
        </div>
        <div class="perf-card">
            <div class="perf-label">ROI</div>
            <div class="perf-value ${roiClass}">${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%</div>
        </div>
        <div class="perf-card">
            <div class="perf-label">Total Wagered</div>
            <div class="perf-value">${formatCurrency(perf.total_wagered || 0)}</div>
        </div>
        <div class="perf-card">
            <div class="perf-label">Total Profit</div>
            <div class="perf-value ${roiClass}">${formatCurrency(perf.total_profit || 0, true)}</div>
        </div>
    `;
    
    container.innerHTML = html;
}

// ============================================================================
// PLACED BETS RENDERING
// ============================================================================

function renderPlacedBets() {
    const placedBets = appData.placed_bets || {};
    
    // Update counts
    document.getElementById('open-count').textContent = (placedBets.open || []).length;
    document.getElementById('pending-count').textContent = (placedBets.pending || []).length;
    document.getElementById('graded-count').textContent = (placedBets.graded || []).length;
    
    // Render each tab
    renderBetTab('open', placedBets.open || []);
    renderBetTab('pending', placedBets.pending || []);
    renderBetTab('graded', placedBets.graded || []);
}

function renderBetTab(tabName, bets) {
    const container = document.getElementById(`${tabName}-bets-grid`);
    
    if (bets.length === 0) {
        container.innerHTML = `<div class="no-picks">No ${tabName} bets</div>`;
        return;
    }
    
    let html = '';
    bets.forEach(bet => {
        html += createPickCard(bet);
    });
    
    container.innerHTML = html;
}

function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');
            
            // Remove active class from all tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked tab
            button.classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });
}

// ============================================================================
// FORMATTING HELPERS
// ============================================================================

function formatCurrency(value, showSign = false) {
    if (value === null || value === undefined || isNaN(value)) {
        return '$0.00';
    }
    
    const formatted = Math.abs(value).toFixed(2);
    const sign = value >= 0 ? (showSign ? '+' : '') : '-';
    return `${sign}$${formatted}`;
}

function formatOdds(odds) {
    if (!odds || isNaN(odds)) {
        return 'N/A';
    }
    
    return odds > 0 ? `+${odds}` : `${odds}`;
}

function formatNumber(value, decimals = 0) {
    if (value === null || value === undefined || isNaN(value)) {
        return 'N/A';
    }
    
    return value.toFixed(decimals);
}

function formatPickType(type) {
    const types = {
        'h2h': 'Moneyline',
        'spreads': 'Spread',
        'totals': 'Total'
    };
    return types[type] || type;
}

function formatTimestamp(timestamp) {
    if (!timestamp) {
        return '--';
    }
    
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', { 
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
        });
    } catch (error) {
        return '--';
    }
}

function formatGameTime(timestamp) {
    if (!timestamp) {
        return 'Time TBD';
    }
    
    try {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = date - now;
        
        // If game already started
        if (diff < 0) {
            return 'In Progress';
        }
        
        // If game is today
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
        }
        
        // Otherwise show date
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    } catch (error) {
        return 'Time TBD';
    }
}

function getStatusClass(status) {
    const classes = {
        'open': 'status-open',
        'pending': 'status-pending',
        'graded': 'status-graded'
    };
    return classes[status] || '';
}

function escapeHtml(text) {
    if (!text) return '';
    
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ============================================================================
// ERROR HANDLING
// ============================================================================

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');
    
    // Add helpful instruction for file:// protocol
    if (window.location.protocol === 'file:' && message.includes('file://')) {
        message += '\n\n💡 To fix this, run a local web server:\n' +
                  '1. Open Terminal in your project folder\n' +
                  '2. Run: python3 -m http.server 8000\n' +
                  '3. Open: http://localhost:8000';
    }
    
    errorText.textContent = message;
    errorDiv.style.display = 'block';
    
    console.error('Application error:', message);
    
    // Also log instructions to console
    if (window.location.protocol === 'file:') {
        console.warn('⚠️ Running on file:// protocol - JSON files cannot be loaded');
        console.info('💡 Solution: Run a local web server:');
        console.info('   cd /Users/danielpreston/Desktop/smartpicks-site');
        console.info('   python3 -m http.server 8000');
        console.info('   Then open: http://localhost:8000');
    }
}

function hideError() {
    const errorDiv = document.getElementById('error-message');
    errorDiv.style.display = 'none';
}

// ============================================================================
// AUTO-REFRESH
// ============================================================================

function startAutoRefresh() {
    // Clear existing timer
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    
    // Set new timer
    refreshTimer = setInterval(() => {
        console.log('Auto-refreshing data...');
        loadData();
    }, REFRESH_INTERVAL);
    
    console.log(`✓ Auto-refresh enabled (every ${REFRESH_INTERVAL / 1000}s)`);
}

// ============================================================================
// EXPORTS (for testing)
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        loadData,
        formatCurrency,
        formatOdds,
        formatTimestamp
    };
}