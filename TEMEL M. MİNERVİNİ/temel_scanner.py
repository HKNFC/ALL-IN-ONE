"""
temel_scanner.py — TEMEL M. MİNERVİNİ
=======================================
UniversalStockScanner'ı extend eder; USA hisselerini orijinal scan_us_stock()
ile tarayıp üstüne FMP temel skoru ekler.

YAKLAŞIM:
  1. scan_us_stock() çağrılır (orijinal, çalışan teknik tarama)
  2. Temel skor FMP'den look-ahead bias'sız eklenir
  3. Final skor = teknik × (1-fw) + temel × fw

BIST taraması DESTEKLENMEZ — yalnızca USA içindir.
"""

import sys
import os
import logging
from datetime import datetime
from typing import Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

from universal_scanner import UniversalStockScanner
from historical_fundamentals_fmp import (
    get_fundamentals_as_of,
    calc_historical_fund_score,
)

logger = logging.getLogger(__name__)


class TemelUSAScanner(UniversalStockScanner):
    """
    USA taramasına FMP temel veri skorunu ekleyen scanner.

    scan_us_stock_temel():
        1. Orijinal scan_us_stock() → teknik filtreler + RS
        2. get_fundamentals_as_of(ticker, as_of_date) → temel skor
        3. final_score = tech * (1 - fw) + fund * fw
    """

    def scan_us_stock_temel(
        self,
        ticker: str,
        sp500_data,
        as_of_date: Optional[str] = None,
        fund_weight: float = 0.40,
        stock_data=None,
    ) -> Optional[dict]:
        """
        Teknik + Temel birleşik skor döndür.

        Args:
            ticker:     Sembol (ör. AAPL)
            sp500_data: Benchmark DataFrame
            as_of_date: 'YYYY-MM-DD' — bu tarihe kadar bilinen veri kullanılır
            fund_weight: 0.0–0.6 (0 = saf teknik)
            stock_data: Hazır OHLCV DataFrame (backtest optimizasyonu için)

        Returns:
            dict (temel+teknik skorlar eklendi) veya None (eleme)
        """
        try:
            # ── 1. Orijinal teknik tarama ────────────────────────────────────
            base = self.scan_us_stock(
                ticker,
                sp500_data,
                stock_data=stock_data,
                as_of_date=as_of_date,
            )
            if base is None:
                return None  # teknik kriterleri geçemedi

            # ── 2. Teknik skoru türet ────────────────────────────────────────
            # RS değeri (IBD tarzı: IBD RS ~0-99 veya diverjans yüzdesi)
            rs = float(base.get('RS', 0) or 0)
            # RS'yi 0-100'e normalize et (RS genellikle -100 ile +200 arasında)
            tech_score = max(0.0, min(100.0, (rs + 50) / 2.0))

            # ── 3. Temel skor (FMP, look-ahead bias'sız) ────────────────────
            fund_score   = 50.0   # varsayılan nötr
            fund_break   = {"note": "temel veri yok — nötr 50"}
            fund_missing = True

            if fund_weight > 0.0:
                date_str = as_of_date or datetime.today().strftime('%Y-%m-%d')
                try:
                    fund_data = get_fundamentals_as_of(ticker, date_str)
                    if fund_data is not None:
                        fund_score, fund_break = calc_historical_fund_score(
                            fund_data, strategy="Alfa"
                        )
                        fund_missing = False
                except Exception as e:
                    logger.debug(f"{ticker} temel veri hatası: {e}")

            # ── 4. Final birleşik skor ───────────────────────────────────────
            final_score = tech_score * (1.0 - fund_weight) + fund_score * fund_weight

            # ── 5. Base dict'e ekle ve döndür ───────────────────────────────
            base.update({
                'Tech_Score':       round(tech_score, 2),
                'Fund_Score':       round(fund_score, 2),
                'Final_Score':      round(final_score, 2),
                'RS_Score':         round(final_score, 2),  # sıralama için
                'Fund_Weight_Used': round(fund_weight, 2),
                'Fund_Missing':     fund_missing,
                'Fund_Breakdown':   fund_break,
            })
            return base

        except Exception as e:
            logger.debug(f"{ticker} scan_us_stock_temel hatası: {e}")
            return None
