"""
BIST Rebalans Tarihi Hesaplayıcı

Türkiye Borsası (BIST) tatil günlerini dikkate alarak
21 iş günü sonraki rebalans tarihini hesaplar.
"""

from datetime import date, timedelta
from typing import Optional

# ── Sabit Türkiye Resmi Tatilleri ──────────────────────────────────────────
_FIXED_HOLIDAYS = {
    (1,  1): "Yılbaşı",
    (4, 23): "Ulusal Egemenlik ve Çocuk Bayramı",
    (5,  1): "Emek ve Dayanışma Bayramı",
    (5, 19): "Atatürk'ü Anma Gençlik ve Spor Bayramı",
    (7, 15): "Demokrasi ve Millî Birlik Günü",
    (8, 30): "Zafer Bayramı",
    (10,29): "Cumhuriyet Bayramı",
}

# ── Dini Tatiller (Hicri takvim — yıla göre değişir) ──────────────────────
# Ramazan Bayramı: 3 gün, Kurban Bayramı: 4 gün + arife (yarım gün → tam gün say)
_RELIGIOUS_HOLIDAYS: set[date] = set()

def _add_range(d: date, n: int) -> None:
    for i in range(n):
        _RELIGIOUS_HOLIDAYS.add(d + timedelta(days=i))

# 2024
_add_range(date(2024, 4,  9), 3)   # Ramazan Bayramı
_add_range(date(2024, 6, 16), 4)   # Kurban Bayramı

# 2025
_add_range(date(2025, 3, 30), 3)   # Ramazan Bayramı
_add_range(date(2025, 6,  5), 4)   # Kurban Bayramı

# 2026
_add_range(date(2026, 3, 20), 3)   # Ramazan Bayramı
_add_range(date(2026, 5, 26), 4)   # Kurban Bayramı

# 2027
_add_range(date(2027, 3,  9), 3)   # Ramazan Bayramı
_add_range(date(2027, 5, 16), 4)   # Kurban Bayramı


def is_bist_holiday(d: date) -> bool:
    """Verilen gün BIST tatili mi?"""
    if d.weekday() >= 5:            # Cumartesi=5, Pazar=6
        return True
    if (d.month, d.day) in _FIXED_HOLIDAYS:
        return True
    if d in _RELIGIOUS_HOLIDAYS:
        return True
    return False


def next_bist_trading_day(d: date) -> date:
    """Verilen tarihten sonraki ilk iş gününü döndürür."""
    d = d + timedelta(days=1)
    while is_bist_holiday(d):
        d += timedelta(days=1)
    return d


def add_bist_trading_days(start: date, n_days: int = 21) -> date:
    """
    Başlangıç tarihinden itibaren n_days BIST iş günü sonrasını döndürür.
    Başlangıç tarihi dahil değil.
    """
    current = start
    counted = 0
    while counted < n_days:
        current += timedelta(days=1)
        if not is_bist_holiday(current):
            counted += 1
    return current


def next_rebalance_date(last_rebalance: date, freq: str = "1m") -> date:
    """
    Son rebalans tarihine göre bir sonraki rebalans tarihini hesaplar.

    freq: "1w" (5 iş günü), "15d" (11 iş günü), "1m" (21 iş günü)
    """
    n_map = {"1w": 5, "15d": 11, "1m": 21}
    n = n_map.get(freq, 21)
    return add_bist_trading_days(last_rebalance, n)


def trading_days_until(target: date, from_date: Optional[date] = None) -> int:
    """Bugünden (veya from_date'ten) hedefe kaç BIST iş günü kaldığını döndürür."""
    if from_date is None:
        from_date = date.today()
    if target <= from_date:
        return 0
    count = 0
    d = from_date
    while d < target:
        d += timedelta(days=1)
        if not is_bist_holiday(d):
            count += 1
    return count


def holiday_name(d: date) -> Optional[str]:
    """Tatil adını döndürür, tatil değilse None."""
    if d.weekday() == 5:
        return "Cumartesi"
    if d.weekday() == 6:
        return "Pazar"
    name = _FIXED_HOLIDAYS.get((d.month, d.day))
    if name:
        return name
    if d in _RELIGIOUS_HOLIDAYS:
        return "Dini Tatil"
    return None
