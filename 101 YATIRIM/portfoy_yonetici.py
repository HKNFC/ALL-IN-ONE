"""
BIST Portföy Yöneticisi — Aylık Rebalancing Motoru
Her ayın ilk iş gününde çalışır.
Mevcut portföydeki hissenin skoru, dışarıdaki bir hissenin skorunun
%10 altına düşerse → çıkar, yeni yüksek puanlyı ekle.
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import sys
import time
from datetime import datetime, date, timedelta
from copy import deepcopy

# bist_tarama.py'deki tarama fonksiyonlarını içe aktar
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bist_tarama import (
    alfa_score, beta_score, delta_score,
    get_bist100_return, run_scan, BIST100,
    print_section
)

# ─────────────────────────────────────────────
#  Sabitler
# ─────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PORTFOY_FILE  = os.path.join(BASE_DIR, "portfoy_durumu.json")
LOG_FILE      = os.path.join(BASE_DIR, "rebalancing_log.txt")
PORTFOY_SIZE  = 5      # Her strateji için portföydeki hisse adedi
ESLEME_ESIGI  = 0.10   # %10 performans farkı eşiği

# ─────────────────────────────────────────────
#  İlk İş Günü Kontrolü
# ─────────────────────────────────────────────
def is_first_business_day(dt: date = None) -> bool:
    if dt is None:
        dt = date.today()
    if dt.weekday() >= 5:
        return False
    d = date(dt.year, dt.month, 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d == dt

# ─────────────────────────────────────────────
#  Portföy Dosyası Okuma / Yazma
# ─────────────────────────────────────────────
def load_portfoy() -> dict:
    if os.path.exists(PORTFOY_FILE):
        with open(PORTFOY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"ALFA": [], "BETA": [], "DELTA": [], "son_guncelleme": None}

def save_portfoy(portfoy: dict):
    portfoy["son_guncelleme"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PORTFOY_FILE, "w", encoding="utf-8") as f:
        json.dump(portfoy, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
#  Log Yazıcı
# ─────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ─────────────────────────────────────────────
#  Puan Haritası: ticker -> skor sözlüğü oluştur
# ─────────────────────────────────────────────
def build_score_map(results: list) -> dict:
    return {r["ticker"]: r["score"] for r in results}

# ─────────────────────────────────────────────
#  Rebalancing Motoru
# ─────────────────────────────────────────────
def rebalance(strategy: str, current_list: list, all_results: list) -> tuple:
    """
    current_list : mevcut portföydeki ticker listesi (ör. ["AKBNK","ISCTR",...])
    all_results  : tüm hisselerin puan listesi (sıralı, en yüksek önce)

    Döndürür: (yeni_liste, degisiklik_listesi)
      degisiklik_listesi: [{"cikti": X, "girdi": Y, "neden": "..."}]
    """
    score_map    = build_score_map(all_results)
    mevcut_set   = set(current_list)
    degisiklikler = []

    # Portföyde olmayan adaylar (sıralı)
    adaylar = [r for r in all_results if r["ticker"] not in mevcut_set]

    yeni_liste = list(current_list)

    for mevcut_ticker in list(current_list):
        mevcut_skor = score_map.get(mevcut_ticker, 0)

        # En yüksek puanlı dışarıdaki aday
        if not adaylar:
            break
        en_iyi_aday = adaylar[0]
        aday_skor   = en_iyi_aday["score"]

        # Eşik kontrolü: aday_skor > mevcut_skor * (1 + esik)
        if aday_skor > mevcut_skor * (1 + ESLEME_ESIGI):
            yeni_liste.remove(mevcut_ticker)
            yeni_liste.append(en_iyi_aday["ticker"])
            mevcut_set.discard(mevcut_ticker)
            mevcut_set.add(en_iyi_aday["ticker"])

            neden = (
                f"{mevcut_ticker} skoru {mevcut_skor} pts, "
                f"{en_iyi_aday['ticker']} skoru {aday_skor} pts "
                f"(%{((aday_skor/mevcut_skor)-1)*100:.1f} fark > esik %{ESLEME_ESIGI*100:.0f})"
            )
            degisiklikler.append({
                "cikti": mevcut_ticker,
                "girdi": en_iyi_aday["ticker"],
                "cikan_skor": mevcut_skor,
                "giren_skor": aday_skor,
                "neden": neden,
            })
            log(f"  [{strategy}] DEGISIKLIK → CIKAN: {mevcut_ticker} ({mevcut_skor}pts) | "
                f"GIREN: {en_iyi_aday['ticker']} ({aday_skor}pts)")

            # Aday listesini güncelle
            adaylar = [r for r in all_results if r["ticker"] not in mevcut_set]
        else:
            log(f"  [{strategy}] {mevcut_ticker} ({mevcut_skor}pts) korunuyor — "
                f"en iyi aday {adaylar[0]['ticker']} ({aday_skor}pts) eşiği geçmiyor")

    return yeni_liste, degisiklikler

# ─────────────────────────────────────────────
#  Tüm Stratejileri Tara ve Rebalance Et
# ─────────────────────────────────────────────
def aylik_rebalancing(force: bool = False):
    bugun = date.today()

    if not force and not is_first_business_day(bugun):
        print(f"Bugun ({bugun}) ayın ilk iş günü degil. Çalışma atlandı.")
        print("Zorla çalıştırmak için: python portfoy_yonetici.py --force")
        return

    log("=" * 65)
    log(f"AYLIK REBALANCING BASLIYOR — {bugun}")
    log("=" * 65)

    portfoy = load_portfoy()

    # İlk çalıştırmada portföy boşsa son tarama sonuçlarını başlangıç yap
    ilk_kurulum = not any(portfoy.get(s) for s in ["ALFA", "BETA", "DELTA"])
    if ilk_kurulum:
        log("Portfoy bos — ilk kurulum modu, baslangic listesi olusturuluyor...")

    # BIST100 referans getirisi
    log("BIST100 referans getirisi aliniyor...")
    bist_ret = get_bist100_return()
    log(f"BIST100 yillik getiri: %{bist_ret:.2f}")

    tum_degisiklikler = {}
    ozet_satirlar     = []

    for strateji in ["ALFA", "BETA", "DELTA"]:
        log(f"\n--- {strateji} TARAMASI BASLIYOR ---")
        sonuclar = run_scan(strateji, BIST100, bist_ret)

        if not sonuclar:
            log(f"  [{strateji}] Hic sonuc gelmedi, atlaniyor.")
            continue

        if ilk_kurulum or not portfoy.get(strateji):
            # İlk kurulum: en yüksek PORTFOY_SIZE hisseyi al
            portfoy[strateji] = [r["ticker"] for r in sonuclar[:PORTFOY_SIZE]]
            log(f"  [{strateji}] Baslangic portfoyu: {portfoy[strateji]}")
            tum_degisiklikler[strateji] = []
        else:
            mevcut = portfoy[strateji]
            yeni, degisiklikler = rebalance(strateji, mevcut, sonuclar)
            portfoy[strateji]   = yeni
            tum_degisiklikler[strateji] = degisiklikler

        # Özet satır
        score_map = build_score_map(sonuclar)
        ozet_satirlar.append((strateji, portfoy[strateji], score_map))

    save_portfoy(portfoy)
    log(f"\nPortfoy kaydedildi: {PORTFOY_FILE}")

    # ── RAPOR ───────────────────────────────
    print_section("PORTFOY DURUMU RAPORU")
    print(f"\n  Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  BIST100 Yillik Getiri: %{bist_ret:.2f}\n")

    for strateji, liste, score_map in ozet_satirlar:
        print(f"\n  {'─'*60}")
        print(f"  {strateji} PORTFOYU:")
        for i, ticker in enumerate(liste, 1):
            skor = score_map.get(ticker, "?")
            print(f"    {i}. {ticker:<10}  {skor} pts")

        degisiklikler = tum_degisiklikler.get(strateji, [])
        if degisiklikler:
            print(f"\n  {strateji} DEGISIKLIKLERI:")
            for d in degisiklikler:
                print(f"    CIKTI : {d['cikti']:<10} ({d['cikan_skor']} pts)")
                print(f"    GIRDI : {d['girdi']:<10} ({d['giren_skor']} pts)")
                print(f"    NEDEN : {d['neden']}")
                print()
        else:
            print(f"\n  {strateji}: Degisiklik yok — mevcut portfoy korundu.")

    # Çoklu stratejide görünen hisseler
    tum_listeler = [set(portfoy.get(s, [])) for s in ["ALFA", "BETA", "DELTA"]]
    cok_stratejili = (tum_listeler[0] & tum_listeler[1]) | \
                     (tum_listeler[0] & tum_listeler[2]) | \
                     (tum_listeler[1] & tum_listeler[2])
    if cok_stratejili:
        print(f"\n  ** En az 2 stratejide gorunen: {', '.join(sorted(cok_stratejili))} **")

    print(f"\n{'':*<65}\n")
    log("REBALANCING TAMAMLANDI.")

# ─────────────────────────────────────────────
#  Portföy Durumu Göster (tarama yapmadan)
# ─────────────────────────────────────────────
def goster_portfoy():
    portfoy = load_portfoy()
    if not any(portfoy.get(s) for s in ["ALFA", "BETA", "DELTA"]):
        print("Henuz kayitli portfoy yok. Once rebalancing calistirin.")
        return
    print(f"\n  Son Guncelleme: {portfoy.get('son_guncelleme', 'bilinmiyor')}\n")
    for s in ["ALFA", "BETA", "DELTA"]:
        liste = portfoy.get(s, [])
        print(f"  {s}: {', '.join(liste) if liste else 'bos'}")
    print()

# ─────────────────────────────────────────────
#  CLI Giriş Noktası
# ─────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--goster" in args:
        goster_portfoy()
    elif "--force" in args or "--ilk-kurulum" in args:
        aylik_rebalancing(force=True)
    else:
        aylik_rebalancing(force=False)
