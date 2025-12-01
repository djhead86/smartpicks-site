/**
 * SmartPicksGPT Frontend
 * Displays betting picks and performance data
 */

// ============================================================================
// STATE
// ============================================================================

let appData = null;
let filteredHistory = [];

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    loadData();
    setupEventListeners();
});

function setupEventListeners() {
    const statusFilter = document.getElementById('status-filter');
    const limitSelect = document.getElementById('limit-select');
    
    if (statusFilter) {
        statusFilter.addEventListener('change', filterHistory);
    }
    
    if (limitSelect) {
        limitSelect.addEventListener('change', filterHistory);
    }
}

// ============================================================================
// DATA LOADING
// ============================================================================

async function loadData() {
    showLoading();
    
    try {
        const response = await fetch('data/data.json');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        appData = await response.json();
        
        hideLoading();
        showContent();
        renderAll();
        
    } catch (error) {
        console.error('Failed to load data:', error);
        showError();
    }
}

// ============================================================================
// UI STATE MANAGEMENT
// ============================================================================

function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('main-content').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showContent() {
    document.getElementById('main-content').classList.remove('hidden');
}

function showError() {
    hideLoading();
    document.getElementById('error').classList.remove('hidden');
}

// ============================================================================
// RENDERING
// ============================================================================

function renderAll() {
    renderLastUpdated();
    renderOverallPerformance();
    renderTodayPicks();
    renderBetHistory();
}

function renderLastUpdated() {
    const el = document.getElementById('last-updated');
    if (appData.generated_at) {
        const date = new Date(appData.generated_at);
        el.textContent = `Last updated: ${formatDateTime(date)}`;
    }
}

function renderOverallPerformance() {
    const perf = appData.overall_performance;
    
    document.getElementById('win-rate').textContent = `${perf.win_rate}%`;
    document.getElementById('total-bets').textContent = `${perf.won}-${perf.lost}-${perf.pending}`;
    
    const profitEl = document.getElementById('net-profit');
    profitEl.textContent = formatCurrency(perf.net_profit);
    profitEl.className = `stat-value ${perf.net_profit >= 0 ? 'positive' : 'negative'}`;
    
    const roiEl = document.getElementById('roi');
    roiEl.textContent = `${perf.roi >= 0 ? '+' : ''}${perf.roi}%`;
    roiEl.className = `stat-value ${perf.roi >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('starting-bankroll').textContent = formatCurrency(perf.starting_bankroll);
    document.getElementById('current-bankroll').textContent = formatCurrency(perf.current_bankroll);
}

function renderTodayPicks() {
    const summary = appData.today_summary;
    const picks = appData.today_picks;
    
    // Summary
    const summaryEl = document.getElementById('today-summary');
    if (picks.length === 0) {
        summaryEl.innerHTML = '<p class="no-picks">No picks available for today.</p>';
    } else {
        summaryEl.innerHTML = `
            <div class="summary-stats">
                <span><strong>${summary.pick_count}</strong> picks</span>
                <span><strong>${formatCurrency(summary.total_stake)}</strong> total stake</span>
                <span><strong>${formatCurrency(summary.expected_return)}</strong> expected return</span>
                <span><strong>${summary.avg_ev}%</strong> avg EV</span>
            </div>
        `;
    }
    
    // Picks
    const picksEl = document.getElementById('today-picks');
    picksEl.innerHTML = '';
    
    picks.forEach(pick => {
        const pickCard = createPickCard(pick);
        picksEl.appendChild(pickCard);
    });
}

function createPickCard(pick) {
    const card = document.createElement('div');
    card.className = 'pick-card';
    
    const gameTime = new Date(pick.commence_time);
    const isLive = gameTime <= new Date();
    
    card.innerHTML = `
        <div class="pick-header">
            <div class="pick-game">
                <strong>${pick.game}</strong>
                <span class="sport-badge">${pick.sport}</span>
            </div>
            <div class="pick-time ${isLive ? 'live' : ''}">
                ${isLive ? '🔴 LIVE' : formatGameTime(gameTime)}
            </div>
        </div>
        
        <div class="pick-details">
            <div class="pick-selection">
                <span class="bet-type-badge">${formatBetType(pick.bet_type)}</span>
                <strong>${pick.selection}</strong>
            </div>
            
            <div class="pick-odds">
                <span class="odds">${formatOdds(pick.odds)}</span>
            </div>
        </div>
        
        <div class="pick-stats">
            <div class="stat-item">
                <span class="label">EV:</span>
                <span class="value ev-positive">+${pick.ev.toFixed(2)}%</span>
            </div>
            <div class="stat-item">
                <span class="label">True Prob:</span>
                <span class="value">${(pick.true_prob * 100).toFixed(1)}%</span>
            </div>
            <div class="stat-item">
                <span class="label">Stake:</span>
                <span class="value">${formatCurrency(pick.bet_amount)}</span>
            </div>
            <div class="stat-item">
                <span class="label">Expected:</span>
                <span class="value">${formatCurrency(pick.expected_return)}</span>
            </div>
        </div>
    `;
    
    return card;
}

function renderBetHistory() {
    filterHistory();
}

function filterHistory() {
    const statusFilter = document.getElementById('status-filter').value;
    const limit = document.getElementById('limit-select').value;
    
    // Filter by status
    let filtered = appData.bet_history;
    if (statusFilter !== 'all') {
        filtered = filtered.filter(bet => bet.status === statusFilter);
    }
    
    // Sort by timestamp (most recent first)
    filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Apply limit
    if (limit !== 'all') {
        filtered = filtered.slice(0, parseInt(limit));
    }
    
    filteredHistory = filtered;
    renderHistoryTable();
}

function renderHistoryTable() {
    const tbody = document.getElementById('bet-history-body');
    tbody.innerHTML = '';
    
    if (filteredHistory.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="no-data">No bets match the selected filter.</td>
            </tr>
        `;
        return;
    }
    
    filteredHistory.forEach(bet => {
        const row = createHistoryRow(bet);
        tbody.appendChild(row);
    });
}

function createHistoryRow(bet) {
    const row = document.createElement('tr');
    row.className = `status-${bet.status}`;
    
    const timestamp = new Date(bet.timestamp);
    const returnValue = bet.status === 'pending' ? '-' : formatCurrency(bet.actual_return);
    const returnClass = bet.actual_return > 0 ? 'positive' : bet.actual_return < 0 ? 'negative' : '';
    
    row.innerHTML = `
        <td>${formatDate(timestamp)}</td>
        <td class="game-cell">${bet.game}</td>
        <td>${bet.sport}</td>
        <td><span class="bet-type-badge small">${formatBetType(bet.bet_type)}</span></td>
        <td>${bet.selection}</td>
        <td>${formatOdds(bet.odds)}</td>
        <td class="ev-cell">${bet.ev >= 0 ? '+' : ''}${bet.ev.toFixed(2)}%</td>
        <td>${formatCurrency(bet.bet_amount)}</td>
        <td><span class="status-badge status-${bet.status}">${bet.status}</span></td>
        <td class="${returnClass}">${returnValue}</td>
    `;
    
    return row;
}

// ============================================================================
// FORMATTING UTILITIES
// ============================================================================

function formatCurrency(amount) {
    const formatted = Math.abs(amount).toFixed(2);
    const sign = amount >= 0 ? '$' : '-$';
    return `${sign}${formatted}`;
}

function formatOdds(odds) {
    if (odds > 0) {
        return `+${odds}`;
    }
    return odds.toString();
}

function formatBetType(type) {
    const types = {
        'h2h': 'ML',
        'spreads': 'Spread',
        'totals': 'O/U'
    };
    return types[type] || type;
}

function formatDate(date) {
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
}

function formatDateTime(date) {
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

function formatGameTime(date) {
    const now = new Date();
    const diffMs = date - now;
    const diffHours = diffMs / (1000 * 60 * 60);
    
    if (diffHours < 24) {
        return date.toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    } else {
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    }
}
