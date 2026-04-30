import logging
import pandas as pd
import numpy as np
from typing import Optional
from disk_cache import OHLCV_COLUMNS
from symbol_mapper import resolve_yahoo_symbol

logger = logging.getLogger("stock_screener.yahoo")


def fetch_yahoo_history(
    ticker: str,
    period: str = "2y",
    market: Optional[str] = None,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    symbol = resolve_yahoo_symbol(ticker, market)

    try:
        # Use Ticker.history() instead of yf.download() to avoid the batch-merge
        # bug in yfinance 1.x where concurrent downloads get combined into a
        # MultiIndex DataFrame with shape (N, 3) instead of (N,) per column.
        ticker_obj = yf.Ticker(symbol)
        data = ticker_obj.history(
            period=period,
            interval="1d",
            auto_adjust=True,
            timeout=15,
        )

        if data is None or data.empty:
            logger.warning("Yahoo Finance: no data for %s (resolved: %s)", ticker, symbol)
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        # Ticker.history() returns a flat-column DataFrame (no MultiIndex)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = pd.DataFrame()
        df["datetime"] = data.index
        df["open"]   = pd.to_numeric(data["Open"],   errors="coerce").values
        df["high"]   = pd.to_numeric(data["High"],   errors="coerce").values
        df["low"]    = pd.to_numeric(data["Low"],    errors="coerce").values
        df["close"]  = pd.to_numeric(data["Close"],  errors="coerce").values
        df["volume"] = pd.to_numeric(data["Volume"], errors="coerce").values

        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
        df = df.dropna(subset=["close"])
        df = df.sort_values("datetime").reset_index(drop=True)

        logger.info(
            "Yahoo Finance: fetched %d rows for %s (resolved: %s)",
            len(df), ticker, symbol,
        )
        return df

    except Exception as e:
        logger.error(
            "Yahoo Finance error for %s (resolved: %s): %s — %s",
            ticker, symbol, type(e).__name__, e,
        )
        return pd.DataFrame(columns=OHLCV_COLUMNS)


def fetch_yahoo_fundamentals(ticker: str, market: Optional[str] = None) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return {}

    symbol = resolve_yahoo_symbol(ticker, market)

    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}

        if not info or info.get("trailingPegRatio") is None and info.get("marketCap") is None:
            logger.warning("Yahoo fundamentals: no data for %s (resolved: %s)", ticker, symbol)
            return {}

        def sf(val):
            if val is None:
                return np.nan
            try:
                v = float(val)
                return v
            except (ValueError, TypeError):
                return np.nan

        revenue = sf(info.get("totalRevenue"))
        net_income = sf(info.get("netIncomeToCommon"))
        gross_profit = sf(info.get("grossProfits"))
        ebitda = sf(info.get("ebitda"))
        total_debt = sf(info.get("totalDebt"))
        total_cash = sf(info.get("totalCash"))
        book_value = sf(info.get("bookValue"))
        shares = sf(info.get("sharesOutstanding"))
        equity_val = book_value * shares if not np.isnan(book_value) and not np.isnan(shares) else np.nan
        total_assets = sf(info.get("totalAssets"))

        operating_margins = sf(info.get("operatingMargins"))
        operating_income = operating_margins * revenue if not np.isnan(operating_margins) and not np.isnan(revenue) else np.nan

        net_margin_calc = np.nan
        if not np.isnan(net_income) and not np.isnan(revenue) and revenue != 0:
            net_margin_calc = net_income / revenue

        roic_calc = np.nan
        if not np.isnan(net_income) and not np.isnan(equity_val) and equity_val != 0:
            roic_calc = net_income / equity_val

        revenue_prev = np.nan
        net_income_prev = np.nan
        try:
            inc_stmt = stock.income_stmt
            if inc_stmt is not None and not inc_stmt.empty and inc_stmt.shape[1] >= 2:
                rev_row = None
                for label in ["Total Revenue", "TotalRevenue"]:
                    if label in inc_stmt.index:
                        rev_row = label
                        break
                if rev_row is not None:
                    revenue_prev = sf(inc_stmt.iloc[inc_stmt.index.get_loc(rev_row), 1])

                ni_row = None
                for label in ["Net Income", "NetIncome", "Net Income Common Stockholders"]:
                    if label in inc_stmt.index:
                        ni_row = label
                        break
                if ni_row is not None:
                    net_income_prev = sf(inc_stmt.iloc[inc_stmt.index.get_loc(ni_row), 1])
        except Exception as e:
            logger.debug("Yahoo income_stmt error for %s: %s", ticker, e)

        de_raw = sf(info.get("debtToEquity"))
        de_ratio = de_raw / 100.0 if not np.isnan(de_raw) else np.nan

        result = {
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": sf(info.get("marketCap")),
            "pe": sf(info.get("trailingPE")),
            "pb": sf(info.get("priceToBook")),
            "ev_ebitda": sf(info.get("enterpriseToEbitda")),
            "peg": sf(info.get("trailingPegRatio") or info.get("pegRatio")),
            "revenue": revenue,
            "revenue_prev_year": revenue_prev,
            "net_income": net_income,
            "net_income_prev_year": net_income_prev,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebitda": ebitda,
            "total_assets": total_assets,
            "total_debt": total_debt,
            "equity": equity_val,
            "cash": total_cash,
            "eps": sf(info.get("trailingEps")),
            "gross_margin": sf(info.get("grossMargins")),
            "net_margin": net_margin_calc if not np.isnan(net_margin_calc) else sf(info.get("profitMargins")),
            "operating_margin": operating_margins,
            "roe": sf(info.get("returnOnEquity")),
            "roa": sf(info.get("returnOnAssets")),
            "roic": roic_calc,
            "debt_to_equity": de_ratio,
        }

        has_financials = any(
            result.get(f) is not None and not (isinstance(result.get(f), float) and np.isnan(result.get(f)))
            for f in ["revenue", "net_income", "equity"]
        )
        if has_financials:
            logger.info("Yahoo fundamentals OK for %s: revenue=%s, net_income=%s, equity=%s",
                        ticker, result.get("revenue"), result.get("net_income"), result.get("equity"))
        else:
            logger.info("Yahoo fundamentals: no financial data for %s", ticker)

        return result

    except Exception as e:
        logger.error("Yahoo fundamentals error for %s: %s — %s", ticker, type(e).__name__, e)
        return {}


def fetch_yahoo_benchmark(index_symbol: str) -> pd.DataFrame:
    from symbol_mapper import resolve_yahoo_benchmark
    resolved = resolve_yahoo_benchmark(index_symbol)
    return fetch_yahoo_history(resolved, period="2y", market=None)
