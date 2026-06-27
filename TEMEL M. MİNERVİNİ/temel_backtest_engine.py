"""
temel_backtest_engine.py — TEMEL M. MİNERVİNİ
==============================================
MinerviniBacktest'i extend eder; USA backtestinde look-ahead bias'sız
FMP temel verisi ile birleşik final_score hesaplar.

Kullanım:
    from temel_backtest_engine import TemelBacktest
    bt = TemelBacktest("2023-01-01", "2024-12-31", fund_weight=0.40)
    result = bt.run_backtest(portfolio_size=7, frequency="monthly")
"""

import sys
import os
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

# Mark Minervini backtest altyapısı
from backtest_engine import MinerviniBacktest, MarketDataCache, _to_float

# Temel scanner (teknik + temel skor)
from temel_scanner import TemelUSAScanner

logger = logging.getLogger(__name__)


def _safe_print(*args, **kwargs):
    """BrokenPipeError'a karşı korumalı print."""
    try:
        print(*args, **kwargs)
    except (BrokenPipeError, OSError):
        pass


class TemelBacktest(MinerviniBacktest):
    """
    USA backtestinde teknik skora ek olarak FMP temel skorunu kullanan engine.

    fund_weight=0.0 → saf teknik (MinerviniBacktest ile aynı sonuç)
    fund_weight=0.4 → %60 teknik + %40 temel
    """

    def __init__(self, start_date, end_date, initial_capital=100_000, fund_weight=0.40):
        super().__init__(start_date, end_date, initial_capital)
        self.fund_weight = float(fund_weight)
        # _us_tickers MinerviniBacktest'ten geliyor (903+ hisse) — override etme!
        self.scanner = TemelUSAScanner()

    # ------------------------------------------------------------------
    # Tek rebalance tarihinde USA taraması (temel + teknik)
    # ------------------------------------------------------------------

    def _scan_usa_temel(self, scan_date: pd.Timestamp) -> list:
        """
        scan_date itibarıyla bilinen veri ile USA hisselerini tara.
        Her hisse için: rs_score, trend_score, vcp_score + fund_score → final_score
        """
        cutoff    = scan_date.normalize()
        as_of_str = cutoff.strftime('%Y-%m-%d')
        sp500     = self._cache.get_slice('^GSPC', cutoff)

        tickers = sorted(self._us_tickers)
        results = []

        def _score(ticker):
            stock_data = self._cache.get_slice(ticker, cutoff)
            if len(stock_data) < 200:
                return None
            return self.scanner.scan_us_stock_temel(
                ticker     = ticker,
                sp500_data = sp500,
                as_of_date = as_of_str,
                fund_weight= self.fund_weight,
                stock_data = stock_data,
            )

        workers = min(12, max(1, len(tickers)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_score, t): t for t in tickers}
            for future in futures:
                try:
                    res = future.result(timeout=30)
                except Exception:
                    res = None
                if res:
                    results.append(res)

        _safe_print(f"  ✅ {len(results)} USA hissesi kriterleri geçti", flush=True)
        return results

    # ------------------------------------------------------------------
    # Hisse seçimi — Final_Score azalan sıraya göre
    # ------------------------------------------------------------------

    def _select_top_temel(self, scan_results: list, top_n: int) -> list:
        """
        BREAKOUT / PIVOT_NEAR / SETUP içinde Final_Score'a göre top N seç.
        Status önceliği yok — saf final_score sıralaması.
        """
        eligible = [
            s for s in scan_results
            if s.get('Status') in ('BREAKOUT', 'PIVOT_NEAR', 'SETUP')
        ]
        if not eligible:
            _safe_print("  ⚠️  Uygun hisse (BREAKOUT/PIVOT_NEAR/SETUP) bulunamadı.", flush=True)
            return []

        eligible.sort(key=lambda s: _to_float(s.get('Final_Score', 0)), reverse=True)
        top = eligible[:top_n]
        for i, s in enumerate(top, 1):
            _safe_print(
                f"    {i}. {s['Ticker']:10s} | "
                f"Final:{_to_float(s.get('Final_Score',0)):6.1f} "
                f"(Tech:{_to_float(s.get('Tech_Score',0)):5.1f} "
                f"Fund:{_to_float(s.get('Fund_Score',0)):5.1f}) "
                f"| {s.get('Status','?')}",
                flush=True,
            )
        return top

    # ------------------------------------------------------------------
    # Ana backtest döngüsü
    # ------------------------------------------------------------------

    def run_backtest(self, portfolio_size=7, frequency='monthly') -> dict:
        """
        USA backtestini temel veri dahil çalıştır.

        Args:
            portfolio_size: Eş zamanlı tutulacak hisse sayısı
            frequency:      'monthly' | 'biweekly' | 'weekly'

        Returns:
            {
              'equity_curve': [...],
              'history':      [...],
              'total_return': float,
              'settings':     {...}
            }
        """
        freq_labels = {'weekly': 'Haftalık', 'biweekly': '15 Günlük', 'monthly': 'Aylık'}
        _safe_print("\n" + "=" * 70, flush=True)
        _safe_print("🚀 TEMEL M. MİNERVİNİ BACKTEST (USA)", flush=True)
        _safe_print(f"📅 {self.start_date.date()} → {self.end_date.date()}", flush=True)
        _safe_print(f"💰 Sermaye: ${self.initial_capital:,.0f}  |  Portföy: {portfolio_size} hisse", flush=True)
        _safe_print(f"⚖️  Temel Ağırlık: %{self.fund_weight*100:.0f}  |  Teknik Ağırlık: %{(1-self.fund_weight)*100:.0f}", flush=True)
        _safe_print("=" * 70, flush=True)

        # Tüm veriyi tek seferlik indir
        all_tickers = list(self._us_tickers)
        self._global_prefetch(all_tickers, 'US')

        rebalance_dates = self.get_rebalance_dates(frequency)
        _safe_print(f"📆 {len(rebalance_dates)} {freq_labels.get(frequency,'Aylık').lower()} rebalancing planlandı", flush=True)

        for i, date in enumerate(rebalance_dates, 1):
            _safe_print(f"\n── Periyot {i}/{len(rebalance_dates)}: {date.strftime('%d %B %Y')} ──", flush=True)

            scan_results = self._scan_usa_temel(date)
            top_stocks   = self._select_top_temel(scan_results, top_n=portfolio_size)

            self.rebalance_portfolio(top_stocks, date)

            pv  = float(self.calculate_portfolio_value(date))
            ret = ((pv / self.initial_capital) - 1) * 100
            self.equity_curve.append({
                'date':       date.strftime('%Y-%m-%d'),
                'value':      pv,
                'return_pct': ret,
            })
            _safe_print(f"  💼 Portföy: ${pv:,.2f}  |  Getiri: {ret:+.2f}%", flush=True)

        # Pozisyonları kapat
        _safe_print("\n── Final: pozisyonlar kapatılıyor ──", flush=True)
        self.rebalance_portfolio([], self.end_date)

        final_value  = float(self.current_capital)
        total_return = ((final_value / self.initial_capital) - 1) * 100
        self.equity_curve.append({
            'date':       self.end_date.strftime('%Y-%m-%d'),
            'value':      final_value,
            'return_pct': total_return,
        })

        _safe_print(f"\n✅ Toplam Getiri: {total_return:+.2f}%", flush=True)

        # ── Summary hesapla (frontend render() için) ──────────────────
        eq_values  = [e['value'] for e in self.equity_curve if e.get('value')]
        trade_hist = list(self.history)   # AL/SAT kayıtları

        # Max drawdown
        max_dd = 0.0
        peak   = self.initial_capital
        for v in eq_values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Win/loss (SELL işlemleri)
        sells     = [t for t in trade_hist if t.get('action') == 'SELL']
        win_count = sum(1 for t in sells if _to_float(t.get('pnl', 0) or t.get('return_pct', 0)) > 0)
        los_count = len(sells) - win_count
        win_rate  = (win_count / len(sells) * 100) if sells else 0.0

        # Sharpe (basit)
        rets   = []
        for i in range(1, len(eq_values)):
            if eq_values[i-1] > 0:
                rets.append((eq_values[i] - eq_values[i-1]) / eq_values[i-1])
        import statistics
        if len(rets) >= 2:
            mean_r = statistics.mean(rets)
            std_r  = statistics.stdev(rets)
            sharpe = (mean_r / std_r * math.sqrt(12)) if std_r > 0 else 0.0
        else:
            sharpe = 0.0

        summary = {
            'total_return':      round(total_return, 2),
            'total_return_pct':  round(total_return, 2),
            'final_value':       round(final_value, 2),
            'initial_capital':   round(self.initial_capital, 2),
            'max_drawdown':      round(-max_dd, 2),
            'win_rate':          round(win_rate, 2),
            'sharpe_ratio':      round(sharpe, 2),
            'total_trades':      len(trade_hist),
            'winning_trades':    win_count,
            'losing_trades':     los_count,
            'currency':          '$',
            'currency_name':     'USD',
            'market':            'US',
            'fund_weight':       self.fund_weight,
        }

        return {
            'equity_curve':  self.equity_curve,
            'trade_history': trade_hist,        # frontend 'trade_history' bekliyor
            'history':       trade_hist,        # uyumluluk için
            'summary':       summary,
            'total_return':  total_return,
            'settings': {
                'start':          self.start_date.strftime('%Y-%m-%d'),
                'end':            self.end_date.strftime('%Y-%m-%d'),
                'fund_weight':    self.fund_weight,
                'portfolio_size': portfolio_size,
                'frequency':      frequency,
            }
        }
