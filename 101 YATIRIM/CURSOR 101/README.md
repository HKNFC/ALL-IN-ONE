# BIST Hisse Tarama Uygulaması

ALFA, BETA ve DELTA portföy kriterlerine göre BIST hisselerini tarayan web uygulaması.

## Kurulum

```bash
cd "/Users/hakanficicilar/Documents/Aİ/101 YATIRIM/CURSOR 101"
pip install -r requirements.txt
```

## Çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` adresi açılacaktır.

## Portföy Tipleri

| Portföy | Odak | Temel Kriterler | Teknik Kriterler |
|---------|------|-----------------|------------------|
| **ALFA** | Momentum / Büyüme | Yüksek büyüme potansiyeli | Fiyat > MA50, RSI 40-70, MACD pozitif |
| **BETA** | Değer / Piyasa uyumlu | Düşük F/K, temettü | Fiyat ~ MA200, RSI 30-55, destek bölgesi |
| **DELTA** | Defansif / İstikrarlı | Büyük kapitalizasyon | Fiyat > MA200, RSI 35-60, düşük volatilite |

## Klasör Yapısı

```
├── app.py                 # Streamlit web uygulaması
├── requirements.txt       # Python bağımlılıkları
├── data/
│   └── portfoy_verisi.csv # Referans portföy verileri
├── docs/
│   └── PORTFOY_ANALIZI.md # Detaylı analiz raporu
└── src/
    └── bist_screener.py   # Tarama motoru
```

## Veri Kaynağı

Hisse fiyat verileri **Yahoo Finance** (yfinance) üzerinden `Sembol.IS` formatıyla çekilir. BIST sembolleri için `.IS` soneki kullanılır.

## Not

- İlk tarama birkaç saniye sürebilir (her hisse için API çağrısı)
- Bazı BIST hisseleri Yahoo Finance'de bulunmayabilir
- Yatırım tavsiyesi değildir; eğitim ve araştırma amaçlıdır
