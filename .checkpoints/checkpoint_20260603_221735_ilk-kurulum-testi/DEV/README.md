# Stock Screener

A production-ready Python Streamlit stock screening web app that ranks BIST (Turkey) and US stocks using a custom RS Score across five dimensions.

## Features

- **RS Score Engine** — Composite 0–100 score based on percentile ranking across all stocks in the selected universe
- **Five Scoring Dimensions**:
  - Financial Strength (25%) — ROIC, leverage, asset quality
  - Growth (20%) — Revenue & earnings growth (YoY + 3Y CAGR)
  - Margin Quality (15%) — Gross, operating, net, EBITDA margins + margin trend
  - Valuation (20%) — P/E, P/B, EV/EBITDA, PEG (lower is better)
  - Momentum (20%) — Multi-period returns, 52W high proximity, relative strength vs index
- **Quality Presets** — None / Basic / Strict pre-screening filters
- **Watchlist** — Persistent JSON-backed watchlist with auto-score updates and CSV export
- **Live Data** — Twelve Data API integration with in-memory caching, rate-limit tracking, and mock data fallback
- **Diagnostics** — Fetch status (fetched/failed/incomplete), missing-field summaries, per-stock warnings

## Kurulum ve Başlatma

### Gereksinimler
- Python 3.12+
- Node.js 20+ ve [pnpm](https://pnpm.io/installation)

### 1. Python ortamı kurulumu

```bash
bash setup.sh
```

Bu komut:
- `.venv` adında bir Python sanal ortamı oluşturur
- Tüm Python bağımlılıklarını yükler
- `env.example` dosyasını `.env` olarak kopyalar

### 2. API anahtarını girin

`.env` dosyasını açıp `TWELVE_DATA_API_KEY` değerini girin:

```
TWELVE_DATA_API_KEY=your_key_here
```

API anahtarı olmadan uygulama demo/mock veri ile çalışır.

### 3. Uygulamayı başlatın

**Sadece Streamlit (ana uygulama):**
```bash
bash run_app.sh
# → http://localhost:5000
```

**Tüm servisler (Streamlit + React + API):**
```bash
bash run_all.sh
# Streamlit  → http://localhost:5000
# API Server → http://localhost:4000
# React App  → http://localhost:3000
```

## Supported Markets

| Market | Stocks | Benchmark |
|--------|--------|-----------|
| BIST (Turkey) | 20 | XU100 |
| US Stocks | 20 | S&P 500 (SPX) |

## Project Structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — sidebar, screener, watchlist, stock details |
| `config.py` | Markets, scoring weights, API settings, filter thresholds |
| `data_model.py` | DataFrame schema, validation, type coercion, mock data |
| `data_fetcher.py` | Orchestration — provider selection, fallback, diagnostics |
| `price_provider.py` | Abstract base class for market data providers |
| `twelve_data_provider.py` | Twelve Data API implementation with caching |
| `financial_metrics.py` | Derived financial ratios (margins, growth, returns) |
| `momentum_metrics.py` | Price-based momentum indicators (returns, MA, relative strength) |
| `scoring_engine.py` | Percentile-based RS Score computation and categorization |
| `filters.py` | Quality filter presets and utility filters |
| `watchlist.py` | JSON-backed watchlist storage and export |
| `utils.py` | Display formatting helpers |

## RS Score Methodology

1. **Derive** financial metrics from raw fundamentals (margins, growth rates, return ratios)
2. **Winsorize** extreme outliers at 5th/95th percentiles
3. **Percentile-rank** each metric across the universe (0–100 scale)
4. **Reverse-score** lower-is-better metrics (D/E, PE, PB, EV/EBITDA, PEG)
5. **Weight** sub-scores into five category scores, then into the final RS Score
6. **Categorize**: Elite (85–100), Strong (70–85), Watchlist (55–70), Weak (40–55), Avoid (0–40)

Missing metrics are handled via proportional weight redistribution — a stock is never penalized for data it lacks.
