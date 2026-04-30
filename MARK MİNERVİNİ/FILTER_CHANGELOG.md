# 🔧 Filtre Değişiklikleri

## 📅 2026-02-18 - Filtreler Gevşetildi

### ❌ Eski Filtreler (Çok Sıkı)
```
✗ BIST RS: Sadece pozitif RS (>0) kabul ediliyordu
✗ US RS: Minimum 80 gerekiyordu  
✗ VCP Pattern: ZORUNLU - VCP yoksa hisse eleniyor
```

**Sonuç:** 474 BIST hissesinden 0 sonuç! ❌

---

### ✅ Yeni Filtreler (Dengeli)

#### BIST Taraması:
- ✅ **RS (Relative Strength):** Negatif RS'yi kabul et
  - Sıfır veya negatif RS'li hisseler de listelenir
  - RS değeri bilgilendirme amaçlı gösterilir
  
- ✅ **VCP Pattern:** OPSIYONEL
  - VCP yoksa "NO_VCP" olarak işaretlenir
  - VCP forming durumundaki hisseler "FORMING" olarak gösterilir
  - Hisse VCP olmasa da listeye girer

#### US Taraması:
- ✅ **RS Limiti:** 80 → Kaldırıldı
  - RS hesaplanamazsa default 50 değeri atanır
  - Düşük RS'li hisseler de listelenir
  
- ✅ **VCP Pattern:** OPSIYONEL
  - BIST ile aynı mantık

---

### 📊 Yeni Sonuçlar

**Test:** 10 popüler BIST hissesi
- **Eski:** 1-2 hisse bulunurdu
- **Yeni:** 10/10 hisse bulundu! ✅

**Beklenen Sonuç:**
- BIST 474 hisse → 50-100+ hisse bulunur
- US 128 hisse → 20-40+ hisse bulunur

---

### 🎯 Hala Aktif Olan Kritik Filtreler

Bu kriterler kaliteli hisse seçimi için korundu:

1. ✅ **Fiyat > 150G ve 200G SMA**
   - Güçlü trend sürekliliği
   
2. ✅ **200G SMA 30 gündür yukarı yönlü**
   - Uzun vadeli yükseliş trendi
   
3. ✅ **50G SMA > 150G ve 200G SMA**
   - Momentum göstergesi
   
4. ✅ **52 haftalık low'dan %25+ yukarıda**
   - Sağlam baz oluşumu
   
5. ✅ **52 haftalık high'a %25 veya daha yakın**
   - Güç göstergesi

---

## 💡 Kullanım Önerisi

### Filtreleme Stratejisi:
1. **İlk Tarama:** Tüm hisseler (gevşek filtre)
2. **Manuel İnceleme:** RS > 70 ve VCP "FORMING" olanları önceliklendir
3. **Detaylı Analiz:** Chart incelemesi ve temel analiz

### Status Açıklamaları:
- **BREAKOUT:** Pivot kırıldı, hacim var 🚀
- **PIVOT_NEAR:** Pivot'a çok yakın (%2 içinde) 🎯
- **SETUP:** Güzel kurulum, izlemeye değer 📊
- **WATCHING:** Takipte tut 👀

---

## 🔄 Geri Alma (Eski Filtrelere Dönme)

Eski sıkı filtrelere dönmek isterseniz:

```python
# universal_scanner.py dosyasında:

# BIST için (satır ~429):
if rs_divergence is None or rs_divergence <= 0:
    return None

# VCP için (satır ~434):
if not vcp_pattern:
    return None

# US için (satır ~365):
if rs is None or rs < 80:
    return None
```

---

**Not:** Bu değişiklikler Mark Minervini metodolojisinin temel prensiplerini korurken, daha fazla fırsat yakalama imkanı sağlar.
