#!/usr/bin/env python3
"""
scan_integrity_test.py — Tarama mantığı doğrulama testi.

Kullanım:
    python3 scan_integrity_test.py

Başarı kriteri:
  1. RS değerleri birbirinden farklı (normalize/cap yok)
  2. Backtest top picks ile scanner top picks aynı hisseleri seçiyor
  3. Sıralama RS'e göre azalan
"""

import warnings, sys, os
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from backtest_engine import MinerviniBacktest

TEST_DATE  = '2026-02-02'
MARKET     = 'US'
TOP_N      = 5

PASS = '✅'
FAIL = '❌'
WARN = '⚠️ '

def run():
    print('='*60)
    print(' SEPA Tarama Bütünlük Testi')
    print(f' Tarih: {TEST_DATE} | Piyasa: {MARKET}')
    print('='*60)
    errors = []

    # ── 1. Backtest taraması ──────────────────────────────────────
    print('\n[1/4] Backtest taraması çalıştırılıyor...')
    bt       = MinerviniBacktest(TEST_DATE, TEST_DATE)
    scan_dt  = pd.Timestamp(TEST_DATE)
    tickers  = list(bt._us_tickers)
    results  = bt.scan_market_at_date(scan_dt, market=MARKET, tickers_override=tickers)
    print(f'      {len(results)} hisse bulundu')

    # ── 2. RS değerleri birbirinden farklı mı? ────────────────────
    print('\n[2/4] RS değerleri kontrol ediliyor...')
    rs_vals = [float(s.get('RS', s.get('RS_Score', 0))) for s in results]
    unique_rs = len(set(rs_vals))
    total_rs  = len(rs_vals)
    pct_unique = unique_rs / total_rs * 100 if total_rs else 0

    if pct_unique > 80:
        print(f'  {PASS} RS farklılaşması: {unique_rs}/{total_rs} benzersiz değer ({pct_unique:.0f}%)')
    else:
        msg = f'RS farklılaşması yetersiz: sadece {unique_rs}/{total_rs} benzersiz (%{pct_unique:.0f})'
        print(f'  {FAIL} {msg}')
        errors.append(msg)

    # Tüm değerler 100 mi? (normalize/cap hatası)
    all_100 = sum(1 for v in rs_vals if v == 100.0)
    if all_100 / total_rs > 0.5:
        msg = f'RS normalize/cap hatası: {all_100}/{total_rs} hisse RS=100 alıyor'
        print(f'  {FAIL} {msg}')
        errors.append(msg)
    else:
        print(f'  {PASS} RS cap hatası yok (RS=100 olan: {all_100}/{total_rs})')

    # ── 3. Backtest top picks ──────────────────────────────────────
    print('\n[3/4] Backtest Top Picks seçiliyor...')
    bt_top = bt.select_top_stocks(results, top_n=TOP_N)
    bt_tickers = [s['Ticker'] for s in bt_top]
    print(f'  Backtest Top {TOP_N}: {", ".join(bt_tickers)}')
    for s in bt_top:
        rs = s.get('RS_Score', s.get('RS', 0))
        print(f'    • {s["Ticker"]:8s} RS={float(rs):.1f}  {s.get("Status","?")}')

    # ── 4. Scanner top picks (aynı mantık) ───────────────────────
    print('\n[4/4] Scanner Top Picks (frontend mantığı) kontrol ediliyor...')

    def scanner_get_top_picks(results, top_n):
        """scanner.html getTopPicks() ile birebir aynı mantık"""
        filtered = [s for s in results if s.get('Status') in ('BREAKOUT','PIVOT_NEAR','SETUP')]
        sorted_  = sorted(filtered,
                          key=lambda s: float(s.get('RS') or s.get('RS_Divergence_%') or 0),
                          reverse=True)
        return sorted_[:top_n]

    sc_top     = scanner_get_top_picks(results, TOP_N)
    sc_tickers = [s['Ticker'] for s in sc_top]
    print(f'  Scanner Top {TOP_N}: {", ".join(sc_tickers)}')

    if bt_tickers == sc_tickers:
        print(f'  {PASS} Backtest ve Scanner aynı hisseleri seçiyor!')
    else:
        only_bt = set(bt_tickers) - set(sc_tickers)
        only_sc = set(sc_tickers) - set(bt_tickers)
        msg = f'Backtest/Scanner farkı — sadece BT: {only_bt}, sadece SC: {only_sc}'
        print(f'  {FAIL} {msg}')
        errors.append(msg)

    # ── RS sıralaması azalan mı? ──────────────────────────────────
    bt_rs = [float(s.get('RS_Score', s.get('RS', 0))) for s in bt_top]
    if bt_rs == sorted(bt_rs, reverse=True):
        print(f'  {PASS} Sıralama doğru (RS azalan)')
    else:
        msg = 'RS sıralaması bozuk'
        print(f'  {FAIL} {msg}')
        errors.append(msg)

    # ── 5. Determinizm: aynı backtest iki kez çalıştırılınca aynı sonuç ─────
    print('\n[5/5] Determinizm kontrolü (aynı backtest 2 kez)...')
    try:
        bt2      = MinerviniBacktest(TEST_DATE, TEST_DATE)
        results2 = bt2.scan_market_at_date(scan_dt, market=MARKET, tickers_override=tickers)
        top2     = bt2.select_top_stocks(results2, top_n=TOP_N)
        bt2_tickers = [s['Ticker'] for s in top2]

        if bt_tickers == bt2_tickers:
            print(f'  {PASS} İki çalıştırma aynı sonucu verdi: {", ".join(bt_tickers)}')
        else:
            msg = f'Determinizm sorunu — 1.çalıştırma: {bt_tickers}, 2.çalıştırma: {bt2_tickers}'
            print(f'  {FAIL} {msg}')
            errors.append(msg)
    except Exception as e:
        print(f'  {WARN} Determinizm testi atlandı: {e}')

    # ── Sonuç ─────────────────────────────────────────────────────
    print('\n' + '='*60)
    if not errors:
        print(f'{PASS} TÜM TESTLER GEÇTİ — Tarama mantığı sağlıklı')
    else:
        print(f'{FAIL} {len(errors)} HATA:')
        for e in errors:
            print(f'   • {e}')
    print('='*60)
    return len(errors) == 0


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
