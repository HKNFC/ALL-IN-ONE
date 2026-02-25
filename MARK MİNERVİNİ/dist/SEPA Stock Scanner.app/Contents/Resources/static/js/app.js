// Mark Minervini Trading Platform - JavaScript

// API Base URL
const API_BASE = '';

// Utility Functions
function showLoading(elementId) {
    document.getElementById(elementId).innerHTML = '<div class="loading">Loading...</div>';
}

function showError(elementId, message) {
    document.getElementById(elementId).innerHTML = `<div class="error">${message}</div>`;
}

// API Calls
async function fetchAPI(endpoint, options = {}) {
    try {
        const response = await fetch(API_BASE + endpoint, options);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// Stock Scanner
async function scanMarkets(market = 'BOTH', quick = true) {
    const endpoint = quick ? '/api/scan/quick' : '/api/scan/full';
    
    return fetchAPI(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ market })
    });
}

// Get Stock Details
async function getStockDetails(ticker, market = 'US') {
    return fetchAPI(`/api/stock/${ticker}?market=${market}`);
}

// Portfolio Management
async function getPortfolio() {
    return fetchAPI('/api/portfolio');
}

async function addToPortfolio(ticker, entryPrice, quantity, stopLoss) {
    return fetchAPI('/api/portfolio', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            ticker,
            entry_price: entryPrice,
            quantity,
            stop_loss: stopLoss
        })
    });
}

// Signals
async function getSignalHistory() {
    return fetchAPI('/api/signals/history');
}

// Stats
async function getStats() {
    return fetchAPI('/api/stats');
}

// Format Currency
function formatCurrency(value, currency = '$') {
    return `${currency}${value.toFixed(2)}`;
}

// Format Percentage
function formatPercent(value) {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

// Export
window.MinerviniPlatform = {
    scanMarkets,
    getStockDetails,
    getPortfolio,
    addToPortfolio,
    getSignalHistory,
    getStats,
    formatCurrency,
    formatPercent
};
